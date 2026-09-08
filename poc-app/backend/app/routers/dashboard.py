from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Invoice, ValidationResult
from app.schemas import DashboardOut, DashboardLineItem

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary/all")
def all_shipments_summary(db: Session = Depends(get_db)):
    """Powers the Dashboard's stat tiles, chart panels, and the History
    listing — one call instead of N+1 round trips per invoice from the
    frontend.

    tatmeen_counts / category_counts are aggregated across every LINE ITEM
    (not per-shipment like `counts` above) — that's the real "how many
    items are reported on Tatmeen" answer the per-shipment overall_status
    can't give, since one shipment can mix reported and not-reported items
    (see rule 16's pharma/non-pharma branching and rule 18's pending-window
    logic in validation_engine.py). tatmeen_counts only reflects pharma
    items that have actually been scanned (a ValidationResult exists) —
    non-pharma items are excluded entirely (Tatmeen doesn't apply to them,
    rule 16), and unscanned pharma items aren't counted as any Tatmeen
    outcome yet since nothing's been checked.
    """
    invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()
    rows = []
    counts = {"green": 0, "yellow": 0, "red": 0, "pending": 0}
    tatmeen_counts = {"green": 0, "yellow": 0, "red": 0}
    category_counts = {"pharma": 0, "non_pharma": 0}

    for inv in invoices:
        statuses = []
        # Same real business rule FinalSummary.tsx uses for its 3-tier
        # verdict (Validated / Completed with Exceptions / Human
        # Intervention Required) - a line only counts as a real "exception"
        # for a genuine invoice/quantity mismatch, a Tatmeen not-reported/
        # failed result, or not being scanned at all. A non-critical finding
        # (near/already-expired stock, a low-confidence-extraction flag)
        # already shows up on its own item row - it shouldn't also drag the
        # WHOLE SHIPMENT down to "yellow" here when every real match/qty/
        # Tatmeen check actually passed. The previous cruder rule ("any
        # line's overall_status is yellow => whole invoice yellow") did
        # exactly that, and it was wrong - confirmed directly: a fully-
        # matched, fully-Tatmeen-reported invoice with only a confidence-
        # review or expiry warning was showing "Warning" here even though
        # FinalSummary would correctly call it "Validation Successful".
        any_unresolved_red = False
        any_exception = False
        any_scanned = False
        for li in inv.line_items:
            category_counts[li.category] = category_counts.get(li.category, 0) + 1
            vr = db.query(ValidationResult).filter(ValidationResult.line_item_id == li.id).first()
            statuses.append(vr.overall_status if vr else "pending")
            if not vr:
                any_exception = True  # not scanned yet
                continue
            any_scanned = True
            if li.category == "pharma" and vr.tatmeen_status in tatmeen_counts:
                tatmeen_counts[vr.tatmeen_status] += 1

            if vr.overall_status == "red" and vr.resolution_action != "accepted":
                any_unresolved_red = True
            mismatched = (vr.invoice_match_status == "red" or vr.quantity_status == "red") and vr.resolution_action != "accepted"
            tatmeen_failed = any(str(f.get("message", "")).startswith("Tatmeen Validation Failed") for f in (vr.findings or []))
            tatmeen_not_reported = vr.tatmeen_status == "red" and not tatmeen_failed
            # SSCC (rule 17) not being reported is a real exception too -
            # it's deliberately a non-critical "yellow" finding at the item
            # level (so the item's own Status dot still reads "Matched"),
            # but that shouldn't let the whole shipment silently read
            # "Validated" when its SSCC genuinely isn't reported.
            sscc_not_reported = vr.sscc_status == "red"
            if mismatched or tatmeen_failed or tatmeen_not_reported or sscc_not_reported:
                any_exception = True

        if not any_scanned:
            overall = "pending"
        elif any_unresolved_red:
            overall = "red"
        elif any_exception:
            overall = "yellow"
        else:
            overall = "green"

        counts[overall] = counts.get(overall, 0) + 1
        rows.append({
            "invoice_number": inv.invoice_number,
            "demo_flow": inv.demo_flow,
            "source": inv.source,
            "supplier": inv.supplier,
            "invoice_date": inv.invoice_date,
            "item_count": len(inv.line_items),
            "scanned_count": sum(1 for s in statuses if s != "pending"),
            "overall_status": overall,
        })

    return {
        "shipments": rows, "counts": counts, "total": len(invoices),
        "tatmeen_counts": tatmeen_counts, "category_counts": category_counts,
    }


@router.get("/{invoice_number}", response_model=DashboardOut)
def get_dashboard(invoice_number: str, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
    if not inv:
        raise HTTPException(404, f"Invoice {invoice_number} not found")

    items = []
    statuses = []
    reasons = []
    for li in inv.line_items:
        vr = db.query(ValidationResult).filter(ValidationResult.line_item_id == li.id).first()
        if vr:
            items.append(DashboardLineItem(
                item_name=li.item_name, category=li.category,
                invoice_status=vr.invoice_match_status, tatmeen_status=vr.tatmeen_status,
                quantity_status=vr.quantity_status, sscc_status=vr.sscc_status,
                overall_status=vr.overall_status,
            ))
            statuses.append(vr.overall_status)
            if vr.overall_status in ("red", "yellow"):
                fail_msgs = [f["message"] for f in vr.findings if f["severity"] in ("fail", "warning")]
                if fail_msgs:
                    reasons.append(f"{li.item_name}: {fail_msgs[0]}")
        else:
            items.append(DashboardLineItem(
                item_name=li.item_name, category=li.category,
                invoice_status="pending", tatmeen_status="n_a",
                quantity_status="pending", sscc_status="n_a", overall_status="pending",
            ))
            statuses.append("pending")

    if any(s == "red" for s in statuses):
        overall = "red"
    elif any(s in ("yellow", "pending") for s in statuses):
        overall = "yellow"
    else:
        overall = "green"

    pharma_count = sum(1 for li in inv.line_items if li.category == "pharma")
    return DashboardOut(
        invoice_number=inv.invoice_number,
        total_items=len(inv.line_items),
        pharma_count=pharma_count,
        non_pharma_count=len(inv.line_items) - pharma_count,
        items=items,
        overall_shipment_status=overall,
        reason="; ".join(reasons) if reasons else None,
    )
