"""
Gemini vision extraction — ported from the reference implementation the
user added at poc-app/codebase/codebase/app.py (a standalone Streamlit
prototype), then re-pointed at the user's company LLM gateway
(https://llm-gateway.damcogroup.com/v1) once IT issued a paid key for it.
That gateway is OpenAI-compatible (POST /v1/chat/completions, not Google's
native generateContent), so this module talks to it via the `openai`
Python SDK with a custom base_url, rather than the `google-genai` SDK the
first version used - same two-call pattern and same JSON schemas as the
reference app, just a different transport underneath. Confirmed directly
against the real gateway before this rewrite: model list, plain vision
call, and schema-constrained JSON output (see the shell session that
produced this) all work exactly like the equivalent Google-direct calls
did.

The reference app's own two-call pattern is preserved as-is: one call
counts/groups boxes by visible distinguishing label, a second call reads
whatever text is printed on each box/group. What's added here is only the
glue this app needs that a Streamlit script doesn't: merging the two
calls' results together, pulling GTIN/Batch/Expiry out of the raw OCR text
per group, and returning the same {"items": [...], ...} shape scans.py's
/upload-gemini endpoint already expects - so nothing downstream of
extract_from_image() needed to change.
"""
import base64
import json
import re
import time

from openai import OpenAI

from app import config

GEMINI_MODEL = "gemini-3.5-flash"

# The gateway returns real HTTP status codes and OpenAI-shaped error bodies
# on failure (429 rate limit / quota, 503 upstream overload) - same
# transient-failure profile as calling Google directly, so the same
# retry-with-backoff approach applies unchanged.
_RETRYABLE_MARKERS = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "rate_limit")
_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 4


def _chat_with_retry(client: OpenAI, **kwargs):
    last_error = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            last_error = e
            if attempt < _MAX_ATTEMPTS - 1 and any(marker in str(e) for marker in _RETRYABLE_MARKERS):
                time.sleep(_RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            raise
    raise last_error  # pragma: no cover - loop always returns or raises above


BOX_COUNT_SCHEMA = {
    "type": "object",
    "properties": {
        "total_count": {"type": "integer"},
        "breakdown": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "count": {"type": "integer"},
                },
                "required": ["label", "count"],
            },
        },
    },
    "required": ["total_count", "breakdown"],
}

OCR_SCHEMA = {
    "type": "object",
    "properties": {
        "extracted_text": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "box_label": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["box_label", "text"],
            },
        },
    },
    "required": ["extracted_text"],
}

COUNT_PROMPT = (
    "Count all distinct boxes/cartons/packages visible in this image. Group them by any "
    "visible distinguishing label, size, or type.\n\n"
    "Count methodically, not at a glance - a rough visual estimate is not accurate enough:\n"
    "1. For each group, identify its rows and columns (or its packing pattern) and count "
    "row by row, keeping a running total as you go, rather than judging the total size of "
    "the pile by eye.\n"
    "2. Check every edge and corner of each cluster for boxes that are partially cut off by "
    "the frame, partially hidden behind another box, or in shadow - these are the units most "
    "often missed.\n"
    "3. After counting each group once, recount it a second time independently. If the two "
    "counts differ, look again at the specific area that's ambiguous (not the whole group) "
    "and resolve which count is correct before finalizing it.\n"
    "4. Do not round or estimate - report the exact number of individual boxes you can "
    "actually distinguish, even in a densely packed group.\n"
    "5. Watch for MULTI-LEVEL packaging - a large master carton that itself holds many "
    "smaller individual units, with its own contained quantity printed on it (e.g. \"Qty: 120\", "
    "\"120 PCS\", a case pack size, or similar). When a carton shows a printed contained "
    "quantity, the count for that group is the NUMBER OF SUCH CARTONS MULTIPLIED BY the "
    "quantity printed on each one - not the number of cartons alone. Include the GTIN in the "
    "label if it's printed and legible, so the group can be matched to an invoice line - e.g. "
    "\"Medium cartons (GTIN 03664798023251)\".\n\n"
    "Return the total count (individual units, not master cartons) and the group breakdown."
)

OCR_PROMPT = (
    "Read all text printed or written on each box/carton/package visible in this "
    "image (product name, batch number, expiry date, barcode text, etc). Return one "
    "entry per box or box group naming which box it belongs to and the text found."
)

# GS1-style fields embedded in the raw per-group OCR text (see real_extraction.py
# for the same pattern applied to Tesseract's output) - the reference app's OCR
# call returns free text, not structured fields, so this app still needs to pull
# GTIN/Batch/Expiry back out of it to validate against invoice line items.
_GTIN_RE = re.compile(r"GTIN[:\s]*([0-9]{8,14})", re.IGNORECASE)
_BATCH_RE = re.compile(r"(?:Lot/?Batch|Lot|Batch)[:\s]*([A-Za-z0-9\-]{2,15})", re.IGNORECASE)
_EXPIRY_RE = re.compile(
    r"Exp\.?[:\s]*([0-9]{4}[\-/][A-Za-z0-9]{2,4}(?:[\-/][0-9]{1,2})?|[0-9]{1,2}[\-/][0-9]{4})",
    re.IGNORECASE,
)


class GeminiExtractionError(RuntimeError):
    pass


def human_readable_error(e: Exception) -> tuple[int, str]:
    """
    Classifies a failed Gemini call into (http_status, client-safe message)
    - per user directive, no raw error JSON should ever reach the frontend
    (this is shown live in front of clients during demos). Distinct
    messages for daily-quota-exhausted vs. short-term-rate-limited vs.
    transient-overload, since "try again in a moment" is actively
    misleading for a daily quota that won't reset for hours.
    """
    text = str(e)
    if "PerDay" in text or ("RESOURCE_EXHAUSTED" in text and "quota" in text.lower()):
        return 429, (
            "This API key has reached its daily usage limit. It will reset automatically, "
            "or an admin can raise the limit via the LLM gateway/billing configuration."
        )
    if "429" in text or "RESOURCE_EXHAUSTED" in text or "rate_limit" in text.lower():
        return 429, "Too many scans in a short time - please wait about a minute and try again."
    if "503" in text or "UNAVAILABLE" in text:
        return 502, (
            "The AI extraction service is temporarily busy. Please wait a moment and try scanning again."
        )
    return 502, "The AI extraction service couldn't process this photo right now. Please try again shortly."


def _client() -> OpenAI:
    if not config.GEMINI_API_KEY:
        raise GeminiExtractionError("GEMINI_API_KEY is not set in the environment.")
    return OpenAI(api_key=config.GEMINI_API_KEY, base_url=config.GEMINI_BASE_URL)


def _image_content_block(image_bytes: bytes) -> dict:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}


def detect_boxes(client: OpenAI, image_bytes: bytes) -> dict:
    response = _chat_with_retry(
        client,
        model=GEMINI_MODEL,
        messages=[{"role": "user", "content": [{"type": "text", "text": COUNT_PROMPT}, _image_content_block(image_bytes)]}],
        response_format={"type": "json_schema", "json_schema": {"name": "box_count", "schema": BOX_COUNT_SCHEMA}},
        # Counting is a factual-extraction task, not a creative one - the
        # default sampling temperature is a real, measured cause of count
        # variance run to run on the identical photo (seen directly: 24 vs
        # 23, 36 vs 31 on the same real images). Low temperature makes the
        # model consistently pick its highest-confidence count instead of
        # sampling a different plausible answer each call.
        temperature=0.1,
    )
    return json.loads(response.choices[0].message.content)


def read_box_text(client: OpenAI, image_bytes: bytes) -> dict:
    response = _chat_with_retry(
        client,
        model=GEMINI_MODEL,
        messages=[{"role": "user", "content": [{"type": "text", "text": OCR_PROMPT}, _image_content_block(image_bytes)]}],
        response_format={"type": "json_schema", "json_schema": {"name": "box_ocr", "schema": OCR_SCHEMA}},
    )
    return json.loads(response.choices[0].message.content)


def _parse_gs1_fields(text: str) -> dict:
    g = _GTIN_RE.search(text)
    b = _BATCH_RE.search(text)
    e = _EXPIRY_RE.search(text)
    return {
        "gtin": g.group(1) if g else None,
        "batch": b.group(1) if b else None,
        "expiry": e.group(1) if e else None,
    }


def detect_boxes_only(image_bytes: bytes) -> dict:
    """
    Just the reference app's count/group call (detect_boxes) - no OCR call.
    Per user directive: Gemini is used ONLY to cross-check the count per
    product group; field extraction (GTIN/Batch/Expiry/Serial) stays on the
    existing classical barcode/OCR pipeline, unchanged. Returns
    {"total_count": N, "breakdown": [{"label": str, "count": int}, ...]}
    exactly as the reference schema defines it - no merging needed since
    there's no second call's output to reconcile against.
    """
    client = _client()
    try:
        return detect_boxes(client, image_bytes)
    except Exception as e:
        raise GeminiExtractionError(f"Gemini request failed: {e}") from e


def extract_from_image(image_bytes: bytes) -> dict:
    """
    Runs the reference app's two-call pipeline (count+group, then per-group
    OCR) and merges both into this app's existing extraction result shape:
    {"items": [{"gtin", "batch", "expiry", "product_name", "count",
    "count_confidence"}, ...], "total_units_visible", "notes"}.

    Kept for reference/comparison - the active scan endpoint now uses
    detect_boxes_only() instead (see scan_upload_gemini in scans.py), per
    user directive to stop using Gemini's OCR call and keep the classical
    pipeline for field extraction.
    """
    client = _client()
    try:
        detection = detect_boxes(client, image_bytes)
        ocr = read_box_text(client, image_bytes)
    except Exception as e:
        raise GeminiExtractionError(f"Gemini request failed: {e}") from e

    # The two calls describe groups at different granularity: the count
    # call groups by PRODUCT ("large blue and white cartons"), the OCR call
    # labels INDIVIDUAL boxes ("top-left box 1", "bottom row box 3") -
    # fuzzy-matching those two label vocabularies directly almost never
    # scores well (verified: a real run returned zero matches this way even
    # though both calls' underlying data was correct). Instead, parse the
    # GTIN/Batch out of every individual OCR entry first, group entries
    # that share the same (gtin, batch) - a real per-product identity, not
    # a label string - then pair each count-breakdown group to whichever
    # identity group's own entry-count is numerically closest to it. Counts
    # naturally align between the two calls (both are counting the same
    # real boxes), even though the label wording never will.
    ocr_entries = ocr.get("extracted_text", [])
    identity_groups: dict[tuple[str | None, str | None], list[dict]] = {}
    for entry in ocr_entries:
        fields = _parse_gs1_fields(entry.get("text", ""))
        key = (fields["gtin"], fields["batch"])
        if key == (None, None):
            continue  # nothing identifiable in this entry - can't group it
        identity_groups.setdefault(key, []).append(fields)

    unassigned_keys = set(identity_groups.keys())
    items = []
    for group in detection.get("breakdown", []):
        label = group.get("label", "")
        count = int(group.get("count") or 0)
        best_key = None
        if unassigned_keys:
            best_key = min(unassigned_keys, key=lambda k: abs(len(identity_groups[k]) - count))
            unassigned_keys.discard(best_key)
        fields = identity_groups[best_key][0] if best_key else {"gtin": None, "batch": None, "expiry": None}
        items.append({
            "gtin": fields["gtin"],
            "batch": fields["batch"],
            "expiry": fields["expiry"],
            "product_name": label,
            "count": count,
            # The reference schema has no per-group confidence field (only
            # a single overall count) - "high" reflects that this is the
            # model's own direct count, not a downstream heuristic guess.
            "count_confidence": "high",
        })

    return {
        "items": items,
        "total_units_visible": detection.get("total_count"),
        "notes": (
            f"Extracted via {GEMINI_MODEL} (2-call: box count/group detection, "
            "then per-group OCR text read) via the company LLM gateway."
        ),
    }
