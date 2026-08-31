"""
SAP Data Source abstraction — per the client's explicit instruction:

    "Do not build an actual SAP integration for this POC. Create a clean
    abstraction such as: SAP Data Source -> Invoice Data, so that an actual
    SAP API can be connected later without changing the rest of the
    application."

Everything outside this module (routers, pipeline, frontend) only ever
calls `get_invoices_from_sap()` / `get_invoice_from_sap(invoice_number)` —
never touches seed rows or a real SAP client directly. Swapping this
function's body for a real SAP OData/RFC call later is the only change
needed; nothing downstream needs to know the difference.

Today it returns the same 7 client-demo-flow invoices seeded in
seed_data.py (tagged `source="sap"` in the DB), reframed here as "what SAP
would have sent us" rather than "hardcoded test data" — same underlying
rows, correct framing per this round's spec. When real sample invoices are
provided, replace `seed_data.seed_all`'s SAP-sourced rows; nothing else
needs to change.
"""
import datetime as dt
import random

from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLineItem


def get_invoices_from_sap(db: Session) -> list[Invoice]:
    """Returns every invoice currently sourced from 'SAP' (i.e. seeded, not
    user-uploaded). A real implementation would call SAP here and upsert
    the results into the same Invoice/InvoiceLineItem tables — the rest of
    the app wouldn't need to change."""
    return db.query(Invoice).filter(Invoice.source == "sap").order_by(Invoice.demo_flow).all()


def get_invoice_from_sap(db: Session, invoice_number: str) -> Invoice | None:
    return (
        db.query(Invoice)
        .filter(Invoice.source == "sap", Invoice.invoice_number == invoice_number)
        .first()
    )


# --- Search-any-invoice-number support (per user request) ---
# A real SAP connection would legitimately return SOME record for any valid
# invoice number the warehouse types in — this POC has only ever shipped 8
# fixed dummy invoices, so searching for anything else returned nothing.
# search_or_fetch_invoice reproduces the real experience: an unrecognized
# number gets a genuinely generated (not hand-authored) invoice, persisted
# exactly like any other SAP-sourced invoice, so it runs through the exact
# same wizard/scan/Tatmeen pipeline as the 8 fixed ones — no special-casing
# anywhere else in the app. Tatmeen results for a generated invoice's
# GTIN/Batch combos naturally fall through to TatmeenAdapter's own random
# fallback (nothing pinned for a number nobody chose in advance), which is
# the right behavior here, not a gap.

_SUPPLIERS = [
    "MedSupply Distribution FZE", "Al Noor Pharma Trading", "Global Pharma Logistics LLC",
    "Gulf Health Distributors", "Emirates Pharma Trading Co.",
]

# name, category, uom — batch/GTIN/expiry are generated fresh per invoice
# so two generated invoices for the same product don't collide on identity.
_CATALOG = [
    ("Paracetamol 500mg Tablets", "pharma", "EA"),
    ("Amoxicillin 250mg Capsules", "pharma", "EA"),
    ("Ibuprofen 400mg Tablets", "pharma", "EA"),
    ("Cetirizine 10mg Tablets", "pharma", "EA"),
    ("Vitamin D3 1000IU Softgels", "pharma", "EA"),
    ("Disposable Face Masks (Box of 50)", "non_pharma", "EA"),
    ("Hand Sanitizer 500ml", "non_pharma", "EA"),
    ("Cotton Wool Rolls (Pack of 10)", "non_pharma", "EA"),
    ("Surgical Gloves (Box of 100)", "non_pharma", "EA"),
]


def _random_valid_gtin() -> str:
    """A syntactically real 13-digit-payload GTIN-14 with a correct GS1
    Mod-10 check digit - generated fresh, not pulled from the fixed demo
    set, but still passes rule 6 (gtin_checksum_valid) rather than
    spuriously failing every generated pharma line on a check digit that
    was never real to begin with."""
    payload = [random.randint(0, 9) for _ in range(13)]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(payload)))
    check = (10 - (total % 10)) % 10
    return "".join(map(str, payload)) + str(check)


def _random_line_item() -> InvoiceLineItem:
    name, category, uom = random.choice(_CATALOG)
    qty = random.choice([8, 10, 12, 15, 20, 24, 30, 50])
    expiry_days_out = random.randint(200, 900)  # comfortably not expired/near-expiry
    expiry = (dt.date.today() + dt.timedelta(days=expiry_days_out)).strftime("%Y-%m")
    return InvoiceLineItem(
        item_name=name,
        gtin=_random_valid_gtin() if category == "pharma" else None,
        batch=f"B{random.randint(10000, 99999)}",
        expiry=expiry if category == "pharma" else None,
        qty=qty,
        uom=uom,
        category=category,
    )


def search_or_fetch_invoice(db: Session, invoice_number: str) -> Invoice:
    """Returns the invoice for this number if it already exists (any
    source - a user may search a number they already uploaded or that's
    one of the fixed demo flows); otherwise generates and persists a new
    SAP-sourced one on the spot."""
    existing = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
    if existing:
        return existing

    inv = Invoice(
        invoice_number=invoice_number,
        sold_to="MPC Drug Store Company L.L.C",
        ship_to="Exhibition Showroom No1, Jurf Indus, Ajman",
        supplier=random.choice(_SUPPLIERS),
        invoice_date=dt.date.today().isoformat(),
        demo_flow=None,
        source="sap",
    )
    inv.line_items = [_random_line_item() for _ in range(random.randint(1, 4))]
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv
