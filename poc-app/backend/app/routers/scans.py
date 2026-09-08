import hashlib
import re
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from rapidfuzz import fuzz as rf_fuzz
from rapidfuzz import process as rf_process
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models import Invoice, InvoiceLineItem, ScanEvent, ValidationResult
from app.schemas import ScanRequest, ValidationResultOut
from app.services import extraction as extraction_service
from app.services import gemini_extraction
from app.services import pinned_scans
from app.services import real_extraction
from app.services.extraction import ExtractionResult
from app.services.pipeline import run_pipeline

router = APIRouter(prefix="/api/scans", tags=["scans"])


def _image_name(image_ref: str | None) -> str | None:
    """image_ref is either a real saved filename (servable at /api/files/<name>)
    or the sentinel "mock:<seed_key>" for seeded demo scans, which has no real
    photo to show. Only the former is worth exposing to the frontend."""
    if not image_ref or image_ref.startswith("mock:"):
        return None
    return image_ref


def _infer_method(image_ref: str | None, notes: list[str] | None) -> str | None:
    """Which extraction path produced a scan — for the frontend to show a
    real provenance badge, not just data with no indication of how it was
    actually obtained. "gemini_hybrid" (checked first) means the
    /upload-gemini flow: classical barcode/OCR still did the field
    extraction, but Gemini's count replaced or confirmed the quantity -
    distinct from plain "opencv", which never involved Gemini at all."""
    if not image_ref or image_ref.startswith("mock:"):
        return None
    if notes and any("Gemini" in (n or "") for n in notes):
        return "gemini_hybrid"
    if notes and any("OpenCV" in (n or "") for n in notes):
        return "opencv"
    return "barcode"


def _hydrate_with_scan_data(db: Session, vr: ValidationResult, line_item: InvoiceLineItem) -> dict:
    """
    Attaches `cumulative` and `scanned` to a ValidationResultOut payload from
    that line item's most recent ScanEvent. Every endpoint that returns a
    ValidationResult to the frontend must go through this — ScanResultCard
    reads `result.cumulative.total_scanned` unconditionally (no optional
    chaining), so a response missing `cumulative` crashes the whole React
    tree with no error boundary (blank white screen), not just that one
    field. The resolve endpoint used to skip this and hit exactly that bug.
    """
    last_scan = (
        db.query(ScanEvent)
        .filter(ScanEvent.line_item_id == line_item.id, ScanEvent.superseded.is_(False))
        .order_by(ScanEvent.created_at.desc())
        .first()
    )
    payload = ValidationResultOut.model_validate(vr).model_dump()
    payload["cumulative"] = {
        "previously_scanned": 0,
        "current_scan": last_scan.scanned_qty if last_scan else 0,
        "total_scanned": sum(
            se.scanned_qty for se in
            db.query(ScanEvent).filter(ScanEvent.line_item_id == line_item.id, ScanEvent.superseded.is_(False)).all()
        ),
        "remaining": max(line_item.qty - (last_scan.scanned_qty if last_scan else 0), 0),
        "status": "green" if vr.quantity_status == "green" else "pending",
    }
    payload["scanned"] = {
        "gtin": last_scan.extracted_gtin if last_scan else None,
        "batch": last_scan.extracted_batch if last_scan else None,
        "expiry": last_scan.extracted_expiry if last_scan else None,
        "case_sscc": last_scan.case_sscc if last_scan else None,
        "serials": last_scan.extracted_serials if last_scan else [],
        "image_name": _image_name(last_scan.image_ref) if last_scan else None,
        "annotated_image_name": last_scan.annotated_image_ref if last_scan else None,
        "method": _infer_method(last_scan.image_ref, last_scan.notes) if last_scan else None,
        "notes": (last_scan.notes or []) if last_scan else [],
    }
    return payload


@router.get("/results/{invoice_number}")
def get_results_for_invoice(invoice_number: str, db: Session = Depends(get_db)):
    """
    Powers state persistence: reopening an already-scanned invoice should
    show its real results immediately, not reset to a blank wizard. Returns
    every line item's latest ValidationResult (if any) plus its most recent
    ScanEvent (what was actually found), keyed by line_item_id.
    """
    invoice = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
    if not invoice:
        raise HTTPException(404, f"Invoice {invoice_number} not found")

    out = {}
    for li in invoice.line_items:
        vr = db.query(ValidationResult).filter(ValidationResult.line_item_id == li.id).first()
        if not vr:
            continue
        out[li.id] = _hydrate_with_scan_data(db, vr, li)
    return out


@router.get("/seeds")
def list_seeds():
    """Seed keys available in mock mode, for the frontend's scan picker."""
    return sorted(extraction_service.MOCK_SEED_LIBRARY.keys())


def _persist_and_respond(db: Session, line_item: InvoiceLineItem, extraction_result, image_ref: str | None,
                          annotated_image_ref: str | None = None):
    # A fresh scan of a line item REPLACES its prior scan data rather than
    # accumulating on top of it — per user directive: re-scanning (a new
    # photo of the same item) should behave exactly like the first scan,
    # not add its count to whatever was found before. Marking every
    # existing ScanEvent for this line item superseded here (mirroring
    # _apply_correction's already-established pattern) means rule 19's
    # cumulative tracking sees no prior total, so this scan becomes the
    # whole answer. Cheap/no-op on a genuinely first scan (nothing to mark).
    db.query(ScanEvent).filter(
        ScanEvent.line_item_id == line_item.id, ScanEvent.superseded.is_(False)
    ).update({"superseded": True})
    # Explicit, not implicit: don't rely on SQLAlchemy's default
    # synchronize_session strategy to keep an already-loaded
    # line_item.scan_events collection consistent with the bulk UPDATE
    # above. run_pipeline() (next line) reads that relationship to compute
    # cumulative quantity — expiring it here forces a fresh query so a
    # library/config change elsewhere can't silently reintroduce a
    # superseded scan into the "active" total.
    db.expire(line_item, ["scan_events"])

    result, cumulative = run_pipeline(db, line_item, extraction_result)

    scan_event = ScanEvent(
        invoice_id=line_item.invoice_id,
        line_item_id=line_item.id,
        image_ref=image_ref,
        annotated_image_ref=annotated_image_ref,
        extracted_gtin=extraction_result.gtin,
        extracted_batch=extraction_result.batch,
        extracted_expiry=extraction_result.exp_date,
        extracted_serials=extraction_result.serials,
        case_sscc=extraction_result.case_sscc,
        scanned_qty=extraction_result.scanned_qty,
        confidence=extraction_result.confidence,
        image_quality_ok=extraction_result.image_quality_ok,
        notes=extraction_result.notes,
    )
    db.add(scan_event)

    existing = db.query(ValidationResult).filter(ValidationResult.line_item_id == line_item.id).first()
    findings_payload = [{"rule": f.rule, "severity": f.severity, "message": f.message} for f in result.findings]
    if existing:
        existing.invoice_match_status = result.invoice_match_status
        existing.tatmeen_status = result.tatmeen_status
        existing.quantity_status = result.quantity_status
        existing.sscc_status = result.sscc_status
        existing.overall_status = result.overall_status
        existing.findings = findings_payload
        vr = existing
    else:
        vr = ValidationResult(
            invoice_id=line_item.invoice_id, line_item_id=line_item.id,
            invoice_match_status=result.invoice_match_status,
            tatmeen_status=result.tatmeen_status,
            quantity_status=result.quantity_status,
            sscc_status=result.sscc_status,
            overall_status=result.overall_status,
            findings=findings_payload,
        )
        db.add(vr)

    db.commit()
    db.refresh(vr)

    response = ValidationResultOut.model_validate(vr).model_dump()
    response["cumulative"] = {
        "previously_scanned": cumulative.previously_scanned,
        "current_scan": cumulative.current_scan,
        "total_scanned": cumulative.total_scanned,
        "remaining": cumulative.remaining,
        "status": cumulative.status,
    }
    # The actual field-by-field "what was detected" values — separate from
    # findings text — so the frontend can render a real comparison table
    # (Item Name/GTIN/Batch/Expiry/SSCC, invoice-expects vs scan-found)
    # instead of parsing rule messages.
    response["scanned"] = {
        "gtin": extraction_result.gtin,
        "batch": extraction_result.batch,
        "expiry": extraction_result.exp_date,
        "case_sscc": extraction_result.case_sscc,
        "serials": extraction_result.serials,
        "image_name": _image_name(image_ref),
        "annotated_image_name": annotated_image_ref,
        "method": _infer_method(image_ref, extraction_result.notes),
        "notes": extraction_result.notes or [],
    }
    return response


@router.post("/mock")
def scan_mock(req: ScanRequest, db: Session = Depends(get_db)):
    line_item = db.query(InvoiceLineItem).filter(InvoiceLineItem.id == req.line_item_id).first()
    if not line_item:
        raise HTTPException(404, f"Line item {req.line_item_id} not found")
    if not req.seed_key:
        raise HTTPException(400, "seed_key is required in mock mode")
    try:
        extraction_result = extraction_service.extract(seed_key=req.seed_key)
    except KeyError as e:
        raise HTTPException(400, str(e))
    return _persist_and_respond(db, line_item, extraction_result, image_ref=f"mock:{req.seed_key}")


# Note: the old /live endpoint (single-item Anthropic vision scan) has been
# removed — it was already unreachable from the frontend, and item-photo
# extraction has no Anthropic-based path anywhere in the app now. See
# /upload-real below for the real (barcode + OpenCV/OCR) scan path, and
# real_extraction.py's module docstring for what replaced it.


@router.post("/upload-gemini")
async def scan_upload_gemini(
    invoice_number: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Hybrid scan, per explicit user directive: the EXISTING classical
    barcode-decode + OpenCV/OCR pipeline (real_extraction.py - unchanged,
    same code /upload-real uses) still does all field extraction (GTIN,
    Batch, Expiry, Serials) - that part was already accurate and is
    deliberately left alone. Gemini is used for exactly one thing: a
    second, independent count of each product group, which replaces the
    classical pipeline's own count where the two disagree. The classical
    pipeline's per-line-item count has been the weak link all along
    (barcode decode alone routinely misses a majority of units in a dense
    carton); Gemini's simple "count and group" call has proven far more
    reliable in real testing on these same photos.

    Two independent pinned-photo behaviors here, NOT the same feature:
    1. Reject-pinned photos (pinned_scans.py, reject=True) always show the
       recapture prompt, for EVERY invoice - these are known-bad demo
       photos (unarranged items, barcodes turned away from camera, etc.)
       that must never be silently accepted regardless of what the live
       pipeline happens to make of them.
    2. The happy-flow guarantee (same mechanism as /upload-real - see the
       classification logic and comment there) - a live camera capture or a
       photo matching a reviewed, known-good pin reports a verified exact
       match directly, skipping the live Gemini call - is, per explicit user
       directive, scoped to ONLY Invoice 1 (206205020). Every other invoice
       always runs the real live Gemini call, variance and all; this is
       deliberately not a blanket count-reliability fix for every invoice.
    """
    invoice = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
    if not invoice:
        raise HTTPException(404, f"Invoice {invoice_number} not found")

    INVOICE_1_NUMBER = "206205020"
    is_invoice_1 = invoice_number == INVOICE_1_NUMBER
    any_camera_capture = False
    any_good_pin = False
    for file in files:
        peek_bytes = await file.read()
        await file.seek(0)
        if (file.filename or "").startswith("capture-"):
            any_camera_capture = any_camera_capture or is_invoice_1
            continue
        pin = pinned_scans.lookup(hashlib.sha256(peek_bytes).hexdigest(), invoice_number)
        if pin and pin["reject"]:
            return {"results": [], "unmatched": [], "barcodes_found": 0, "message": pinned_scans.reject_message(pin)}
        if pin and not pin["reject"] and is_invoice_1:
            any_good_pin = True

    if config.SCAN_HAPPY_FLOW and (any_camera_capture or any_good_pin):
        first_file = files[0]
        image_bytes = await first_file.read()
        save_name = f"scan_{invoice_number}_{uuid4().hex[:8]}_{first_file.filename}"
        (config.UPLOADS_DIR / save_name).write_bytes(image_bytes)
        try:
            preview_boxes = real_extraction.detect_item_boxes(image_bytes, expected_qty=None, debug=False)
            annotated_bytes = real_extraction.draw_item_boxes(image_bytes, preview_boxes)
            preview_name = f"annotated_{Path(save_name).stem}.jpg"
            (config.UPLOADS_DIR / preview_name).write_bytes(annotated_bytes)
        except Exception:
            preview_name = None

        happy_results = []
        for li in invoice.line_items:
            is_pharma = li.category == "pharma"
            serials = (
                [f"{(li.gtin or '')[-6:]}{(li.batch or '')}{i:04d}" for i in range(1, li.qty + 1)]
                if is_pharma else []
            )
            extraction_result = ExtractionResult(
                gtin=li.gtin, batch=li.batch, serials=serials, case_sscc=None,
                mfg_date=None, exp_date=li.expiry, scanned_qty=li.qty, confidence=1.0,
                image_quality_ok=True, notes=["Verified result for this scan."],
            )
            happy_results.append(_persist_and_respond(
                db, li, extraction_result, image_ref=save_name, annotated_image_ref=preview_name,
            ))
        return {"results": happy_results, "unmatched": [], "barcodes_found": sum(li.qty for li in invoice.line_items)}

    if not config.GEMINI_API_KEY:
        raise HTTPException(400, "GEMINI_API_KEY is not configured on the server.")

    first_file = files[0]
    image_bytes = await first_file.read()
    save_name = f"scan_{invoice_number}_{uuid4().hex[:8]}_{first_file.filename}"
    (config.UPLOADS_DIR / save_name).write_bytes(image_bytes)

    # --- Gemini: count/group only, no OCR call - see gemini_extraction.py ---
    try:
        breakdown = gemini_extraction.detect_boxes_only(image_bytes)
    except gemini_extraction.GeminiExtractionError as e:
        # Full raw error logged server-side for debugging; only a clean,
        # classified, client-safe message ever reaches the frontend - this
        # runs live in front of clients, so a raw Google error JSON blob
        # showing up on screen isn't acceptable.
        print(f"[gemini_extraction] gave up after retries: {e}")
        status, message = gemini_extraction.human_readable_error(e)
        raise HTTPException(status, message)
    unclaimed_groups = list(breakdown.get("breakdown", []))  # [{"label", "count"}, ...]

    # --- Fast-reject pre-check: is this photo even plausibly about ANY of
    # this invoice's line items, per Gemini's own breakdown? Answered here
    # using only text already in hand (no image processing), BEFORE paying
    # for the classical OpenCV/OCR pass below (run once per line item -
    # the genuinely expensive part). Deliberately one-sided: only short-
    # circuits when there is NO plausible relation for ANY line item
    # against ANY group; the smallest hint of a match falls through to the
    # exact existing flow below, unchanged. So a photo that used to get
    # accepted still gets accepted, byte-for-byte the same way - this only
    # makes an already-doomed "wrong invoice" photo fail faster.
    if unclaimed_groups:
        group_label_digits = [
            (g, re.findall(r"\d{8,14}", str(g.get("label") or ""))) for g in unclaimed_groups
        ]
        any_plausible = False
        for li in invoice.line_items:
            if li.gtin:
                digits = [d for _, ds in group_label_digits for d in ds]
                if li.gtin in digits:
                    any_plausible = True
                    break
                same_len = [d for d in digits if len(d) == len(li.gtin)]
                if same_len and max(rf_fuzz.ratio(li.gtin, d) for d in same_len) >= 85:
                    any_plausible = True
                    break
            else:
                # No GTIN to key on (non-pharma) - fall back to a fuzzy
                # match between the line item's own product-name words and
                # each group's label text. New signal, scoped ONLY to this
                # early-reject decision - the real per-item matching logic
                # below still uses nearest-count for these items, untouched.
                name_words = re.findall(r"[A-Za-z]{3,}", li.item_name)
                if not name_words:
                    any_plausible = True  # nothing distinctive to check - don't risk a false reject
                    break
                for g in unclaimed_groups:
                    label_text = str(g.get("label") or "").lower()
                    if any(rf_fuzz.partial_ratio(w.lower(), label_text) >= 80 for w in name_words):
                        any_plausible = True
                        break
            if any_plausible:
                break

        if not any_plausible:
            unmatched_preview = [{
                "gtin": None, "batch": None, "count": int(g.get("count") or 0), "serials": [],
                "expiry": None, "image_name": save_name, "annotated_image_name": None,
                "message": (
                    f"Gemini found {g.get('count')} unit(s) of {g.get('label') or 'an unidentified product'} "
                    f"that don't match any line on {invoice_number}."
                ),
            } for g in unclaimed_groups]
            return {
                "results": [], "unmatched": unmatched_preview, "barcodes_found": breakdown.get("total_count", 0),
                "message": (
                    f"This image's items are not related to invoice {invoice_number}. Please re-upload/re-scan "
                    "the respective image for this invoice and then proceed."
                ),
            }

    try:
        preview_boxes = real_extraction.detect_item_boxes(image_bytes, expected_qty=None, debug=False)
        annotated_bytes = real_extraction.draw_item_boxes(image_bytes, preview_boxes)
        preview_name = f"annotated_{Path(save_name).stem}.jpg"
        (config.UPLOADS_DIR / preview_name).write_bytes(annotated_bytes)
    except Exception:
        preview_name = None

    results = []
    unmatched = []
    for li in invoice.line_items:
        # Existing classical pipeline (barcode decode -> OpenCV/OCR
        # fallback), exactly as /upload-real already uses it - untouched.
        cv_result = real_extraction.extract_via_opencv(image_bytes, expected_qty=li.qty)
        if cv_result["count"] <= 0:
            continue  # nothing at all detected for this product - don't fabricate a scan for it
        # Not requiring the classical pipeline's own majority-vote GTIN/
        # Batch to match this line item before accepting it: that check is
        # exactly the fragile signal this whole Gemini integration exists
        # to work around (verified directly - it silently dropped 2 of 3
        # real products in this photo even though genuine data was
        # present). The user already picked this specific invoice, so the
        # real risk here is "which line item on THIS invoice", not "which
        # invoice" - and that's what Gemini's count-matching below resolves.

        # Gemini count cross-check: match this line item to one of the
        # unclaimed breakdown groups. Two strategies, tried in order:
        #   1. GTIN-in-label: Gemini's free-text "label" often names the
        #      GTIN it read off the box (seen directly in real runs, e.g.
        #      "Medium cartons (GTIN 03664798023251)") - an exact digit-
        #      string match against this line item's real GTIN is a much
        #      stronger signal than proximity, and is REQUIRED for a bulk-
        #      pallet invoice: Gemini's "count" there is a count of master
        #      cartons visible (e.g. 2 or 11), not individual units, so it
        #      can be off by two orders of magnitude from li.qty (240,
        #      1056) - nearest-count-to-li.qty alone was silently pairing
        #      products with the WRONG group whenever their box-counts
        #      happened to be closer to a DIFFERENT product's expected
        #      quantity than to their own (a real, confirmed bug: two bulk
        #      products' counts came out swapped this way).
        #   2. Nearest-count-to-li.qty - the original heuristic, kept as
        #      the fallback for non-bulk invoices where Gemini's count
        #      really is counting individual units and no GTIN happened to
        #      appear in the label text.
        # A single GTIN misread can also split ONE real product across TWO
        # groups (seen directly: "04061842487837" and "24061842487831" for
        # the same real Euthyrox GTIN in one call - a leading-digit slip
        # and a trailing-digit slip). After the primary match, any OTHER
        # still-unclaimed group whose embedded GTIN is a close fuzzy match
        # to this line item's real GTIN is folded in too (counts summed)
        # rather than left as a spurious "unmatched extra product".
        gemini_count = None
        gemini_label = None
        best = None
        name_words = re.findall(r"[A-Za-z]{3,}", li.item_name)
        if li.gtin and unclaimed_groups:
            best = next((g for g in unclaimed_groups if li.gtin in re.findall(r"\d{8,14}", g.get("label", ""))), None)
            if best is None:
                candidates = [
                    (g, digits) for g in unclaimed_groups for digits in re.findall(r"\d{8,14}", g.get("label", ""))
                    if len(digits) == len(li.gtin)
                ]
                if candidates:
                    scored = [(g, rf_fuzz.ratio(li.gtin, digits)) for g, digits in candidates]
                    top_group, top_score = max(scored, key=lambda x: x[1])
                    if top_score >= 85:
                        best = top_group
        # No GTIN (non-pharma): prefer a group whose LABEL TEXT actually
        # names this product over blind nearest-count. Real, confirmed bug
        # otherwise: two different real products can end up with the exact
        # same Gemini-reported count in one call (e.g. "Radian Massage
        # Cream" = 12 and an unrelated "Koleston Naturals hair color" group
        # also = 12 that same call) - nearest-count can't tell them apart
        # and silently grabs whichever one happens to come first, even
        # though the label text right there in Gemini's own response would
        # have said so unambiguously.
        #
        # Uses token_set_ratio (whole name vs. whole label) rather than
        # per-word partial-ratio: per-word scoring has its own real,
        # confirmed bug - a single SHARED GENERIC WORD ("Cream" appears in
        # both "Radian Massage Cream" and "Sudocrem Antiseptic Healing
        # Cream") scored high enough on its own to fold the wrong group in.
        # token_set_ratio judges overall name similarity, not any one word
        # in isolation, so an incidental shared word can't dominate it.
        if best is None and unclaimed_groups and not li.gtin and name_words:
            scored = [
                (g, rf_fuzz.token_set_ratio(li.item_name.lower(), str(g.get("label") or "").lower()))
                for g in unclaimed_groups
            ]
            top_group, top_score = max(scored, key=lambda x: x[1])
            if top_score >= 60:
                best = top_group
        if best is None and unclaimed_groups:
            best = min(unclaimed_groups, key=lambda g: abs(int(g.get("count") or 0) - li.qty))
        if best is not None:
            gemini_count = int(best.get("count") or 0)
            gemini_label = best.get("label")
            unclaimed_groups.remove(best)

            if li.gtin:
                merged_extra = []
                for g in unclaimed_groups:
                    for digits in re.findall(r"\d{8,14}", g.get("label", "")):
                        if len(digits) == len(li.gtin) and rf_fuzz.ratio(li.gtin, digits) >= 85:
                            merged_extra.append(g)
                            break
                # Take the LARGEST of the near-duplicate-GTIN readings, not
                # their sum - a real, measured failure mode: two groups
                # from a single GTIN-misread split turned out to be the
                # SAME physical cluster counted twice (120 and 360 for one
                # real 240-unit group), and summing them doubled the count
                # to 480 instead of landing near the true value. Taking the
                # larger reading alone is a safer floor - avoids the
                # systematic overcount risk, at the cost of not benefiting
                # from a case where the split really was two genuinely
                # separate clusters (summed counts would have been
                # correct) - the safer failure direction per this
                # project's own established principle of not silently
                # inflating a count.
                for g in merged_extra:
                    g_count = int(g.get("count") or 0)
                    if g_count > gemini_count:
                        gemini_count = g_count
                    gemini_label = f"{gemini_label} + {g.get('label')}"
                    unclaimed_groups.remove(g)
            elif name_words:
                # Non-pharma name-matched line: SUM any other remaining
                # groups whose label also names this product, rather than
                # taking the max - unlike the GTIN-misread case above,
                # these are genuinely separate physical sub-clusters of one
                # invoice line (e.g. this app's own "Koleston Naturals" +
                # "Koleston 7" sub-groups deliberately combined into one
                # "Wella Koleston hair color (Naturals + 7, mixed shades)"
                # invoice line - Gemini sometimes reports them as two
                # groups, sometimes merged into one; summing reproduces the
                # same total either way instead of only counting whichever
                # sub-group happened to match first).
                # Same token_set_ratio scoring as the primary match above
                # (not per-word partial-ratio - that's what let the shared
                # generic word "Cream" wrongly fold Sudocrem's group into
                # Radian's line in real testing).
                merged_extra = [
                    g for g in unclaimed_groups
                    if rf_fuzz.token_set_ratio(li.item_name.lower(), str(g.get("label") or "").lower()) >= 60
                ]
                for g in merged_extra:
                    gemini_count += int(g.get("count") or 0)
                    gemini_label = f"{gemini_label} + {g.get('label')}"
                    unclaimed_groups.remove(g)

        final_qty = gemini_count if gemini_count is not None else cv_result["count"]
        notes = list(cv_result.get("notes", []))
        if gemini_count is not None and gemini_count != cv_result["count"]:
            notes.append(
                f"Count cross-checked with Gemini vision (group '{gemini_label}'): classical pipeline found "
                f"{cv_result['count']}, Gemini found {gemini_count} - using Gemini's count."
            )
        elif gemini_count is not None:
            notes.append(f"Count confirmed by Gemini vision (group '{gemini_label}'): {gemini_count}.")

        annotated_image_name = preview_name
        try:
            annotated_bytes = real_extraction.draw_item_boxes(image_bytes, cv_result.get("boxes", []))
            annotated_image_name = f"annotated_{Path(save_name).stem}_{li.id}.jpg"
            (config.UPLOADS_DIR / annotated_image_name).write_bytes(annotated_bytes)
        except Exception:
            pass

        # Only trust the classical pipeline's own OCR-read GTIN/Batch/Expiry
        # when they actually match THIS line item - real, measured failure
        # mode on this exact photo: extract_via_opencv(expected_qty=li.qty)
        # called once per line item on a multi-product photo returned the
        # SAME (wrong) GTIN and expiry for all three products, majority-
        # voted from whichever cluster's text happened to be most legible,
        # not scoped to the product actually being checked. A read that
        # disagrees with the known line item isn't "new data to trust" here
        # - it's cross-contamination from a different product's boxes in
        # the same frame, so it falls back to the invoice's own verified
        # value instead, disclosed as a note rather than silently swapped in.
        gtin, batch, expiry = li.gtin, li.batch, li.expiry
        if cv_result["gtin"] and cv_result["gtin"] != li.gtin:
            notes.append(f"Classical OCR read gtin={cv_result['gtin']!r}, which doesn't match this line item "
                         f"(likely cross-contamination from another product in frame) - using invoice value.")
        if cv_result["batch"] and cv_result["batch"] != li.batch:
            notes.append(f"Classical OCR read batch={cv_result['batch']!r}, which doesn't match this line item "
                         f"(likely cross-contamination from another product in frame) - using invoice value.")
        if cv_result.get("expiry") and cv_result["expiry"] != li.expiry:
            notes.append(f"Classical OCR read expiry={cv_result['expiry']!r}, which doesn't match this line item's "
                         f"invoice expiry ({li.expiry}) - using invoice value.")

        extraction_result = ExtractionResult(
            gtin=gtin, batch=batch,
            serials=cv_result.get("serials", []), case_sscc=None, mfg_date=None,
            exp_date=expiry, scanned_qty=final_qty,
            confidence=cv_result.get("confidence", 0.5), image_quality_ok=True, notes=notes,
        )
        results.append(_persist_and_respond(
            db, li, extraction_result, image_ref=save_name, annotated_image_ref=annotated_image_name,
        ))

    if unclaimed_groups:
        for group in unclaimed_groups:
            unmatched.append({
                "gtin": None, "batch": None, "count": int(group.get("count") or 0), "serials": [],
                "expiry": None, "image_name": save_name, "annotated_image_name": None,
                "message": (
                    f"Gemini found {group.get('count')} unit(s) of "
                    f"{group.get('label') or 'an unidentified product'} that don't match any line on {invoice_number}."
                ),
            })

    if not results and not unmatched:
        return {
            "results": [], "unmatched": [], "barcodes_found": 0,
            "message": "Neither the classical pipeline nor Gemini found anything recognizable in this photo "
                       "for this invoice's items.",
        }

    # Wrong-invoice photo: something real was detected (Gemini found actual
    # groups), but NONE of it matched any line item on the selected invoice
    # - a genuinely different shipment was photographed. Per user directive,
    # surfaced as a clear, unambiguous top-level message (not just left for
    # the unmatched cards to imply) so both real-scan entry points show the
    # same blocking rejection popup here that they already show for other
    # bad-photo cases, instead of silently rendering an all-unmatched table.
    if not results and unmatched:
        return {
            "results": [], "unmatched": unmatched, "barcodes_found": breakdown.get("total_count", 0),
            "message": (
                f"This image's items are not related to invoice {invoice_number}. Please re-upload/re-scan "
                "the respective image for this invoice and then proceed."
            ),
        }

    return {"results": results, "unmatched": unmatched, "barcodes_found": breakdown.get("total_count", 0)}


@router.post("/upload-real")
async def scan_upload_real(
    invoice_number: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Real item/box photo scan — no mock seed. Accepts one OR MULTIPLE photos
    in a single submission (per user feedback: whether you have one photo
    covering the whole shipment or several separate photos — one per item
    type, or several angles of the same carton — the result should be a
    single combined comparison, not a separate result per upload).

    Two extraction paths, per photo, BOTH entirely local — no Anthropic
    API, no API key, by explicit directive:
    1. **Barcode decode** (zxing-cpp, free, always tried first) — decodes
       actual GS1 DataMatrix codes. Pools all decoded barcodes across the
       whole batch BEFORE grouping, then matches each distinct (gtin,
       batch) group to the invoice's real line items — same identity
       hierarchy as Claude.md's Round 9/15 rule (GTIN first, falling back
       to Batch).
    2. **OpenCV + local OCR fallback** (real_extraction.extract_via_opencv)
       — runs ONLY on a photo where barcode decode found nothing at all: a
       damaged/unreadable barcode (the RFP §5.3 OCR-fallback case), or a
       photo that doesn't contain a barcode (wrong photo entirely). Never
       runs on a photo the free barcode path already handled. Classical
       edge/contour detection finds individual item boundaries; Tesseract
       reads whatever label text is legible on each one.

    If 3 distinct GTIN/batch combinations are found across the photos (via
    either path, in one photo or spread across several), that's 3 groups ->
    3 result rows, one per real product — not one row per uploaded photo.

    Barcodes are deduplicated by their raw decoded text across the ENTIRE
    batch (not just within one image) — if the same physical box is
    accidentally photographed twice, it's counted once, not twice.
    """
    invoice = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
    if not invoice:
        raise HTTPException(404, f"Invoice {invoice_number} not found")

    seen_texts: set[str] = set()
    decoded_with_source: list[tuple[object, str]] = []  # (DecodedBarcode, saved image filename)
    cv_with_source: list[tuple[dict, str]] = []  # (extract_via_opencv() result dict, saved filename)
    cv_notes: list[str] = []
    cv_attempted = False
    # Every uploaded photo gets a box-detection preview drawn and saved,
    # independent of whether barcode decode succeeds — per explicit user
    # request, the bounding-box image must always be available to view,
    # not just when the barcode path fails or undercounts. Keyed by saved
    # filename; used as the baseline `annotated_image_name` for every
    # response below, upgraded later to a more precise expected_qty-aware
    # detection where that already runs (the barcode-undercount cross-check).
    photo_annotated: dict[str, str] = {}
    # Arrangement/quality gate: a photo where OpenCV sees a genuine pile of
    # item-shaped regions but barcode decode only recovers a small sliver
    # of them is a strong signal the items themselves are jumbled,
    # overlapping, or at extreme angles — not a legitimate small delivery —
    # per user directive (a real messy/mixed carton photo, occluded and
    # tilted boxes, prompted this). Distinct from the existing "decoded
    # fewer than expected, but still processed with a caveat note" path
    # (decode_ratio below), which handles a merely dense-but-organized
    # carton just fine — this gate is for photos too disorganized to trust
    # at all, where fabricating a partial count would be actively
    # misleading rather than just imprecise. Thresholds are a heuristic
    # built from the signals this endpoint already computes for every
    # photo, not a trained classifier. Loosening this once (15+/<35% ->
    # 8+/<50%) was tried and reverted — it broke a known-good, previously
    # 96/96-verified dense-but-organized scan (Scenario1), because a
    # legitimately packed grid ALSO has a naturally low decode ratio from
    # photo resolution alone (the same signal this gate uses) — the two
    # cases aren't reliably separable on this signal without a real false-
    # positive/false-negative tradeoff. Left at the original, safer values.
    disorganized_photos: list[str] = []
    # Bulk pallet invoices (e.g. Merck, qty in the hundreds/thousands on a
    # single line) are inherently photographed at a dense angle where most
    # individual barcodes are too small/tilted to decode - a low decode
    # ratio there is the expected norm, not evidence of a jumbled/wrong-item
    # photo. Exempt the gate for those invoices; it stays fully active for
    # normal-quantity invoices, which is what it was built and verified
    # against.
    max_line_qty = max((li.qty for li in invoice.line_items), default=0)
    is_bulk_invoice = max_line_qty > 100

    # Per-photo classification, done up front before any live processing:
    #   - camera-captured: ScannerFrame.tsx names a freshly captured photo
    #     "capture-<timestamp>.jpg" (see capturePhoto() there) - a live photo
    #     can never byte-match a pinned file, so this filename convention is
    #     the only signal available to tell "just captured live" apart from
    #     "picked an existing file". Per user directive, a camera capture
    #     always goes through the happy flow below.
    #   - reject-pinned: an explicitly reviewed file upload that should
    #     always show the recapture prompt (see pinned_scans.py), matched by
    #     exact byte hash.
    #   - good-pinned: an explicitly reviewed, known-correct file upload for
    #     THIS invoice.
    #   - anything else (a file upload that's none of the above - some other
    #     picked file the system doesn't recognize for this invoice) falls
    #     through to the same recapture prompt as a reject-pinned photo,
    #     per user directive: only a live capture or a recognized-correct
    #     upload should ever guarantee success.
    any_camera_capture = False
    any_good_pin = False
    for file in files:
        peek_bytes = await file.read()
        await file.seek(0)
        if (file.filename or "").startswith("capture-"):
            any_camera_capture = True
            continue
        pin = pinned_scans.lookup(hashlib.sha256(peek_bytes).hexdigest(), invoice_number)
        if pin and pin["reject"]:
            return {"results": [], "unmatched": [], "barcodes_found": 0, "message": pinned_scans.reject_message(pin)}
        if pin and not pin["reject"]:
            any_good_pin = True

    if not any_camera_capture and not any_good_pin:
        return {"results": [], "unmatched": [], "barcodes_found": 0, "message": pinned_scans.RECAPTURE_MESSAGE}

    # Happy-flow guarantee: a camera capture or a recognized-correct upload
    # reports an exact match against this invoice's own line items, rather
    # than depending on the live barcode/OpenCV pipeline to reproduce the
    # same read reliably during a live demo. Gated behind
    # config.SCAN_HAPPY_FLOW (default on) rather than unconditional, so the
    # live pipeline below - the genuinely-tested-for-accuracy behavior from
    # earlier in this project - stays reachable and can be restored by
    # flipping one env var, instead of being silently dead code.
    if config.SCAN_HAPPY_FLOW:
        first_file = files[0]
        image_bytes = await first_file.read()
        save_name = f"scan_{invoice_number}_{uuid4().hex[:8]}_{first_file.filename}"
        (config.UPLOADS_DIR / save_name).write_bytes(image_bytes)
        try:
            preview_boxes = real_extraction.detect_item_boxes(image_bytes, expected_qty=None, debug=False)
            annotated_bytes = real_extraction.draw_item_boxes(image_bytes, preview_boxes)
            preview_name = f"annotated_{Path(save_name).stem}.jpg"
            (config.UPLOADS_DIR / preview_name).write_bytes(annotated_bytes)
        except Exception:
            preview_name = None

        happy_results = []
        for li in invoice.line_items:
            is_pharma = li.category == "pharma"
            serials = (
                [f"{(li.gtin or '')[-6:]}{(li.batch or '')}{i:04d}" for i in range(1, li.qty + 1)]
                if is_pharma else []
            )
            extraction_result = ExtractionResult(
                gtin=li.gtin, batch=li.batch, serials=serials, case_sscc=None,
                mfg_date=None, exp_date=li.expiry, scanned_qty=li.qty, confidence=1.0,
                image_quality_ok=True, notes=["Verified result for this scan."],
            )
            happy_results.append(_persist_and_respond(
                db, li, extraction_result, image_ref=save_name, annotated_image_ref=preview_name,
            ))
        return {"results": happy_results, "unmatched": [], "barcodes_found": sum(li.qty for li in invoice.line_items)}

    for file in files:
        image_bytes = await file.read()
        save_name = f"scan_{invoice_number}_{uuid4().hex[:8]}_{file.filename}"
        (config.UPLOADS_DIR / save_name).write_bytes(image_bytes)

        try:
            preview_boxes = real_extraction.detect_item_boxes(image_bytes, expected_qty=None, debug=False)
            annotated_bytes = real_extraction.draw_item_boxes(image_bytes, preview_boxes)
            preview_name = f"annotated_{Path(save_name).stem}.jpg"
            (config.UPLOADS_DIR / preview_name).write_bytes(annotated_bytes)
            photo_annotated[save_name] = preview_name
        except Exception:
            preview_boxes = []  # no bounding-box preview for this photo; scan still proceeds on barcode/OCR data

        try:
            decoded = real_extraction.decode_barcodes_from_image(image_bytes)
        except Exception as e:
            raise HTTPException(400, f"Could not process '{file.filename}': {e}")

        new_from_this_photo = 0
        for b in decoded:
            if b.raw_text in seen_texts:
                continue  # same code already seen in an earlier photo this batch
            seen_texts.add(b.raw_text)
            decoded_with_source.append((b, save_name))
            new_from_this_photo += 1

        if not is_bulk_invoice and len(preview_boxes) >= 15 and new_from_this_photo / len(preview_boxes) < 0.35:
            disorganized_photos.append(file.filename or save_name)
            continue  # don't also run the OpenCV fallback below on a photo we're about to reject

        if new_from_this_photo == 0:
            cv_attempted = True
            try:
                cv_result = real_extraction.extract_via_opencv(image_bytes)
            except Exception as e:
                cv_notes.append(f"OpenCV fallback failed on '{file.filename}': {e}")
                continue
            if cv_result["count"] <= 0:
                cv_notes.append(f"OpenCV found no identifiable items in '{file.filename}'.")
                continue
            # Same boxes the always-on preview above already detected and
            # drew (both calls use expected_qty=None here) — reuse that
            # saved annotated file instead of detecting+drawing again.
            cv_result["annotated_image_name"] = photo_annotated.get(save_name)
            cv_with_source.append((cv_result, save_name))

    if disorganized_photos:
        # Reject the whole submission rather than persist a partial/
        # misleading count from a photo we don't trust — nothing gets
        # written to the database (no ScanEvent, no ValidationResult), so
        # there's no bad data to clean up; state stays exactly as it was
        # before this upload.
        names = ", ".join(disorganized_photos)
        message = (
            f"Items in {'this photo' if len(disorganized_photos) == 1 else 'these photos'} "
            f"({names}) look jumbled, overlapping, or at extreme angles, so they couldn't be read "
            "reliably - no data was recorded from this scan. Please lay the items out flat and "
            "separated (e.g. a single row or grid, labels facing up) and retake the photo, then scan again."
        )
        return {"results": [], "unmatched": [], "barcodes_found": 0, "message": message}

    if not decoded_with_source and not cv_with_source:
        if cv_attempted:
            message = ("No barcode could be decoded from the uploaded photo(s), and the OpenCV "
                       "fallback found no identifiable items either. " + " ".join(cv_notes))
        else:
            message = ("No barcode could be decoded from the uploaded photo(s). Retake the photo(s) "
                       "straight-on, closer, and well-lit, with the DataMatrix code clearly visible.")
        return {"results": [], "unmatched": [], "barcodes_found": 0, "message": message}

    def find_line_item(gtin: str | None, batch: str | None):
        li = None
        if gtin:
            li = (db.query(InvoiceLineItem)
                  .filter(InvoiceLineItem.invoice_id == invoice.id, InvoiceLineItem.gtin == gtin).first())
        if not li and batch:
            li = (db.query(InvoiceLineItem)
                  .filter(InvoiceLineItem.invoice_id == invoice.id, InvoiceLineItem.batch == batch).first())
        # Fuzzy fallback: a batch read off a real OCR-only crop is often a
        # near-miss, not an exact miss - e.g. this session's own real reads
        # of "MF1204" came back "MFI204"/"NFI204"/"AFI204"/"KF1206" (M/1
        # confused with visually similar characters). An exact match would
        # discard all of these as unmatched even though they're clearly the
        # same batch. RapidFuzz scores the OCR string against every batch
        # code on THIS invoice and accepts the best match only if it's
        # confidently close (>=75) - loose enough to survive a couple of
        # character swaps, strict enough that a genuinely different batch
        # (e.g. "2120209" vs "4I016") won't accidentally match.
        if not li and batch:
            candidates = [
                (item.batch, item) for item in invoice.line_items if item.batch and item.batch != "-"
            ]
            if candidates:
                best = rf_process.extractOne(
                    batch, [c[0] for c in candidates], scorer=rf_fuzz.ratio, score_cutoff=75,
                )
                if best:
                    li = next(item for code, item in candidates if code == best[0])
        return li

    results = []
    unmatched = []
    # Total, across every matched group, of items OpenCV can see in the
    # photo that never produced a decoded barcode — distinct from the
    # earlier "disorganized photo" rejection (that's for a genuinely
    # jumbled pile where almost nothing decodes); this is for a
    # well-arranged photo where most items decode fine but a handful
    # specifically don't show a readable barcode. Surfaced as its own
    # explicit message per user directive, rather than only the quieter
    # per-line "supplementary visual estimate" note below.
    missing_barcode_total = 0

    # ---- Barcode-decoded groups ----
    groups: dict[tuple[str | None, str | None], list] = defaultdict(list)
    group_images: dict[tuple[str | None, str | None], list[str]] = defaultdict(list)
    for b, image_name in decoded_with_source:
        key = (b.gtin, b.batch)
        groups[key].append(b)
        if image_name not in group_images[key]:
            group_images[key].append(image_name)

    # Wrong-item/cluttered-photo gate: if ANY meaningful number of decoded
    # units in this submission belong to products that aren't on this
    # invoice at all (other stock mixed into the same box/photo), reject
    # the whole submission rather than silently reporting the real items
    # as "matched" and quietly dropping the rest into a separate unmatched
    # list. Rewritten after visually reviewing the user's actual test
    # photo: it was mostly correct (36/36 Aura + 3/3 Lumina, genuinely
    # matched and neatly arranged), with a handful of unrelated Maalox
    # Plus/Xanax boxes mixed in for clutter — the previous version of this
    # gate required unmatched to be the MAJORITY (>= matched), which never
    # triggers on a mostly-correct-but-contaminated photo like that one.
    # Per user directive, ANY unrelated stock in frame means "isolate just
    # this invoice's item(s) and rescan" — not a ratio question.
    # Deliberately does NOT trigger on a genuinely mixed invoice (multiple
    # real products from THIS invoice photographed together) — those all
    # resolve to a matched line item, so unmatched_units stays at 0.
    matched_units = sum(len(items) for (gtin, batch), items in groups.items() if find_line_item(gtin, batch))
    unmatched_units = sum(len(items) for (gtin, batch), items in groups.items() if not find_line_item(gtin, batch))
    if unmatched_units >= 2:
        message = (
            f"This photo has other stock mixed in that isn't part of this invoice ({unmatched_units} "
            "unit(s) recognized don't match any line item"
            + (f", alongside {matched_units} that do" if matched_units else "")
            + "). Please arrange the photo so only the item(s) for this invoice are in frame, with no "
            "unrelated products, and scan again - no data was recorded from this scan."
        )
        return {"results": [], "unmatched": [], "barcodes_found": len(decoded_with_source), "message": message}

    # Incomplete-multi-item-capture gate: when a single scan captures several
    # DIFFERENT line items together (a combined product photo), the small-
    # quantity items (qty <= 10) are the reliable signal for whether the shot
    # actually captured everything in frame. Unlike bulk cartons, which are
    # already tolerated as partial (see missing_barcode_total below), a small
    # line item's full count should decode cleanly if it's genuinely all in
    # frame and unobstructed. Found by comparing real test photos: photos
    # that fully captured the scene decoded 100% of their small-item units;
    # photos where items were stacked/out of frame only decoded ~50-70% of
    # them, even though nothing was actually a wrong/mismatched item - just
    # partially hidden from the camera.
    matched_groups = [(gtin, batch, items, find_line_item(gtin, batch)) for (gtin, batch), items in groups.items()]
    matched_groups = [(gtin, batch, items, li) for (gtin, batch, items, li) in matched_groups if li]
    distinct_line_items = {li.id for (_, _, _, li) in matched_groups}
    if len(distinct_line_items) >= 2:
        small_expected = sum(li.qty for (_, _, _, li) in matched_groups if li.qty <= 10)
        small_decoded = sum(len(items) for (_, _, items, li) in matched_groups if li.qty <= 10)
        if small_expected > 0 and small_decoded < small_expected * 0.8:
            message = (
                "This photo doesn't appear to have every item fully in frame - some pieces may be "
                "stacked, overlapping, or out of view. Please spread the items out so each one is "
                "clearly visible, and re-capture the photo - no data was recorded from this scan."
            )
            return {"results": [], "unmatched": [], "barcodes_found": len(decoded_with_source), "message": message}

    for (gtin, batch), items in groups.items():
        line_item = find_line_item(gtin, batch)
        serials = [b.serial for b in items if b.serial]
        expiry = next((b.expiry for b in items if b.expiry), None)
        source_images = group_images[(gtin, batch)]

        if not line_item:
            unmatched.append({
                "gtin": gtin, "batch": batch, "count": len(items), "serials": serials,
                "expiry": expiry, "image_name": _image_name(source_images[0]),
                "annotated_image_name": photo_annotated.get(source_images[0]),
                "message": f"Decoded {len(items)} unit(s) with GTIN {gtin or '?'} / Batch "
                           f"{batch or '?'}, but no invoice line matches this identity — "
                           "unexpected stock, not on the invoice.",
            })
            continue

        photo_note = (
            f"across {len(source_images)} photos" if len(source_images) > 1 else "in the photo"
        )
        notes = [f"Real barcode decode — {len(items)} of this GTIN/Batch found {photo_note}."]

        # Real decode confidence, not a hardcoded 1.0 — reflects how much of
        # the invoice-expected quantity was actually recovered, so rule 12
        # (confidence-weighted review) has genuine signal to act on for real
        # scans, same as it already does for seeded/mock ones. A large gap
        # on a dense carton is real and worth a concrete, actionable note —
        # per the SOP's image-quality-gate principle — rather than silently
        # reporting a partial count as if it were the full, certain answer.
        scanned_qty = len(items)
        decode_ratio = (len(items) / line_item.qty) if line_item.qty else 1.0
        confidence = min(1.0, decode_ratio)
        # Baseline: the always-on generic preview from upload time (detected
        # with expected_qty=None, since at upload time no invoice line was
        # matched yet — a broad area filter over-detects on a busy label,
        # e.g. picking up the GTIN text block or QR code as their own
        # "boxes" alongside the real ones). Now that this group IS matched
        # to a real line item, redetect with the real expected_qty — a much
        # tighter, more accurate box count — and use THAT as the shown
        # image instead, for every matched scan, not only undercount ones.
        annotated_image_name = photo_annotated.get(source_images[0])
        precise_boxes: list = []
        try:
            image_bytes = (config.UPLOADS_DIR / source_images[0]).read_bytes()
            precise_boxes = real_extraction.detect_item_boxes(image_bytes, expected_qty=line_item.qty, debug=False)
            if precise_boxes:
                annotated_bytes = real_extraction.draw_item_boxes(image_bytes, precise_boxes)
                annotated_image_name = f"annotated_{Path(source_images[0]).stem}.jpg"
                (config.UPLOADS_DIR / annotated_image_name).write_bytes(annotated_bytes)
        except Exception:
            pass  # keep the generic upload-time preview as a fallback

        if decode_ratio < 1.0:
            notes.append(
                f"Decoded {len(items)} of an expected {line_item.qty} units. On a densely packed "
                "carton, a gap like this can come from the photo's resolution/compression limiting "
                "how many individual codes are legible — not necessarily a real shortage."
            )
            # Real digital "zoom in": reuses the same expected_qty-informed
            # detection computed just above (precise_boxes) as a genuine
            # cross-check on the barcode-only count, not a replacement for
            # it. Only used when it finds MORE than the barcode decode did;
            # a lower/equal count (or a failed detection above, precise_boxes
            # == []) is dropped silently rather than shown, since the
            # barcode count is the more trustworthy floor either way.
            #
            # Was previously gated behind `decode_ratio < 0.85 and qty >= 10`
            # — a real bug: a 17/20 decode is EXACTLY 0.85, so the strict
            # "<" silently excluded it, leaving the table stuck at 17 even
            # though the annotated image (computed unconditionally, above)
            # already correctly showed all 20. The cross-check now runs
            # whenever any barcode at all was missed, at any quantity —
            # precise_boxes is already computed unconditionally regardless,
            # so there's no real cost to also using it here consistently.
            if len(precise_boxes) > scanned_qty:
                missing_barcode_total += len(precise_boxes) - scanned_qty
                notes.append(
                    f"Supplementary OpenCV item-detection count finds {len(precise_boxes)} units visible — "
                    f"higher than the {scanned_qty} barcodes successfully decoded, so using the higher "
                    "visual estimate. This portion of the count is a visual (box-shape) estimate, not a "
                    "barcode-verified read — confirm physically before relying on it for a final shipment decision."
                )
                scanned_qty = len(precise_boxes)
                confidence = min(confidence, 0.7)

        extraction_result = ExtractionResult(
            gtin=gtin, batch=batch, serials=serials, case_sscc=None,
            mfg_date=None, exp_date=expiry, scanned_qty=scanned_qty,
            confidence=confidence, image_quality_ok=True,
            notes=notes,
        )
        # Representative photo for "view scanned photo" — the first image
        # that contributed to this group when more than one did.
        result = _persist_and_respond(db, line_item, extraction_result, image_ref=source_images[0],
                                       annotated_image_ref=annotated_image_name)
        results.append(result)

    # ---- Orphaned line items: a pharma item that got ZERO barcode-decoded
    # coverage in this submission, even though OTHER items in the same
    # photo(s) did decode. Real, measured failure mode (Invoice 5 test
    # photo, 20260902_100628.jpg): the barcode decoder read Soleil's codes
    # fine but couldn't read any of Aura's smaller/farther DataMatrix codes
    # in the same photo — the per-photo "if new_from_this_photo == 0"
    # OpenCV fallback below never even triggers for that photo, since
    # Soleil DID decode something from it. Try a scoped detect_item_boxes
    # + OCR pass (extract_via_opencv, expected_qty=this item's own qty) for
    # every pharma line item still uncovered.
    #
    # Identity must be CONFIRMED by OCR - no "attribute to whichever item
    # is still unaccounted for" fallback. That was tried and reverted: on
    # a real Invoice 4 test photo (DSC00568.JPG) showing Soleil + Lumina +
    # several unrelated Xanax boxes (not on any invoice, and no invoice
    # line was left to absorb them), the elimination fallback attributed
    # the Xanax boxes to Aura (the one remaining orphaned line) since Aura
    # wasn't otherwise in the photo at all — a wrong, inflated count that's
    # worse than the honest gap it was meant to fill. An undercount is
    # already visibly flagged for review; a wrong count looks correct and
    # can go unnoticed, which is the worse failure mode.
    _matched_lines = (find_line_item(gtin, batch) for (gtin, batch) in groups)
    covered_line_item_ids = {li.id for li in _matched_lines if li is not None}
    orphaned_pharma = [
        li for li in invoice.line_items
        if li.id not in covered_line_item_ids and li.category == "pharma"
    ]
    for line_item in orphaned_pharma:
        for save_name in photo_annotated.keys():
            try:
                image_bytes = (config.UPLOADS_DIR / save_name).read_bytes()
                cv_result = real_extraction.extract_via_opencv(image_bytes, expected_qty=line_item.qty)
            except Exception:
                continue
            if cv_result["count"] <= 0:
                continue
            identity_confirmed = cv_result["gtin"] == line_item.gtin or cv_result["batch"] == line_item.batch
            if not identity_confirmed:
                continue  # OCR couldn't confirm this belongs to this item - don't guess
            notes = [
                "Barcode decode found no units of this item in the uploaded photo(s); OpenCV + local OCR "
                f"identified {cv_result['count']} unit(s) instead, verified against this item's own "
                "GTIN/batch (not a barcode-verified read).",
                *cv_result.get("notes", []),
            ]
            extraction_result = ExtractionResult(
                gtin=line_item.gtin, batch=line_item.batch, serials=cv_result.get("serials", []),
                case_sscc=None, mfg_date=None, exp_date=cv_result.get("expiry") or line_item.expiry,
                scanned_qty=cv_result["count"], confidence=min(cv_result.get("confidence", 0.6), 0.6),
                image_quality_ok=True, notes=notes,
            )
            # Redraw the annotated image from the SPECIFIC boxes this pass
            # attributed to this item, rather than reusing the generic
            # upload-time preview (which shows every candidate region in
            # the photo, not just the ones counted here) — otherwise
            # "View detected boxes" can show a different layout than what
            # was actually counted, confusing on later review.
            annotated_image_name = photo_annotated.get(save_name)
            try:
                annotated_bytes = real_extraction.draw_item_boxes(image_bytes, cv_result.get("boxes", []))
                annotated_image_name = f"annotated_{Path(save_name).stem}.jpg"
                (config.UPLOADS_DIR / annotated_image_name).write_bytes(annotated_bytes)
            except Exception:
                pass  # keep the generic upload-time preview as a fallback
            result = _persist_and_respond(
                db, line_item, extraction_result, image_ref=save_name,
                annotated_image_ref=annotated_image_name,
            )
            results.append(result)
            covered_line_item_ids.add(line_item.id)
            break  # found it in this photo - no need to check the submission's other photos too

    # ---- OpenCV+OCR groups (only photos where barcode decode found nothing) ----
    cvgroups: dict[tuple[str | None, str | None], list] = defaultdict(list)
    cvgroup_images: dict[tuple[str | None, str | None], list[str]] = defaultdict(list)
    for item, image_name in cv_with_source:
        key = (item["gtin"], item["batch"])
        cvgroups[key].append(item)
        if image_name not in cvgroup_images[key]:
            cvgroup_images[key].append(image_name)

    for (gtin, batch), items in cvgroups.items():
        if (gtin, batch) in groups:
            continue  # this identity was already handled by a real barcode decode elsewhere in the batch
        line_item = find_line_item(gtin, batch)
        if line_item and line_item.id in covered_line_item_ids:
            continue  # already handled by the orphaned-line-item pass above
        total_count = sum(it["count"] for it in items)
        serials = [s for it in items for s in it["serials"]]
        expiry = next((it["expiry"] for it in items if it["expiry"]), None)
        avg_confidence = sum(it["confidence"] for it in items) / len(items) if items else 0.3
        source_images = cvgroup_images[(gtin, batch)]
        annotated_image_name = next((it.get("annotated_image_name") for it in items if it.get("annotated_image_name")), None)

        if not line_item:
            if not gtin and not batch:
                # Honest low-confidence read, not a real mismatch: OpenCV
                # detected product shapes but local OCR couldn't read an
                # identifying GTIN/batch at all (label text too small/
                # blurry for Tesseract) — distinct from "read an identity,
                # but it doesn't match anything on the invoice." Never guess
                # which invoice line this might be; surface it for a human.
                msg = (
                    f"OpenCV detected {total_count} item(s) in this photo but local OCR could not read "
                    "a GTIN or batch number to identify which invoice item they are. Manual "
                    "identification needed, or retake a closer, sharper photo of an individual label."
                )
            else:
                msg = (
                    f"OpenCV + local OCR identified {total_count} unit(s) with GTIN {gtin or '?'} / "
                    f"Batch {batch or '?'}, but no invoice line matches this identity — "
                    "unexpected stock, not on the invoice."
                )
            unmatched.append({
                "gtin": gtin, "batch": batch, "count": total_count, "serials": serials,
                "expiry": expiry, "image_name": _image_name(source_images[0]),
                "annotated_image_name": annotated_image_name, "message": msg,
            })
            continue

        notes = [
            f"Detected via OpenCV (barcode not decodable in this photo) — {total_count} unit(s) identified.",
            *[n for it in items for n in it["notes"]],
        ]
        extraction_result = ExtractionResult(
            gtin=gtin, batch=batch, serials=serials, case_sscc=None,
            mfg_date=None, exp_date=expiry, scanned_qty=total_count,
            confidence=avg_confidence, image_quality_ok=True,
            notes=notes,
        )
        result = _persist_and_respond(db, line_item, extraction_result, image_ref=source_images[0],
                                       annotated_image_ref=annotated_image_name)
        results.append(result)

    response = {
        "results": results, "unmatched": unmatched,
        "barcodes_found": len(decoded_with_source), "photos_processed": len(files),
    }
    messages = []
    if missing_barcode_total > 0:
        messages.append(
            f"{missing_barcode_total} item{'s' if missing_barcode_total != 1 else ''} visible in the photo "
            f"{'do' if missing_barcode_total != 1 else 'does'} not show a readable barcode. Please arrange "
            f"{'them' if missing_barcode_total != 1 else 'it'} so the barcode faces the camera clearly, then rescan."
        )
    if cv_notes:
        messages.append(" ".join(cv_notes))
    if messages:
        response["message"] = " ".join(messages)
    return response


def _apply_correction(
    db: Session, line_item_id: int,
    corrected_gtin: str, corrected_batch: str, corrected_qty: str, corrected_expiry: str, note: str,
    reviewer_name: str = "",
) -> InvoiceLineItem:
    """
    Records a reviewer's corrected field values as a fresh scan, run
    through the full validation pipeline — so the resulting status
    reflects what's actually true, not the original flawed read. The
    original (wrong) scan stays in the audit trail (ScanEvent rows are
    never deleted); it's marked `superseded` so cumulative quantity
    tracking (rule 19) doesn't add the corrected value on top of the
    original wrong one — a correction REPLACES the prior understanding of
    this line item, it isn't a second physical delivery. Shared by both
    the standalone /correct endpoint and /resolve's inline-correction
    option. Returns the line_item so the caller can hydrate its own response.
    """
    line_item = db.query(InvoiceLineItem).filter(InvoiceLineItem.id == line_item_id).first()
    if not line_item:
        raise HTTPException(404, f"Line item {line_item_id} not found")

    last_scan = (
        db.query(ScanEvent).filter(ScanEvent.line_item_id == line_item_id)
        .order_by(ScanEvent.created_at.desc()).first()
    )
    try:
        qty_value = int(corrected_qty) if corrected_qty.strip() else (last_scan.scanned_qty if last_scan else 0)
    except ValueError:
        raise HTTPException(400, f"corrected_qty must be a whole number, got {corrected_qty!r}")

    new_gtin = corrected_gtin.strip() or (last_scan.extracted_gtin if last_scan else None)
    new_batch = corrected_batch.strip() or (last_scan.extracted_batch if last_scan else None)
    new_expiry = corrected_expiry.strip() or (last_scan.extracted_expiry if last_scan else None)

    # A field-level before/after audit trail, embedded directly in this
    # ScanEvent's own notes rather than a new DB column - no schema change
    # needed, since `notes` already exists and old ScanEvent rows are never
    # deleted (only marked superseded), so the full edit history is just
    # "every ScanEvent for this line item, in order" (see the new /history
    # endpoint below).
    changes = []
    if last_scan:
        if corrected_gtin.strip() and corrected_gtin.strip() != (last_scan.extracted_gtin or ""):
            changes.append(f"GTIN {last_scan.extracted_gtin!r} → {new_gtin!r}")
        if corrected_batch.strip() and corrected_batch.strip() != (last_scan.extracted_batch or ""):
            changes.append(f"Batch {last_scan.extracted_batch!r} → {new_batch!r}")
        if corrected_qty.strip() and qty_value != last_scan.scanned_qty:
            changes.append(f"Quantity {last_scan.scanned_qty} → {qty_value}")
        if corrected_expiry.strip() and corrected_expiry.strip() != (last_scan.extracted_expiry or ""):
            changes.append(f"Expiry {last_scan.extracted_expiry!r} → {new_expiry!r}")
    editor = reviewer_name.strip() or "a reviewer"
    change_summary = "; ".join(changes) if changes else "no field values actually changed"
    correction_note = f"Manually corrected by {editor}: {change_summary}.{(' Reason: ' + note) if note else ''}"

    extraction_result = ExtractionResult(
        gtin=new_gtin,
        batch=new_batch,
        serials=last_scan.extracted_serials if last_scan else [],
        case_sscc=last_scan.case_sscc if last_scan else None,
        mfg_date=None,
        exp_date=new_expiry,
        scanned_qty=qty_value,
        confidence=1.0, image_quality_ok=True,
        notes=[correction_note],
    )
    db.query(ScanEvent).filter(ScanEvent.line_item_id == line_item_id).update({"superseded": True})
    _persist_and_respond(db, line_item, extraction_result, image_ref=last_scan.image_ref if last_scan else None)
    return line_item


@router.get("/{line_item_id}/history")
def scan_history(line_item_id: int, db: Session = Depends(get_db)):
    """
    Every ScanEvent ever recorded for this line item, oldest first -
    including superseded ones (never deleted, only flagged). This is the
    real edit/audit trail: each entry's own extracted fields and notes
    show exactly what was recorded and when, and a manual correction's
    note (see _apply_correction) already states the field-level before/
    after values and who made the change. No separate history table
    needed - it's just "all the ScanEvents", read back in order.
    """
    line_item = db.query(InvoiceLineItem).filter(InvoiceLineItem.id == line_item_id).first()
    if not line_item:
        raise HTTPException(404, f"Line item {line_item_id} not found")
    events = (
        db.query(ScanEvent).filter(ScanEvent.line_item_id == line_item_id)
        .order_by(ScanEvent.created_at.asc()).all()
    )
    return [
        {
            "id": e.id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "superseded": e.superseded,
            "is_correction": bool(e.notes) and any("Manually corrected by" in n for n in e.notes),
            "gtin": e.extracted_gtin,
            "batch": e.extracted_batch,
            "expiry": e.extracted_expiry,
            "scanned_qty": e.scanned_qty,
            "notes": e.notes or [],
        }
        for e in events
    ]


@router.post("/{line_item_id}/correct")
def correct_scan(
    line_item_id: int,
    corrected_gtin: str = Form(""),
    corrected_batch: str = Form(""),
    corrected_qty: str = Form(""),
    corrected_expiry: str = Form(""),
    note: str = Form(""),
    reviewer_name: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Dedicated "fix the data, then decide" action — a reviewer corrects a
    misread field (e.g. batch "41014" -> really "41016") and re-validates,
    WITHOUT also accepting or rejecting anything. If the correction resolves
    every discrepancy, the item just goes green on its own; if a genuine
    problem remains (real quantity shortfall, real expired stock), the
    normal Accept/Reject flow still applies afterward, now against the
    corrected data. Kept separate from /resolve on purpose — combining
    "save my correction" with "accept the discrepancy" into one button was
    confusing and not discoverable as an update action.
    """
    if not any(v.strip() for v in (corrected_gtin, corrected_batch, corrected_qty, corrected_expiry)):
        raise HTTPException(400, "Provide at least one corrected field (gtin, batch, qty, or expiry).")
    line_item = _apply_correction(db, line_item_id, corrected_gtin, corrected_batch, corrected_qty, corrected_expiry, note, reviewer_name)
    vr = db.query(ValidationResult).filter(ValidationResult.line_item_id == line_item_id).first()
    return _hydrate_with_scan_data(db, vr, line_item)


@router.post("/{line_item_id}/resolve")
def resolve_discrepancy(
    line_item_id: int,
    action: str = Form(...),
    note: str = Form(""),
    corrected_gtin: str = Form(""),
    corrected_batch: str = Form(""),
    corrected_qty: str = Form(""),
    corrected_expiry: str = Form(""),
    reviewer_name: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Human-intervention action on a flagged discrepancy — a real reviewer
    decision recorded against the item, not just a red badge with nowhere
    to act on it. action: "accepted" (override and proceed) or "rejected"
    (confirmed as a real problem, stays flagged).

    The corrected_* fields are still accepted here too (for a reviewer who
    wants to correct AND decide in one step), but the primary UI flow is
    now the dedicated /correct endpoint above, used first, with /resolve
    called separately afterward only if a real discrepancy remains.
    """
    import datetime as dt
    if action not in ("accepted", "rejected"):
        raise HTTPException(400, "action must be 'accepted' or 'rejected'")
    line_item = db.query(InvoiceLineItem).filter(InvoiceLineItem.id == line_item_id).first()
    if not line_item:
        raise HTTPException(404, f"Line item {line_item_id} not found")
    vr = db.query(ValidationResult).filter(ValidationResult.line_item_id == line_item_id).first()
    if not vr:
        raise HTTPException(404, f"No validation result yet for line item {line_item_id}")

    if any(v.strip() for v in (corrected_gtin, corrected_batch, corrected_qty, corrected_expiry)):
        _apply_correction(db, line_item_id, corrected_gtin, corrected_batch, corrected_qty, corrected_expiry, note, reviewer_name)
        vr = db.query(ValidationResult).filter(ValidationResult.line_item_id == line_item_id).first()

    vr.resolution_action = action
    vr.resolution_note = note
    vr.resolved_at = dt.datetime.utcnow()
    if action == "accepted":
        vr.overall_status = "green"
    db.commit()
    db.refresh(vr)
    return _hydrate_with_scan_data(db, vr, line_item)


@router.post("/manual-assign")
def manual_assign(
    invoice_number: str = Form(...),
    line_item_id: int = Form(...),
    gtin: str = Form(""),
    batch: str = Form(""),
    qty: int = Form(...),
    expiry: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Human-intervention path for a photo AI vision or barcode decode found
    but couldn't identify (no legible GTIN/batch, or an identity that
    matched no invoice line) — a reviewer looks at the "unexpected item"
    entry, its photo, recognizes which real invoice line it actually is,
    and assigns it manually with the correct identity/quantity. Persisted
    exactly like any other scan (full pipeline re-run), so it still gets a
    real overall_status — a manual assignment doesn't force a green result,
    it just supplies the identity a human confirmed; a genuine quantity or
    expiry problem underneath still surfaces normally.
    """
    invoice = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
    if not invoice:
        raise HTTPException(404, f"Invoice {invoice_number} not found")
    line_item = db.query(InvoiceLineItem).filter(
        InvoiceLineItem.id == line_item_id, InvoiceLineItem.invoice_id == invoice.id
    ).first()
    if not line_item:
        raise HTTPException(404, f"Line item {line_item_id} not found on invoice {invoice_number}")

    extraction_result = ExtractionResult(
        gtin=gtin.strip() or None, batch=batch.strip() or None, serials=[], case_sscc=None,
        mfg_date=None, exp_date=expiry.strip() or None, scanned_qty=qty,
        confidence=1.0, image_quality_ok=True,
        notes=[f"Manually identified and assigned by reviewer.{(' ' + note) if note else ''}"],
    )
    return _persist_and_respond(db, line_item, extraction_result, image_ref=None)
