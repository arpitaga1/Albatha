import datetime as dt
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models import Invoice, InvoiceLineItem, ValidationResult
from app.schemas import InvoiceOut, InvoiceSummary
from app.services import real_extraction, sap_source

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


@router.get("", response_model=list[InvoiceSummary])
def list_invoices(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).order_by(Invoice.demo_flow).all()
    return [
        InvoiceSummary(id=inv.id, invoice_number=inv.invoice_number,
                        demo_flow=inv.demo_flow, item_count=len(inv.line_items))
        for inv in invoices
    ]


def _sap_row(db: Session, inv: Invoice) -> dict:
    statuses = []
    for li in inv.line_items:
        vr = db.query(ValidationResult).filter(ValidationResult.line_item_id == li.id).first()
        statuses.append(vr.overall_status if vr else "pending")
    if not statuses or all(s == "pending" for s in statuses):
        status = "pending"
    elif any(s == "red" for s in statuses):
        status = "red"
    elif any(s in ("yellow", "pending") for s in statuses):
        status = "yellow"
    else:
        status = "green"

    return {
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date,
        "supplier": inv.supplier,
        "item_count": len(inv.line_items),
        "total_quantity": sum(li.qty for li in inv.line_items),
        "status": status,
        "demo_flow": inv.demo_flow,
    }


@router.get("/sap")
def list_sap_invoices(db: Session = Depends(get_db)):
    """
    "Invoices from SAP" — per the spec: a clearly-labeled list of dummy
    invoices presented as if fetched from SAP. Goes through
    app.services.sap_source exclusively (never queries seed rows directly)
    so a real SAP integration later only requires changing that one module.
    """
    return [_sap_row(db, inv) for inv in sap_source.get_invoices_from_sap(db)]


@router.get("/sap/search/{invoice_number}")
def search_sap_invoice(invoice_number: str, db: Session = Depends(get_db)):
    """
    Looks up one invoice number against "SAP" directly, per user request —
    the fixed 8 demo invoices were the only thing searchable before. If it
    already exists (a demo flow, a prior upload, or a previously-searched
    number), returns that; otherwise generates and persists a new
    SAP-sourced invoice for it on the spot (sap_source.search_or_fetch_invoice)
    so searching a number nobody's seen before still runs through the exact
    same wizard/scan/Tatmeen pipeline as any other SAP invoice.
    """
    inv = sap_source.search_or_fetch_invoice(db, invoice_number.strip())
    return _sap_row(db, inv)


@router.get("/preloaded")
def list_preloaded_invoices(db: Session = Depends(get_db)):
    """
    "Pre-uploaded Invoices" dropdown on the Start New Validation screen —
    real client-provided invoice fixtures (app.services.sap_source.
    get_preloaded_invoices), kept separate from the "Invoices from SAP"
    list above even though the row shape is identical.
    """
    return [_sap_row(db, inv) for inv in sap_source.get_preloaded_invoices(db)]


@router.post("/upload", response_model=InvoiceOut)
async def upload_invoice(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Real invoice ingestion — no mock, no seed key. First tries free,
    deterministic OCR + regex parsing (Tesseract via PyMuPDF for PDFs) — see
    app/services/real_extraction.py's two layout patterns. If neither
    pattern matches AND EXTRACTION_MODE=live is configured (a real,
    user-opted-in ANTHROPIC_API_KEY), falls back to a live AI-vision read of
    the document instead of hand-writing a new regex per invoice template.

    On total failure (no regex match, and live mode unavailable or itself
    failing), this raises rather than silently substituting mock data for
    something presented as real — the "graceful fallback" the spec asks for
    is offered explicitly instead (the frontend surfaces "browse Invoices
    from SAP instead" alongside the error), never automatically, so a user
    is never shown fabricated data believing it came from their own document.
    """
    file_bytes = await file.read()
    content_type = file.content_type or "application/octet-stream"

    try:
        raw_text = real_extraction.ocr_document(file_bytes, content_type)
    except Exception as e:
        raise HTTPException(400, f"Could not OCR this file: {e}")

    parsed = real_extraction.parse_invoice_text(raw_text)
    extraction_method = "ocr-regex"

    if not parsed.lines and config.EXTRACTION_MODE == "live":
        try:
            parsed = real_extraction.extract_invoice_live(file_bytes, content_type)
            extraction_method = "live-vision"
        except Exception as e:
            raise HTTPException(502, f"Live AI-vision extraction failed: {e}")

    if not parsed.lines:
        detail = (
            "OCR ran, but no line items could be parsed from this document. "
            "Both known layout patterns (Sample Invoice.pdf style and "
            "Test_Invoice_Item1_Item2.pdf style) failed to match — a "
            "differently-formatted invoice needs its own pattern, or set "
            "EXTRACTION_MODE=live with an ANTHROPIC_API_KEY to read it via "
            "AI vision instead. "
            f"First 300 chars of what OCR read: {raw_text[:300]!r}"
        )
        raise HTTPException(422, detail)

    invoice_number = parsed.invoice_number or f"UPLOAD-{int(dt.datetime.utcnow().timestamp())}"

    existing = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
    if existing:
        return existing  # idempotent: re-uploading the same invoice returns the same record

    # Save the original document so a user can click back into it later and
    # see exactly what they uploaded — not just the data extracted from it.
    save_name = f"invoice_{invoice_number}_{uuid4().hex[:8]}_{file.filename}"
    (config.UPLOADS_DIR / save_name).write_bytes(file_bytes)

    inv = Invoice(
        invoice_number=invoice_number,
        sold_to=parsed.sold_to or "(not detected by OCR)",
        ship_to="",
        supplier=(
            "(uploaded document — extracted via live AI vision)"
            if extraction_method == "live-vision"
            else "(uploaded document — no supplier field detected)"
        ),
        invoice_date=dt.date.today().isoformat(),
        demo_flow=None,
        source="upload",
        source_file_name=save_name,
    )
    inv.line_items = [
        InvoiceLineItem(
            item_name=line.description,
            gtin=line.gtin,
            batch=line.batch,
            expiry=line.expiry,
            qty=line.qty,
            uom=line.uom,
            category="pharma",  # every line the OCR pattern matches has a GTIN column, i.e. pharma-style
        )
        for line in parsed.lines
    ]
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.get("/{invoice_number}", response_model=InvoiceOut)
def get_invoice(invoice_number: str, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
    if not inv:
        raise HTTPException(404, f"Invoice {invoice_number} not found")
    return inv
