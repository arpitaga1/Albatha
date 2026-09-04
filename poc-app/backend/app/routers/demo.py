"""
Dedicated endpoint reproducing the Round 13-14 SSCC/case-containment
negative-control test (see Claude.md, sscc_negative_control.py) — but now
calling the actual validation_engine.rule_case_containment implementation
that ships in this app, not the standalone R&D script. Proves rule 5 still
catches the same two injected faults inside the real application code.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Invoice, InvoiceLineItem, ScanEvent, SSCCRecord, TatmeenRecord, ValidationResult
from app.services.extraction import ExtractionResult
from app.services.seed_data import seed_all
from app.services.validation_engine import LineItemValidation, rule_case_containment

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/reseed")
def reseed(db: Session = Depends(get_db)):
    """Wipes every table this app writes to and re-runs seed_all(), so the
    system comes back looking exactly like a fresh install - the 7 demo
    invoices + Tatmeen/SSCC dummy data restored, and every scan/validation
    result from prior runs gone. Deleted in FK-dependency order (results and
    scan events before the line items/invoices they point to); Tatmeen and
    SSCC dummy records have no FK to invoices, so order doesn't matter for
    those two. seed_all() is otherwise a no-op once any invoice exists, which
    is exactly why this needs to delete first rather than just calling it
    again."""
    db.query(ValidationResult).delete()
    db.query(ScanEvent).delete()
    db.query(InvoiceLineItem).delete()
    db.query(Invoice).delete()
    db.query(TatmeenRecord).delete()
    db.query(SSCCRecord).delete()
    db.commit()

    seed_all(db)

    return {"status": "reseeded", "invoices": db.query(Invoice).count()}

REAL_ITEM1_SERIALS = [
    "1037937537575", "1068077918463", "1072254253703", "1055969362709",
    "1069150858268", "1029547440017", "1007499603293", "1083054485175",
    "1091890218839", "1067563877542", "1057909533493", "1018278484685",
]


@router.get("/sscc-negative-control")
def sscc_negative_control():
    """Runs both Round 14 fault scenarios against the real Item 1 data and
    returns the findings — a live, re-runnable proof that rule 5 works."""
    expected = set(REAL_ITEM1_SERIALS)

    # Scenario A: foreign serial injected into the case.
    extraction_a = ExtractionResult(
        gtin="00300036120018", batch="2120209",
        serials=REAL_ITEM1_SERIALS + ["1099999999999"],
        case_sscc="1459466A0", mfg_date=None, exp_date="2028-06",
        scanned_qty=13, confidence=0.95, image_quality_ok=True,
    )
    result_a = LineItemValidation()
    rule_case_containment(extraction_a, expected, result_a)

    # Scenario B: one unit's case code doesn't match the rest — simulated
    # by reporting only 11 of the 12 real serials as belonging to this case
    # (the 12th, 1007499603293, is "elsewhere" — a different case), which
    # rule 5 flags as missing even though every serial individually would
    # still match the invoice if checked in isolation.
    scenario_b_serials = [s for s in REAL_ITEM1_SERIALS if s != "1007499603293"]
    extraction_b = ExtractionResult(
        gtin="00300036120018", batch="2120209",
        serials=scenario_b_serials,
        case_sscc="1459466A0", mfg_date=None, exp_date="2028-06",
        scanned_qty=11, confidence=0.95, image_quality_ok=True,
    )
    result_b = LineItemValidation()
    rule_case_containment(extraction_b, expected, result_b)

    return {
        "scenario_a_foreign_serial": {
            "description": "13 units scanned under case 1459466A0 (12 real + 1 fabricated), invoice expects 12.",
            "findings": [f.__dict__ for f in result_a.findings],
        },
        "scenario_b_case_mismatch": {
            "description": "Serial 1007499603293 missing from this case (simulating it being mispacked "
                            "into a different carton) — count and other 11 serials otherwise correct.",
            "findings": [f.__dict__ for f in result_b.findings],
        },
    }
