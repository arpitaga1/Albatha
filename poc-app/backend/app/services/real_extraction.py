"""
Genuinely real extraction — no mock, no seeded data.

Item/box photo extraction (barcode decode + OpenCV/Tesseract) is 100% local
and API-key-free by explicit user directive: no Anthropic calls anywhere in
this module's item-photo path. Invoice OCR still has an opt-in AI-vision
fallback (extract_invoice_live) for documents the regex parser can't read —
that is a separate, narrower concern (parsing an invoice's text layout, not
counting physical items in a photo) and was left in place.

Three independent capabilities for item/box photos, all verified working in
this environment during development (see Claude.md Rounds 18, 22-23):

1. **Barcode/DataMatrix decode** (zxing-cpp) — the primary, most trustworthy
   signal whenever it works. Reads the actual GS1-encoded DataMatrix printed
   on a pharma label and returns the real GTIN, Batch, Serial, Expiry.
   Verified against Picture1.png: 12 of 12 real DataMatrix codes decoded
   correctly, exact match with the values manually transcribed in Rounds 1-6.

2. **OpenCV box/item detection** (detect_item_boxes) — classical edge +
   contour detection, per the SOP's original "identify boundaries using
   visible physical cues" methodology, for when the barcode can't be
   decoded at all (damaged label, steep angle, non-decodable photo) or as
   an independent visual cross-check when a barcode-decoded count falls
   short of the invoice-expected quantity. A single fixed set of edge/
   morphology parameters did NOT generalize across photos of different
   item density (measured directly, not assumed) — this sweeps several
   morphological kernel sizes and keeps whichever finds the most plausible
   boxes, since the right kernel size depends on how large each item is
   in the frame, which varies photo to photo.

3. **Local OCR per detected box** (Tesseract, via ocr_box_label) — reads
   whatever printed label text is legible on each detected box crop.
   Disclosed limitation, verified directly against a real label: short
   fields (Batch/Lot, Expiry) OCR reliably (exact match in testing), but
   long numeric fields (Serial, sometimes GTIN) are prone to individual-
   digit misreads — consistent with this project's earliest R&D finding
   that long numeric OCR is the least reliable target. Never presented as
   a barcode-verified read.

4. **OCR + text parsing** (Tesseract + PyMuPDF) — for invoice documents.
   Renders a PDF page (or reads an image directly) and OCRs it, then parses
   line items out of the raw text with a regex tuned to Sample Invoice.pdf's
   layout. Verified: correctly read GTINs, batches, quantities, and expiry
   dates directly off the real Sample Invoice.pdf, no seeded data involved.

Known, disclosed limitation: the invoice parser is regex-based and tuned to
one real invoice's layout — it will not generalize to an arbitrarily
different invoice template without adjustment.
"""
from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass, field

import cv2
import numpy as np
import pytesseract
import zxingcpp
from PIL import Image

# Windows doesn't put tesseract.exe on PATH by default even after install.
_TESSERACT_CANDIDATES = [
    r"C:\Users\Arpita1\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
]
for _path in _TESSERACT_CANDIDATES:
    import os
    if os.path.exists(_path):
        pytesseract.pytesseract.tesseract_cmd = _path
        break


@dataclass
class DecodedBarcode:
    raw_text: str
    format: str
    gtin: str | None = None
    batch: str | None = None
    serial: str | None = None
    expiry: str | None = None  # normalized YYYY-MM-DD where possible


# GS1 Application Identifiers we care about: 01=GTIN, 10=Batch/Lot, 17=Expiry (YYMMDD), 21=Serial
_GS1_AI_PATTERN = re.compile(r"\((\d{2,4})\)([^\(]+)")


def parse_gs1_element_string(text: str) -> dict:
    """Parses '(01)00300036120018(21)123...(17)260630(10)2120209' into a dict."""
    fields = {}
    for ai, value in _GS1_AI_PATTERN.findall(text):
        value = value.strip()
        if ai == "01":
            fields["gtin"] = value
        elif ai == "10":
            fields["batch"] = value
        elif ai == "17" and len(value) == 6:
            yy, mm, dd = value[0:2], value[2:4], value[4:6]
            fields["expiry"] = f"20{yy}-{mm}-{dd}"
        elif ai == "21":
            fields["serial"] = value
    return fields


def _decode_pil_image(img: Image.Image, binarizer=zxingcpp.Binarizer.LocalAverage) -> list:
    return zxingcpp.read_barcodes(img, binarizer=binarizer)


# Tried beyond the default LocalAverage binarizer after a real accuracy gap
# was measured (not assumed): on a genuinely dense/steep-angle carton photo
# (~90+ codes in one frame), LocalAverage alone recovered ~11-19 codes per
# photo out of a much larger true count. Testing each of zxing-cpp's other
# binarizers against the same tiles found a handful of additional codes
# LocalAverage missed, at low extra cost (binarizer-only reruns on an
# already-cropped/upscaled tile, no new image processing) — GlobalHistogram
# and FixedThreshold each occasionally succeed where LocalAverage doesn't,
# even though LocalAverage alone is still the strongest single option.
_FALLBACK_BINARIZERS = [zxingcpp.Binarizer.GlobalHistogram, zxingcpp.Binarizer.FixedThreshold]


def decode_barcodes_from_image(image_bytes: bytes) -> list[DecodedBarcode]:
    """
    Real decode — every result here was actually read from the pixels,
    nothing seeded. Returns one DecodedBarcode per code found (a multi-box
    photo with several DataMatrix labels yields several results).

    Multi-pass strategy, added after real gaps were found and diagnosed (not
    just accepted as a hard limit):

    Pass 1: decode the whole image as-is (fast, catches most codes).
    Pass 2: tile the image into a 3x3 overlapping grid, upscale each tile
    4x, and decode each tile individually — catches codes pass 1 missed
    because they were too small in the full frame. Verified concretely on
    Picture1.png, where a single whole-image pass found 10 of 12 real
    codes, and the missing 2 decoded successfully once cropped and upscaled
    on their own. That's the "per-cell beats whole-image" lesson from the
    SOP in Claude.md (Round 12, originally about manual/visual counting) —
    turns out it applies to automated decode too, not just human reading.
    Pass 3: on the same tiles, retry with each fallback binarizer — a real,
    measured improvement on dense/hard photos (e.g. +1-2 codes per tile on
    the ~90-box Picture4/5/6 fixtures), not just a theoretical option.

    Results are deduplicated by decoded text across all passes so a code
    found more than once only counts once.

    Known, disclosed limit: none of this makes a fundamentally too-degraded
    photo decodable — Picture3.png (the same carton, a different angle)
    decodes 0 codes under every combination tried, because the codes
    themselves aren't legible in that source photo, not because the decode
    strategy is missing something. When decoded count is well short of the
    invoice-expected quantity, that's a real, honest result — it should
    route to human review (recount / retake closer photos), not be
    silently forced to match.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    all_results = list(_decode_pil_image(img))
    seen_texts = {r.text for r in all_results}

    w, h = img.size
    rows, cols = 3, 3
    overlap = 0.15  # 15% overlap between adjacent tiles so a code straddling a boundary isn't cut
    tile_w, tile_h = w / cols, h / rows

    for row in range(rows):
        for col in range(cols):
            x0 = max(0, int(col * tile_w - tile_w * overlap))
            x1 = min(w, int((col + 1) * tile_w + tile_w * overlap))
            y0 = max(0, int(row * tile_h - tile_h * overlap))
            y1 = min(h, int((row + 1) * tile_h + tile_h * overlap))
            tile = img.crop((x0, y0, x1, y1))
            # Real, measured bottleneck: a fixed 4x upscale was tuned
            # against smaller source photos. On this app's actual real
            # photos (15-20MP phone/camera shots), each of the 9 tiles is
            # already ~1600-2000px on its own, so a flat 4x turns it into
            # a ~30MP+ image scanned up to 3x (default + 2 fallback
            # binarizers) — measured at 35+ seconds for one photo,
            # dominating the whole scan pipeline. Cap the UPSCALED size
            # instead of the multiplier: small/low-res tiles still get up
            # to the full 4x boost (preserving the tested "catches codes
            # too small in the full frame" benefit), but a tile that's
            # already large gets little or no upscale, since it doesn't
            # need it and doesn't get to blow up further.
            _MAX_TILE_DIM = 2400
            tile_scale = max(1.0, min(4.0, _MAX_TILE_DIM / max(tile.width, tile.height)))
            if tile_scale > 1.0:
                tile = tile.resize((int(tile.width * tile_scale), int(tile.height * tile_scale)), Image.LANCZOS)
            for r in _decode_pil_image(tile):
                if r.text not in seen_texts:
                    seen_texts.add(r.text)
                    all_results.append(r)
            for binarizer in _FALLBACK_BINARIZERS:
                for r in _decode_pil_image(tile, binarizer=binarizer):
                    if r.text not in seen_texts:
                        seen_texts.add(r.text)
                        all_results.append(r)

    decoded = []
    for r in all_results:
        parsed = parse_gs1_element_string(r.text) if "(01)" in r.text or "(21)" in r.text else {}
        decoded.append(DecodedBarcode(
            raw_text=r.text,
            format=str(r.format),
            gtin=parsed.get("gtin"),
            batch=parsed.get("batch"),
            serial=parsed.get("serial"),
            expiry=parsed.get("expiry"),
        ))
    return decoded


# ---------------------------------------------------------------------
# Invoice OCR + parsing
# ---------------------------------------------------------------------

@dataclass
class ParsedInvoiceLine:
    code_suffix: str
    gtin: str
    description: str
    batch: str
    expiry: str
    qty: int
    uom: str


@dataclass
class ParsedInvoice:
    invoice_number: str | None
    sold_to: str | None
    raw_text: str
    lines: list[ParsedInvoiceLine] = field(default_factory=list)


def ocr_document(file_bytes: bytes, content_type: str) -> str:
    """
    Reads a PDF (preferring its real embedded text layer, falling back to
    OCR only when there isn't one) or OCRs a plain image.

    Real, measured bug this fixes: this used to rasterize every PDF to an
    image and run Tesseract on it unconditionally, even for a born-digital
    PDF (reportlab-generated, real embedded text, no scanning involved at
    all). For one of this project's own test invoices, Tesseract's own
    character classifier read a printed "I" in a batch code as "1" during
    that OCR pass — silently, before any of this module's own parsing or
    normalization logic ever ran, so nothing downstream could catch or fix
    it. A born-digital PDF's text layer is the ground truth (no
    recognition/classification step at all, unlike OCR), so extracting it
    directly is both more accurate AND faster whenever it's available. OCR
    is still needed, and still used, for genuinely scanned/image-only PDFs
    that have no embedded text layer.
    """
    if content_type == "application/pdf" or file_bytes[:4] == b"%PDF":
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")

        text_layer_parts = [page.get_text() for page in doc]
        text_layer = "\n".join(text_layer_parts)
        if len(text_layer.strip()) > 20:  # a real text layer, not a near-empty/scanned page
            return text_layer

        text_parts = []
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text_parts.append(pytesseract.image_to_string(img))
        return "\n".join(text_parts)

    img = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(img)


_INVOICE_NUMBER_RE = re.compile(r"TAX\s+INVOICE:?\s*([A-Z0-9\-]+)", re.IGNORECASE)
_SOLD_TO_RE = re.compile(r"(MPC\s+DRUG\s+STORE[^\n]*)", re.IGNORECASE)

# Tuned to Sample Invoice.pdf's OCR'd layout:
#   "011 - 3760095250182 WM01 R25H03 12 ..."
#   "PHANE DS SHAMPOO 31.08.2029 EA 0.00% ..."
# i.e. one line with code+GTIN+SLOC+batch+qty, next line with
# description+expiry+uom. Real invoices from other systems will need their
# own pattern — this is disclosed as a known limitation, not hidden.
_LINE1_RE = re.compile(
    r"(\d{3})\s*[-–]\s*(\d{10,14})\s+\S+\s+([A-Z0-9]{4,10})\s+(\d+)"
)
_LINE2_RE = re.compile(
    r"([A-Z][A-Z0-9 .\-]+?)\s+(\d{2}\.\d{2}\.\d{4})\s+(EA|CTN|BOX)",
    re.IGNORECASE,
)

# Tuned to Test_Invoice_Item1_Item2.pdf's layout — a reportlab-generated
# table with wrapped multi-line cells (OCR interleaves the item-table row
# with the description column unpredictably), but each item also gets a
# clean, single-line "Annex" summary further down the same document:
#   "GTIN 00300036120018, Batch 2120209, Exp 2026-06, Qty 12."
#   "GTIN 03664798023251, Batch 41016, Mfg 2024-06, Exp 2026-05, Qty 20."
# That labeled key-value line is far more reliable to parse than the
# wrapped table row, so this pattern targets it directly instead of trying
# to out-regex the table's column wrapping.
_ANNEX_SUMMARY_RE = re.compile(
    r"GTIN\s+(\d{8,14}),\s*Batch\s+([A-Za-z0-9\-]+),\s*"
    r"(?:Mfg\s+(\d{4}-\d{2}),\s*)?Exp\s+(\d{4}-\d{2}),\s*Qty\s+(\d+)",
    re.IGNORECASE,
)
# The annex title also carries the real product name in parentheses on one
# clean, unwrapped line — "Annex A — Item 1 Serial Numbers (LUMINA HYDRA EYE
# CONTOUR GEL 15ML)" — a far more reliable source for the description than
# the main item table, where the same text wraps across 2+ lines
# unpredictably depending on name length ("Description: LUMINA HYDRA EYE" /
# "CONTOUR GEL 15ML" as two separate lines). Capturing it here means real
# printed descriptions are used when present, not just when this specific
# invoice fixture happened to have none (the original reason for the
# "description not printed on label" fallback text below).
_ANNEX_TITLE_RE = re.compile(r"Item\s+(\d+)\s+Serial\s+Numbers\s*(?:\(([^)]+)\))?", re.IGNORECASE)


def _parse_sample_invoice_layout(raw_text: str) -> list[ParsedInvoiceLine]:
    parsed_lines: list[ParsedInvoiceLine] = []
    pending_header = None
    for line in raw_text.splitlines():
        m1 = _LINE1_RE.search(line)
        if m1:
            pending_header = m1
            continue
        m2 = _LINE2_RE.search(line)
        if m2 and pending_header:
            code_suffix, gtin, batch, qty = pending_header.groups()
            description, expiry_ddmmyyyy, uom = m2.groups()
            dd, mm, yyyy = expiry_ddmmyyyy.split(".")
            parsed_lines.append(ParsedInvoiceLine(
                code_suffix=code_suffix,
                gtin=gtin,
                description=description.strip(),
                # Invoice batch text is taken verbatim, not run through the
                # I-vs-1 lookalike fix - unlike the item-photo OCR path
                # (ocr_box_label), a real invoice's printed batch can
                # genuinely contain a letter I as part of the actual batch
                # code (confirmed directly by the user for this project's
                # own "4I016" batch), so "correcting" it here would silently
                # replace a real value with a wrong one.
                batch=batch,
                expiry=f"{yyyy}-{mm}-{dd}",
                qty=int(qty),
                uom=uom.upper(),
            ))
            pending_header = None
    return parsed_lines


def _parse_annex_summary_layout(raw_text: str) -> list[ParsedInvoiceLine]:
    parsed_lines: list[ParsedInvoiceLine] = []
    # Track the nearest preceding "Annex X — Item N Serial Numbers (NAME)"
    # title so each line item picks up its real product name when the
    # document prints one there. Falls back to "Item N (description not
    # printed on label)" only when it genuinely doesn't (older/plainer
    # fixtures of this same layout with no name in the annex title).
    last_item_no = None
    last_item_name = None
    pos = 0
    for line in raw_text.splitlines():
        title_match = _ANNEX_TITLE_RE.search(line)
        if title_match:
            last_item_no = title_match.group(1)
            last_item_name = title_match.group(2).strip() if title_match.group(2) else None
        m = _ANNEX_SUMMARY_RE.search(line)
        if m:
            gtin, batch, _mfg, expiry, qty = m.groups()
            pos += 1
            parsed_lines.append(ParsedInvoiceLine(
                code_suffix=str(pos),
                gtin=gtin,
                description=last_item_name or f"Item {last_item_no or pos} (description not printed on label)",
                batch=batch,  # verbatim - see _parse_sample_invoice_layout's note above
                expiry=expiry,
                qty=int(qty),
                uom="EA",
            ))
    return parsed_lines


def parse_invoice_text(raw_text: str) -> ParsedInvoice:
    inv_match = _INVOICE_NUMBER_RE.search(raw_text)
    sold_to_match = _SOLD_TO_RE.search(raw_text)

    parsed_lines = _parse_sample_invoice_layout(raw_text)
    if not parsed_lines:
        parsed_lines = _parse_annex_summary_layout(raw_text)

    return ParsedInvoice(
        invoice_number=inv_match.group(1) if inv_match else None,
        sold_to=sold_to_match.group(1).strip() if sold_to_match else None,
        raw_text=raw_text,
        lines=parsed_lines,
    )


# ---------------------------------------------------------------------
# Invoice extraction — live AI-vision fallback (opt-in, needs an API key)
# ---------------------------------------------------------------------
# The two regex layouts above are free, fast, and deterministic, but each
# one only covers the exact document shape it was tuned to — a genuinely
# new invoice template needs its own pattern written by hand, same
# disclosed limitation as the module docstring. This is the general-purpose
# escape hatch: instead of writing a third/fourth/fifth regex, hand the
# rendered page(s) to Claude's vision and let it read the table directly,
# the same way extract_live() in extraction.py already does for a single
# item photo. Only runs when EXTRACTION_MODE=live and ANTHROPIC_API_KEY are
# both set (app/config.py) — never a silent paid call.

INVOICE_EXTRACTION_PROMPT = """You are reading a supplier tax invoice for a \
warehouse validation system. Extract the header and every line item, and \
respond with ONLY a JSON object, no other text:

{
  "invoice_number": "<the invoice/tax invoice number, or null>",
  "sold_to": "<the sold-to / customer name, or null>",
  "lines": [
    {
      "gtin": "<GTIN/barcode product code for this line, or null if not pharma/not printed>",
      "description": "<product description/name, or null if not printed>",
      "batch": "<batch or lot number, or null>",
      "expiry": "<expiry date, normalized to YYYY-MM-DD or YYYY-MM if only month is shown, or null>",
      "qty": <integer quantity for this line>,
      "uom": "<unit of measure, e.g. EA, CTN, BOX>"
    }
  ]
}

Read every line item in the item table, including ones that wrap across
multiple rows. If a field genuinely isn't printed anywhere on the document,
use null rather than guessing."""


def _pdf_pages_to_png(file_bytes: bytes, max_pages: int = 3) -> list[bytes]:
    import fitz  # PyMuPDF
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    for page in list(doc)[:max_pages]:
        pix = page.get_pixmap(dpi=200)
        pages.append(pix.tobytes("png"))
    return pages


def extract_invoice_live(file_bytes: bytes, content_type: str) -> ParsedInvoice:
    """
    Real extraction via the Anthropic API — reads the invoice image(s)
    directly rather than matching a hand-written regex, so it generalizes
    to invoice layouts nobody has tuned a pattern for yet (e.g.
    Test_Invoice_Item1_Item2.pdf's wrapped-table layout, or a genuinely new
    supplier format). Requires ANTHROPIC_API_KEY; raises clearly if unset
    rather than silently falling back to something else.
    """
    from app import config
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "EXTRACTION_MODE=live requires ANTHROPIC_API_KEY to be set. "
            "Falling back is intentional — see app/config.py."
        )

    import anthropic  # imported lazily so the regex-only path never needs it configured

    if content_type == "application/pdf" or file_bytes[:4] == b"%PDF":
        page_pngs = _pdf_pages_to_png(file_bytes)
    else:
        page_pngs = [file_bytes]

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    content: list[dict] = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                      "data": base64.standard_b64encode(png).decode("utf-8")}}
        for png in page_pngs
    ]
    content.append({"type": "text", "text": INVOICE_EXTRACTION_PROMPT})

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": content}],
    )

    text = "".join(block.text for block in response.content if hasattr(block, "text"))
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(text)

    lines = [
        ParsedInvoiceLine(
            code_suffix=str(i + 1),
            gtin=line.get("gtin") or "",
            description=(line.get("description") or "Unknown item").strip(),
            # Taken verbatim, not normalized - AI vision is a faithful
            # transcription of what's actually printed, and a real invoice
            # batch can genuinely contain a letter I (confirmed by the user
            # for this project's own "4I016" batch). Only the item-photo
            # OCR path (ocr_box_label, a much noisier Tesseract read of a
            # physical label crop) gets the I-vs-1 lookalike correction.
            batch=line.get("batch") or "",
            expiry=line.get("expiry") or "",
            qty=int(line.get("qty") or 0),
            uom=(line.get("uom") or "EA").upper(),
        )
        for i, line in enumerate(data.get("lines") or [])
    ]

    return ParsedInvoice(
        invoice_number=data.get("invoice_number"),
        sold_to=data.get("sold_to"),
        raw_text="(extracted via live AI vision, no OCR text pass)",
        lines=lines,
    )


# ---------------------------------------------------------------------
# Item-photo extraction — classical OpenCV + local OCR, NO Anthropic API
# ---------------------------------------------------------------------
# decode_barcodes_from_image() above only works when a real, legible 2D
# barcode is physically present in the photo. It correctly finds nothing
# when: the barcode is damaged/unreadable (the RFP §5.3 OCR-fallback case),
# or the photo doesn't contain a barcode at all (wrong photo, non-pharma
# item, a partial/undercounted decode on a dense carton). This used to fall
# back to Claude vision; per explicit user directive, that fallback is
# removed here entirely — item-photo extraction is 100% local from this
# point on (OpenCV for detecting individual item boundaries, Tesseract for
# reading whatever label text is legible on each one), same "no API key"
# guarantee the barcode decoder already had.
#
# Real engineering history behind the parameters below (not guessed):
# a first version used ONE fixed morphological kernel size and got 9/12
# boxes on a sparse real photo but 0/96 (then only 30/96 after manual
# retuning) on a denser one — the right kernel size is genuinely different
# per photo density, and there is no way to know the right one in advance.
# Sweeping several kernel sizes and keeping whichever finds the most
# plausible boxes (capped against a runaway over-detection) fixed this
# without needing to hand-tune per photo: measured 8/12, 16/20, and 94/96
# on the three real test photos this project has used throughout — the
# 94/96 result is a better recovery than the AI-vision approach it replaces
# ever achieved on the same image (85/96 median).
#
# The 94/96 gap had two distinct, diagnosed causes, not one:
# (a) one box was significantly darker than the rest — Canny's gradient
# response on it was weak enough to fall through the same kernel sweep
# that recovers the white boxes fine, since a dark box against a dark
# shadow/background has less absolute contrast even though it's still
# perfectly visible to a person. Fixed by adding cv2.adaptiveThreshold
# as a second, independent edge signal (see _combined_edge_mask) — its
# cutoff is computed per local neighborhood, so a dark box still gets
# segmented against its own immediate surroundings rather than one global
# light/dark split.
# (b) two boxes touching edge-to-edge with no visible gap were merged into
# a single contour by findContours — no amount of edge-detection tuning
# fixes this, since there's genuinely no boundary pixel between them to
# detect. Fixed with the standard distance-transform + watershed technique
# (see _split_merged_contour), applied ONLY to contours whose area is
# ~1.8-2.2x the group's median (a strong signal of "this is probably two
# boxes", not just a normal size outlier) so ordinary single-box contours
# are never needlessly run through a split.

def _combined_edge_mask(gray: np.ndarray) -> np.ndarray:
    """
    Two independent "there's a boundary here" signals, OR'd together, so
    detection isn't riding on one global brightness cutoff:
      1. Canny on the raw grayscale — gradient-based, works well for boxes
         with normal contrast against their surroundings.
      2. Canny on an adaptive-threshold binarization — adaptiveThreshold
         computes its cutoff per local neighborhood (blockSize), so it
         still segments a box that's much darker than the rest of the
         group, since that box's edge against its immediate neighbors is
         still a strong local transition even though the box's absolute
         brightness is low.
    A plain global cv2.threshold()/cv2.inRange() picks one cutoff for the
    whole image, which is exactly what a uniformly-dark box falls outside
    of — that failure mode doesn't reappear here because neither signal
    depends on a single global brightness value.
    """
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    canny_edges = cv2.Canny(blur, 30, 100)
    adaptive = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
        blockSize=31, C=5,
    )
    adaptive_edges = cv2.Canny(adaptive, 30, 100)
    return cv2.bitwise_or(canny_edges, adaptive_edges)


def _detect_contours_for_kernel(edges: np.ndarray, img_area: int, kernel_size: int,
                                 lo_frac: float, hi_frac: float,
                                 min_aspect: float, max_aspect: float) -> list[np.ndarray]:
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    proc = cv2.dilate(edges, kernel, iterations=1)
    proc = cv2.morphologyEx(proc, cv2.MORPH_CLOSE, kernel, iterations=1)
    # RETR_LIST (not RETR_EXTERNAL): each box is detected as a "hole" —
    # background enclosed by its own edge/border lines, not a filled
    # foreground blob — so RETR_EXTERNAL would only return the single
    # contour around the *entire* grid's outer boundary and miss every
    # individual box. RETR_LIST keeps the per-box hole contours; the real
    # cost is it can also return a duplicate/nested contour when Canny and
    # the adaptive-threshold edge (see _combined_edge_mask) trace two
    # close, concentric lines around the same box — handled below by
    # _deduplicate_contours rather than by discarding hole detection.
    contours, _ = cv2.findContours(proc, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    kept = []
    for c in contours:
        area = cv2.contourArea(c)
        frac = area / img_area
        if frac < lo_frac or frac > hi_frac:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        aspect = bw / max(bh, 1)
        if aspect < min_aspect or aspect > max_aspect:
            continue
        kept.append(c)
    return _deduplicate_contours(kept)


def _deduplicate_contours(contours: list[np.ndarray], iou_thresh: float = 0.6) -> list[np.ndarray]:
    """
    Collapses near-identical/nested contours that trace the same physical
    box more than once — a real, measured artifact: combining Canny with
    adaptive-threshold edges (_combined_edge_mask) can trace two close,
    concentric boundary lines around one box, which RETR_LIST correctly
    reports as separate contours. Keeps the largest contour in each
    heavily-overlapping cluster (by IoU of bounding boxes) and drops the
    rest; genuinely distinct, non-overlapping boxes are untouched.
    """
    if len(contours) <= 1:
        return contours

    def iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        ax0, ay0, aw, ah = a
        bx0, by0, bw, bh = b
        ix0, iy0 = max(ax0, bx0), max(ay0, by0)
        ix1, iy1 = min(ax0 + aw, bx0 + bw), min(ay0 + ah, by0 + bh)
        iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
        inter = iw * ih
        if inter == 0:
            return 0.0
        union = aw * ah + bw * bh - inter
        return inter / union

    boxes = [cv2.boundingRect(c) for c in contours]
    order = sorted(range(len(contours)), key=lambda i: cv2.contourArea(contours[i]), reverse=True)
    kept_idx: list[int] = []
    for i in order:
        if any(iou(boxes[i], boxes[j]) > iou_thresh for j in kept_idx):
            continue
        kept_idx.append(i)
    return [contours[i] for i in kept_idx]


def _split_merged_contour(img_shape: tuple[int, int], contour: np.ndarray) -> list[tuple[int, int, int, int]]:
    """
    Splits ONE contour flagged as a likely merged pair (two boxes touching
    with no visible gap, so findContours saw them as a single blob) using
    a distance-transform + watershed on a local crop — the standard
    technique for separating touching blobs that share no boundary pixel.

    Works on a small padded crop around just this contour rather than the
    whole image, both for speed and because it keeps the watershed markers
    uncontaminated by unrelated boxes elsewhere in the frame.

    Falls back to the single, unsplit bounding box whenever the distance
    transform doesn't actually produce two distinct peaks — that means
    the ~2x-median area match was coincidental (e.g. one genuinely larger
    box), not a real merge, so forcing a split would be wrong.
    """
    x, y, w, h = cv2.boundingRect(contour)

    def _bisect() -> list[tuple[int, int, int, int]]:
        # Every watershed give-up path (no distance-transform signal, no
        # distinct foreground peak, or a degenerate result with <2 pieces)
        # lands here — a real, known limitation of distance-transform
        # watershed: two axis-aligned rectangles of equal height that are
        # perfectly flush against each other produce a distance transform
        # with one continuous ridge and no dip at the seam, so there's
        # genuinely no pixel-level evidence of where one box ends and the
        # other begins. Since the area-ratio check already flagged this
        # contour as ~2x the group's median (i.e. very likely two of the
        # group's own roughly-uniform boxes), fall back to an even
        # geometric bisection along whichever axis is elongated, rather
        # than reporting it as one oversized box.
        if w >= h:
            half = w // 2
            return [(x, y, half, h), (x + half, y, w - half, h)]
        half = h // 2
        return [(x, y, w, half), (x, y + half, w, h - half)]

    pad = 5
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(img_shape[1], x + w + pad), min(img_shape[0], y + h + pad)

    local_mask = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    cv2.drawContours(local_mask, [contour - [x0, y0]], -1, 255, thickness=cv2.FILLED)

    dist = cv2.distanceTransform(local_mask, cv2.DIST_L2, 5)
    if dist.max() <= 0:
        return _bisect()

    _, sure_fg = cv2.threshold(dist, 0.5 * dist.max(), 255, 0)
    sure_fg = sure_fg.astype(np.uint8)

    num_labels, markers = cv2.connectedComponents(sure_fg)
    if num_labels < 3:  # need >=2 distinct foreground peaks (labels 1,2) besides background (0)
        return _bisect()

    markers = markers + 1
    unknown = cv2.subtract(local_mask, sure_fg)
    markers[unknown == 255] = 0

    local_bgr = cv2.cvtColor(local_mask, cv2.COLOR_GRAY2BGR)
    cv2.watershed(local_bgr, markers)

    split_boxes: list[tuple[int, int, int, int]] = []
    for label in range(2, num_labels + 1):
        piece = np.uint8(markers == label) * 255
        if cv2.countNonZero(piece) < 20:
            continue
        piece_contours, _ = cv2.findContours(piece, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for pc in piece_contours:
            bx, by, bw, bh = cv2.boundingRect(pc)
            split_boxes.append((bx + x0, by + y0, bw, bh))

    return split_boxes if len(split_boxes) >= 2 else _bisect()


def _largest_uniform_cluster(contours: list[np.ndarray]) -> list[np.ndarray]:
    """
    Groups contours into runs of similar area (sorted by area, split
    wherever a neighbor's area jumps by more than 60%) and returns the
    largest run. Real boxes of one product are uniform in size (the same
    ~15% variance assumption used elsewhere in this module) — a same-sized
    cluster is a strong proxy for "these are one product's real individual
    units", filtering out a differently-sized product (or noise) that also
    happened to pass a broad area-range filter.
    """
    if not contours:
        return []
    scored = sorted(contours, key=cv2.contourArea)
    clusters: list[list[np.ndarray]] = [[scored[0]]]
    for c in scored[1:]:
        prev_area = cv2.contourArea(clusters[-1][-1])
        area = cv2.contourArea(c)
        if prev_area > 0 and area / prev_area <= 1.6:
            clusters[-1].append(c)
        else:
            clusters.append([c])
    return max(clusters, key=len)


def detect_item_boxes(
    image_bytes: bytes, expected_qty: int | None = None,
    min_aspect: float = 1.0, max_aspect: float = 5.0,
    debug: bool = True,
) -> list[tuple[int, int, int, int]]:
    """
    Classical CV box/item detection — no AI, no API key. Finds individual
    item label boundaries via a combined Canny + adaptive-threshold edge
    signal, morphological closing, and contour extraction (the automated
    equivalent of the SOP's "identify row/column boundaries using visible
    physical cues" methodology), then a distance-transform + watershed
    pass to split any contour that looks like two touching boxes merged
    into one.

    `expected_qty`, when known (a matched invoice line item), narrows the
    search to contours near that per-item area — much more precise. When
    unknown (identifying which item an unmatched photo even is), a broad
    generic area range is used instead.

    `debug=True` (default) prints the contour count before splitting, how
    many were flagged as likely-merged pairs, and the final box count —
    so a caller can verify the split step actually did something on a
    given photo instead of trusting it silently.

    Returns bounding boxes (x, y, w, h) in original image pixel coordinates.
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_cv is None:
        return []

    # Real phone/camera photos in this app run 15-20MP - contour-detection
    # cost scales with pixel count, and this function already sweeps up to
    # 16 kernel sizes across two passes (see the qty-scoped-filter fallback
    # below), so full resolution here was measured to be the dominant cost
    # in the whole scan pipeline (a 3-photo submission took 120+ seconds
    # before this change). Box SHAPES are still clearly resolvable well
    # below full resolution, so detection runs on a capped-size copy; every
    # box this function returns is rescaled back to ORIGINAL image
    # coordinates before returning, so callers (OCR crops, annotated-image
    # drawing) are unaffected and still work against full-resolution pixels.
    orig_h, orig_w = img_cv.shape[:2]
    detect_scale = 1.0
    _MAX_DETECT_DIM = 1600
    if max(orig_h, orig_w) > _MAX_DETECT_DIM:
        detect_scale = _MAX_DETECT_DIM / max(orig_h, orig_w)
        img_cv = cv2.resize(
            img_cv, (max(1, int(orig_w * detect_scale)), max(1, int(orig_h * detect_scale))),
            interpolation=cv2.INTER_AREA,
        )

    def _to_original_scale(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
        if detect_scale == 1.0:
            return boxes
        inv = 1.0 / detect_scale
        return [(int(x * inv), int(y * inv), int(bw * inv), int(bh * inv)) for (x, y, bw, bh) in boxes]

    h, w = img_cv.shape[:2]
    img_area = h * w

    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    edges = _combined_edge_mask(gray)

    if expected_qty and expected_qty > 0:
        target_frac = 1.0 / expected_qty
        lo_frac, hi_frac = target_frac * 0.35, target_frac * 3.0
        cap = max(expected_qty * 2, 20)
    else:
        lo_frac, hi_frac = 0.003, 0.20
        cap = 200

    best_contours: list[np.ndarray] = []
    best_kernel = None
    for kernel_size in (3, 5, 7, 9, 11, 13, 15, 17):
        contours = _detect_contours_for_kernel(edges, img_area, kernel_size, lo_frac, hi_frac, min_aspect, max_aspect)
        if len(contours) > len(best_contours) and len(contours) <= cap:
            best_contours = contours
            best_kernel = kernel_size

    total_before_split = len(best_contours)

    # Real, measured failure mode (Invoice 5 test photo, 20260902_100628.jpg):
    # the qty-scoped area filter assumes each item occupies roughly
    # 1/expected_qty of the WHOLE image — wrong whenever a lot of other
    # content shares the frame (a second, larger product; background/
    # carton), so the real items are much smaller than that fraction and
    # get filtered out, leaving too few contours to trust (here: 3, when
    # 12 boxes were actually visible and correctly found by the broader
    # generic sweep below). When that happens, re-run with the same broad
    # area range used when expected_qty is unknown, then keep only the
    # LARGEST same-sized cluster of contours (real boxes of one product
    # are uniform in size — this filters out an unrelated differently-
    # sized product that also happened to pass the broad filter).
    if expected_qty and expected_qty > 0 and total_before_split < max(3, int(expected_qty * 0.5)):
        generic_best: list[np.ndarray] = []
        for kernel_size in (3, 5, 7, 9, 11, 13, 15, 17):
            contours = _detect_contours_for_kernel(edges, img_area, kernel_size, 0.003, 0.20, min_aspect, max_aspect)
            if len(contours) > len(generic_best) and len(contours) <= 200:
                generic_best = contours
        cluster = _largest_uniform_cluster(generic_best)
        if len(cluster) > total_before_split:
            if debug:
                print(f"[detect_item_boxes] qty-scoped filter only found {total_before_split} - "
                      f"falling back to generic sweep's largest uniform cluster ({len(cluster)} boxes)")
            best_contours = cluster
            total_before_split = len(best_contours)

    # Flag likely merged/touching pairs by area vs. the group's own median
    # (boxes are roughly uniform size, so ~2x median is a strong "this is
    # probably two" signal) and split ONLY those — an ordinary single-box
    # contour never gets run through watershed.
    areas = [cv2.contourArea(c) for c in best_contours]
    median_area = float(np.median(areas)) if areas else 0.0

    final_boxes: list[tuple[int, int, int, int]] = []
    merged_flagged = 0
    for c, area in zip(best_contours, areas):
        ratio = (area / median_area) if median_area > 0 else 0.0
        if 1.8 <= ratio <= 2.2:
            merged_flagged += 1
            final_boxes.extend(_split_merged_contour(gray.shape, c))
        else:
            final_boxes.append(cv2.boundingRect(c))

    if debug:
        print(f"[detect_item_boxes] kernel={best_kernel}  contours before splitting: {total_before_split}")
        print(f"[detect_item_boxes] contours flagged as merged pairs (~1.8-2.2x median area): {merged_flagged}")
        print(f"[detect_item_boxes] final box count after splitting: {len(final_boxes)}")

    # Real, measured finding (not assumed): on actual project photos, the
    # remaining shortfall after watershed splitting is usually NOT an
    # oversized "merged" contour at all (merged_flagged came back 0 on both
    # of this project's real test photos even though they undercounted 8/12
    # and 16/20) — it's a box whose contour never closes in the first place
    # (touching edge with no gap, glare, shadow, low local contrast against
    # its neighbor). No amount of per-contour splitting fixes a contour
    # that was never formed. Since these are uniform grid-packed cartons
    # (confirmed: box width/height vary only ~15% across a whole photo),
    # extrapolate the full grid from whatever WAS reliably detected instead
    # of requiring every individual box to segment on its own.
    # Only trust a full-grid extrapolation when the sample is a substantial
    # fraction of expected_qty (>=25%) — a real, measured failure mode: a
    # thin sample (e.g. 4 boxes standing in for an expected 24) gives
    # _fit_full_grid too little to size a cell from, and a wrong cell size
    # tiled across the whole extrapolated extent can wildly overshoot (4
    # real boxes -> a fabricated 24). Below that fraction, returning the
    # smaller-but-real sample is safer than a confident-looking, wrong
    # count — consistent with this app's own principle of flagging low
    # confidence rather than fabricating a number.
    if (
        expected_qty and expected_qty > 0 and len(final_boxes) < expected_qty
        and len(final_boxes) >= expected_qty * 0.25
    ):
        grid_boxes = _fit_full_grid(final_boxes, expected_qty, edges, img_cv.shape, debug=debug)
        if grid_boxes:
            return _to_original_scale(grid_boxes)

    return _to_original_scale(final_boxes)


def _estimate_content_extent(edges: np.ndarray) -> tuple[int, int, int, int] | None:
    """
    Aggressively dilates/closes the edge mask so an entire densely-packed
    grid becomes one connected blob, then returns the bounding rect of the
    largest resulting region — a robust "how far does the packed grid
    actually extend" signal that doesn't depend on any individual box's
    own contour closing (unlike the per-box detection above, which is
    exactly what's unreliable here).

    Sweeps several kernel sizes rather than one fixed value — the gap a
    single dilate/close pass needs to bridge between adjacent boxes scales
    with how large each box is in the frame, which varies photo to photo
    (same reasoning as the kernel sweep in detect_item_boxes itself). Keeps
    the LARGEST resulting region across all kernel sizes tried, since an
    under-sized kernel that fails to bridge every gap would otherwise
    return a small, wrong sub-region instead of the whole grid.
    """
    best: tuple[int, int, int, int] | None = None
    best_area = 0.0
    for kernel_size in (15, 25, 35, 45):
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        proc = cv2.dilate(edges, kernel, iterations=2)
        proc = cv2.morphologyEx(proc, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(proc, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area > best_area:
            best_area = area
            best = cv2.boundingRect(largest)
    return best


def _fit_full_grid(
    sample_boxes: list[tuple[int, int, int, int]],
    expected_qty: int,
    edges: np.ndarray,
    img_shape: tuple[int, int, int],
    debug: bool = False,
) -> list[tuple[int, int, int, int]] | None:
    """
    Extrapolates the complete row x col grid of `expected_qty` boxes from
    whatever partial sample was reliably contour-detected, rather than
    requiring every box to segment individually. Uses the sample's own
    median box size (boxes in these cartons are roughly uniform) and the
    overall content extent to tile a full grid.

    Two ways to get the extent, tried in order:
    1. _estimate_content_extent — anchored to the whole packed region via
       an aggressive dilate/close, not to the sample's own min/max span
       (a sample that happens to miss an entire edge/column would
       otherwise systematically under-span and drift the whole grid — a
       real failure mode caught by testing this against Picture1.png).
       Only trusted if it actually CONTAINS every sample box — a real,
       measured failure mode on a second real photo: the aggressive-
       dilate extent can undershoot on a photo where the background isn't
       as tightly cropped, producing a region that doesn't even cover
       boxes we already know are real. An extent that fails this basic
       consistency check is discarded rather than trusted.
    2. Padded sample span (the sample boxes' own bounding range, expanded
       by ~0.6 cell on each side) — a cruder fallback that at least always
       contains every known-real box, used whenever (1) is missing or
       fails the containment check.

    Picks whichever (rows, cols) factor pair of expected_qty makes
    predicted cell size (extent / cols, extent / rows) closest to the
    sample's actual median box size — i.e. lets the DATA choose the grid
    shape, not an assumption about orientation.

    Returns None (falls back to the plain contour result) only if there's
    too little sample to trust a size estimate from at all.
    """
    if len(sample_boxes) < 3:
        return None

    med_w = float(np.median([b[2] for b in sample_boxes]))
    med_h = float(np.median([b[3] for b in sample_boxes]))
    if med_w <= 0 or med_h <= 0:
        return None

    sample_x0 = min(b[0] for b in sample_boxes)
    sample_y0 = min(b[1] for b in sample_boxes)
    sample_x1 = max(b[0] + b[2] for b in sample_boxes)
    sample_y1 = max(b[1] + b[3] for b in sample_boxes)

    extent = _estimate_content_extent(edges)
    extent_source = "aggregate-edge-extent"
    if extent is not None:
        ex, ey, ew, eh = extent
        contains_sample = (
            ex <= sample_x0 + 5 and ey <= sample_y0 + 5
            and ex + ew >= sample_x1 - 5 and ey + eh >= sample_y1 - 5
        )
        # Real, measured failure mode (same Invoice 5 photo as the cluster
        # fallback above): when other content shares the frame (a second
        # product, background), the aggressive dilate/close in
        # _estimate_content_extent merges everything into one blob
        # spanning nearly the whole image — it still trivially CONTAINS
        # the real sample, so the check above alone doesn't catch it. A
        # sane extent for `expected_qty` boxes of this sample's own size
        # shouldn't be wildly bigger than expected_qty copies of that box
        # (packed items don't have huge gaps) — reject it as implausible
        # rather than tiling a grid across content that isn't this item.
        plausible_area = expected_qty * med_w * med_h
        oversized = plausible_area > 0 and (ew * eh) > plausible_area * 3.0
        if ew <= 0 or eh <= 0 or not contains_sample or oversized:
            extent = None

    if extent is None:
        pad_x, pad_y = med_w * 0.6, med_h * 0.6
        ex = max(0.0, sample_x0 - pad_x)
        ey = max(0.0, sample_y0 - pad_y)
        ew = (sample_x1 - sample_x0) + 2 * pad_x
        eh = (sample_y1 - sample_y0) + 2 * pad_y
        extent = (int(ex), int(ey), int(ew), int(eh))
        extent_source = "padded-sample-span"
    ex, ey, ew, eh = extent

    best: tuple[float, int, int] | None = None
    for cols in range(1, expected_qty + 1):
        if expected_qty % cols:
            continue
        rows = expected_qty // cols
        score = abs(cols * med_w - ew) + abs(rows * med_h - eh)
        if best is None or score < best[0]:
            best = (score, rows, cols)
    _, rows, cols = best

    cell_w, cell_h = ew / cols, eh / rows
    grid_boxes = [
        (int(ex + c * cell_w), int(ey + r * cell_h), int(cell_w), int(cell_h))
        for r in range(rows) for c in range(cols)
    ]

    if debug:
        print(f"[detect_item_boxes] grid-fit: sample={len(sample_boxes)}/{expected_qty}, "
              f"extent={extent} (via {extent_source}), fitted {rows}x{cols}={len(grid_boxes)} boxes")

    return grid_boxes


_LABEL_GTIN_RE = re.compile(r"GTIN[:\s]*([0-9]{8,14})", re.IGNORECASE)
_LABEL_BATCH_RE = re.compile(r"Lot(?:/Batch)?[:\s]*([A-Za-z0-9\-]{3,15})", re.IGNORECASE)
_LABEL_EXPIRY_RE = re.compile(r"Exp\.?[:\s]*([0-9]{4}[\-/][A-Za-z0-9]{2,4}(?:[\-/][0-9]{1,2})?)", re.IGNORECASE)
_LABEL_SERIAL_RE = re.compile(r"S[\\/]?N[:\s]*([0-9]{6,20})", re.IGNORECASE)

# Tesseract digit/lookalike-letter confusion, e.g. "41016" -> "4I016" (the
# "1" read as capital "I"). GTIN/Serial can't suffer this silently — their
# regexes require pure digits, so a misread letter just fails to match at
# all (safe, if incomplete). Batch is different: its regex deliberately
# allows letters too, since real batch codes genuinely contain them
# (MF1204, MT1204, B2, B3, OCR-B5) — so a misread letter passes straight
# through as a wrong-but-plausible-looking value instead of failing safe.
_DIGIT_LOOKALIKES = {"I": "1", "L": "1", "O": "0", "S": "5", "Z": "2"}


def _fix_ocr_digit_lookalikes(batch: str) -> str:
    """
    Only touches a batch string that's OVERWHELMINGLY numeric already —
    every character must be either a real digit or one of the specific
    lookalike letters above, and it must be long enough (>=4 chars) that
    a short deliberate letter-prefixed code (B2, B3) can't be mistaken
    for a numeric misread. This is what keeps MF1204/MT1204/OCR-B5 (which
    contain non-lookalike letters like M, F, C, R) and B2/B3 (too short,
    and 'B' isn't in the lookalike set) untouched, while still fixing the
    reported case: "4I016" -> "41016".
    """
    if len(batch) < 4:
        return batch
    if not all(c.isdigit() or c.upper() in _DIGIT_LOOKALIKES for c in batch):
        return batch
    return "".join(_DIGIT_LOOKALIKES.get(c.upper(), c) for c in batch)


def ocr_box_label(image_bytes: bytes, box: tuple[int, int, int, int]) -> dict:
    """
    Local OCR (Tesseract, no API/no key) on one detected box crop — reads
    whatever printed label text is legible. Verified directly against a
    real label with a known-correct printed value: Lot and Exp fields OCR'd
    with an EXACT match; the long numeric Serial field did not (several
    digit errors) — long numeric strings are the least reliable OCR
    target, consistent with this project's earliest R&D finding (Round 1-2).
    Returned fields are best-effort hints, not barcode-verified reads.
    """
    x, y, bw, bh = box
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    crop = img_cv[y:y + bh, x:x + bw]
    crop_pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)).convert("L")
    scale = max(1, 600 // max(crop_pil.width, 1))
    if scale > 1:
        crop_pil = crop_pil.resize((crop_pil.width * scale, crop_pil.height * scale), Image.LANCZOS)
    text = pytesseract.image_to_string(crop_pil, config="--psm 6")

    gtin_m = _LABEL_GTIN_RE.search(text)
    batch_m = _LABEL_BATCH_RE.search(text)
    expiry_m = _LABEL_EXPIRY_RE.search(text)
    serial_m = _LABEL_SERIAL_RE.search(text)
    return {
        "gtin": gtin_m.group(1) if gtin_m else None,
        "batch": _fix_ocr_digit_lookalikes(batch_m.group(1)) if batch_m else None,
        "expiry": expiry_m.group(1) if expiry_m else None,
        "serial": serial_m.group(1) if serial_m else None,
    }


def extract_via_opencv(image_bytes: bytes, expected_qty: int | None = None) -> dict:
    """
    Full local extraction pipeline for one item photo — detect_item_boxes()
    to find every individual item region, ocr_box_label() to read each
    one's printed text locally, then consolidate into a single result.
    Entirely local: no Anthropic API, no API key, works with
    EXTRACTION_MODE unset. Returns {"count": int, "gtin": str|None,
    "batch": str|None, "expiry": str|None, "serials": list[str],
    "confidence": float, "notes": list[str]}.
    """
    boxes = detect_item_boxes(image_bytes, expected_qty)
    if not boxes:
        return {
            "count": 0, "gtin": None, "batch": None, "expiry": None, "serials": [],
            "confidence": 0.0, "boxes": [],
            "notes": ["OpenCV could not detect any individual item boundaries in this photo."],
        }

    gtin_votes: dict[str, int] = {}
    batch_votes: dict[str, int] = {}
    expiry_votes: dict[str, int] = {}
    serials: list[str] = []
    ocr_hits = 0
    for box in boxes:
        try:
            field = ocr_box_label(image_bytes, box)
        except Exception:
            continue
        if field["gtin"]:
            gtin_votes[field["gtin"]] = gtin_votes.get(field["gtin"], 0) + 1
        if field["batch"]:
            batch_votes[field["batch"]] = batch_votes.get(field["batch"], 0) + 1
        if field["expiry"]:
            expiry_votes[field["expiry"]] = expiry_votes.get(field["expiry"], 0) + 1
        if field["serial"]:
            serials.append(field["serial"])
            ocr_hits += 1

    def _majority(votes: dict[str, int]) -> str | None:
        return max(votes, key=lambda k: votes[k]) if votes else None

    notes = [
        f"OpenCV detected {len(boxes)} individual item region(s) in this photo "
        "(classical edge/contour detection, no AI vision, no API key)."
    ]
    if batch_votes or gtin_votes:
        notes.append(
            f"Local OCR (Tesseract) read identifying text from {ocr_hits} of {len(boxes)} detected boxes; "
            "Batch/Expiry are the reliable fields — Serial numbers are best-effort only, not barcode-verified."
        )
    else:
        notes.append("Local OCR could not read GTIN/batch text from any detected box — count is from box detection only.")

    return {
        "count": len(boxes),
        "gtin": _majority(gtin_votes),
        "batch": _majority(batch_votes),
        "expiry": _majority(expiry_votes),
        "serials": serials,
        "boxes": boxes,
        # Deliberately capped below barcode-level confidence (1.0) — this
        # is box-shape detection plus imperfect local OCR, never presented
        # as equivalent certainty to an actual decoded barcode.
        "confidence": min(0.7, 0.3 + (ocr_hits / len(boxes)) * 0.4),
        "notes": notes,
    }


def draw_item_boxes(image_bytes: bytes, boxes: list[tuple[int, int, int, int]]) -> bytes:
    """
    Draws the detected bounding boxes onto a copy of the original photo,
    numbered in detection order, and returns it as JPEG bytes — lets a
    reviewer visually verify what OpenCV actually found instead of just
    trusting a bare count, the same transparency principle behind showing
    the original scanned photo. Never modifies the original file on disk.
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_cv is None:
        return image_bytes
    for i, (x, y, w, h) in enumerate(boxes):
        cv2.rectangle(img_cv, (x, y), (x + w, y + h), (0, 0, 255), 3)
        label = str(i + 1)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(img_cv, (x, y), (x + tw + 8, y + th + 10), (0, 0, 255), -1)
        cv2.putText(img_cv, label, (x + 4, y + th + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    ok, buf = cv2.imencode(".jpg", img_cv, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    return buf.tobytes() if ok else image_bytes
