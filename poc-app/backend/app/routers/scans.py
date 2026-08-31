from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models import Invoice, InvoiceLineItem, ScanEvent, ValidationResult
from app.schemas import ScanRequest, ValidationResultOut
from app.services import extraction as extraction_service
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
    real provenance badge (barcode decode vs. OpenCV+OCR), not just data
    with no indication of how it was actually obtained."""
    if not image_ref or image_ref.startswith("mock:"):
        return None
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
            pass  # no bounding-box preview for this photo; scan still proceeds on barcode/OCR data

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
        return li

    results = []
    unmatched = []

    # ---- Barcode-decoded groups ----
    groups: dict[tuple[str | None, str | None], list] = defaultdict(list)
    group_images: dict[tuple[str | None, str | None], list[str]] = defaultdict(list)
    for b, image_name in decoded_with_source:
        key = (b.gtin, b.batch)
        groups[key].append(b)
        if image_name not in group_images[key]:
            group_images[key].append(image_name)

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
    if cv_notes:
        response["message"] = " ".join(cv_notes)
    return response


def _apply_correction(
    db: Session, line_item_id: int,
    corrected_gtin: str, corrected_batch: str, corrected_qty: str, corrected_expiry: str, note: str,
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

    extraction_result = ExtractionResult(
        gtin=corrected_gtin.strip() or (last_scan.extracted_gtin if last_scan else None),
        batch=corrected_batch.strip() or (last_scan.extracted_batch if last_scan else None),
        serials=last_scan.extracted_serials if last_scan else [],
        case_sscc=last_scan.case_sscc if last_scan else None,
        mfg_date=None,
        exp_date=corrected_expiry.strip() or (last_scan.extracted_expiry if last_scan else None),
        scanned_qty=qty_value,
        confidence=1.0, image_quality_ok=True,
        notes=[f"Manually corrected by reviewer.{(' ' + note) if note else ''}"],
    )
    db.query(ScanEvent).filter(ScanEvent.line_item_id == line_item_id).update({"superseded": True})
    _persist_and_respond(db, line_item, extraction_result, image_ref=last_scan.image_ref if last_scan else None)
    return line_item


@router.post("/{line_item_id}/correct")
def correct_scan(
    line_item_id: int,
    corrected_gtin: str = Form(""),
    corrected_batch: str = Form(""),
    corrected_qty: str = Form(""),
    corrected_expiry: str = Form(""),
    note: str = Form(""),
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
    line_item = _apply_correction(db, line_item_id, corrected_gtin, corrected_batch, corrected_qty, corrected_expiry, note)
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
        _apply_correction(db, line_item_id, corrected_gtin, corrected_batch, corrected_qty, corrected_expiry, note)
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
