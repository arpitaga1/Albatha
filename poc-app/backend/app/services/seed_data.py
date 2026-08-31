"""
Seeds the SQLite DB with the 7 client demo-flow invoices + a matching
Tatmeen dummy dataset + SSCC hierarchy records, per the client's
requirements doc and Claude.md Round 15.

Item 1's data (GTIN 00300036120018 / Batch 2120209 / 12 real serials) is the
actual data validated in Rounds 1-14 against Picture1.png — reused here for
continuity. Everything else follows the client's own "Item 1 / Item 2 / B1 /
B2 / GTIN001..." demo convention from their requirements doc, since that's
what they specified.

Flow 3 is the OCR-fallback scenario proposed in Claude.md Round 15 —
NOT client-confirmed. Clearly labeled as a proposal in the seeded invoice
number's description.

Product names (Round 20): renamed from generic "Item 1/2/3" to realistic
pharma/non-pharma product names, per user request, so the demo reads like a
real pharmacy shipment rather than a labeled test fixture. Naming is kept
consistent by GTIN/batch across every invoice the same product appears in —
GTIN 00300036120018/Batch 2120209 is always "Paracetamol 500mg Tablets",
wherever it shows up.
"""
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLineItem, ScanEvent, TatmeenRecord, SSCCRecord, ValidationResult
from app.services.extraction import ExtractionResult
from app.services.pipeline import run_pipeline

# Consistent product names, keyed by the identifier that recurs across flows.
PARACETAMOL = "Paracetamol 500mg Tablets"       # GTIN 00300036120018 / Batch 2120209 — real Item 1 data
AMOXICILLIN = "Amoxicillin 250mg Capsules"       # GTIN 00800000200024 / Batch B2
IBUPROFEN = "Ibuprofen 400mg Tablets"            # GTIN 00800000300038 / Batch B3
VITAMIN_C = "Vitamin C 1000mg Effervescent Tablets"  # OCR-fallback item, no GTIN
FACE_MASKS = "Disposable Face Masks (Box of 50)"     # non-pharma
HAND_SANITIZER = "Hand Sanitizer 500ml"              # non-pharma
COTTON_WOOL = "Cotton Wool Rolls (Pack of 10)"       # non-pharma


def seed_all(db: Session) -> None:
    if db.query(Invoice).count() > 0:
        return  # already seeded

    # ---- Flow 1: all pharma items reported ----
    inv1 = Invoice(invoice_number="INV001", sold_to="MPC Drug Store Company L.L.C",
                    ship_to="Exhibition Showroom No1, Jurf Indus, Ajman",
                    invoice_date="2026-08-19", demo_flow=1, source="sap", supplier="MedSupply Distribution FZE")
    inv1.line_items = [
        InvoiceLineItem(item_name=PARACETAMOL, gtin="00300036120018", batch="2120209",
                         expiry="2028-06", qty=12, uom="EA", category="pharma"),
        InvoiceLineItem(item_name=AMOXICILLIN, gtin="00800000200024", batch="B2",
                         expiry="2027-06", qty=10, uom="EA", category="pharma"),
    ]

    # ---- Flow 2: one pharma item not reported ----
    inv2 = Invoice(invoice_number="INV002", sold_to="MPC Drug Store Company L.L.C",
                    ship_to="Exhibition Showroom No1, Jurf Indus, Ajman",
                    invoice_date="2026-08-19", demo_flow=2, source="sap", supplier="MedSupply Distribution FZE")
    inv2.line_items = [
        InvoiceLineItem(item_name=PARACETAMOL, gtin="00300036120018", batch="2120209",
                         expiry="2028-06", qty=12, uom="EA", category="pharma"),
        InvoiceLineItem(item_name=AMOXICILLIN, gtin="00800000200024", batch="B2",
                         expiry="2027-06", qty=10, uom="EA", category="pharma"),
    ]

    # ---- Flow 3 (RESERVED — proposed OCR-fallback demo, unconfirmed) ----
    inv3 = Invoice(invoice_number="INV003", sold_to="MPC Drug Store Company L.L.C",
                    ship_to="Exhibition Showroom No1, Jurf Indus, Ajman",
                    invoice_date="2026-08-19", demo_flow=3, source="sap", supplier="Global Pharma Logistics LLC")
    inv3.line_items = [
        InvoiceLineItem(item_name=f"{VITAMIN_C} (damaged barcode, OCR fallback)", gtin=None,
                         batch="OCR-B5", expiry="2027-05", qty=1, uom="EA", category="pharma"),
    ]

    # ---- Flow 4: SSCC reported ----
    inv4 = Invoice(invoice_number="INV004", sold_to="MPC Drug Store Company L.L.C",
                    ship_to="Exhibition Showroom No1, Jurf Indus, Ajman",
                    invoice_date="2026-08-19", demo_flow=4, source="sap", supplier="Al Noor Pharma Trading")
    inv4.line_items = [
        InvoiceLineItem(item_name=PARACETAMOL, gtin="00300036120018", batch="2120209",
                         expiry="2028-06", qty=12, uom="EA", category="pharma"),
        InvoiceLineItem(item_name=AMOXICILLIN, gtin="00800000200024", batch="B2",
                         expiry="2027-06", qty=10, uom="EA", category="pharma"),
        InvoiceLineItem(item_name=IBUPROFEN, gtin="00800000300038", batch="B3",
                         expiry="2027-09", qty=12, uom="EA", category="pharma",
                         sscc="SSCC-CHILD-001"),
    ]

    # ---- Flow 5: SSCC not reported ----
    inv5 = Invoice(invoice_number="INV005", sold_to="MPC Drug Store Company L.L.C",
                    ship_to="Exhibition Showroom No1, Jurf Indus, Ajman",
                    invoice_date="2026-08-19", demo_flow=5, source="sap", supplier="Al Noor Pharma Trading")
    inv5.line_items = [
        InvoiceLineItem(item_name=PARACETAMOL, gtin="00300036120018", batch="2120209",
                         expiry="2028-06", qty=12, uom="EA", category="pharma"),
        InvoiceLineItem(item_name=AMOXICILLIN, gtin="00800000200024", batch="B2",
                         expiry="2027-06", qty=10, uom="EA", category="pharma"),
        InvoiceLineItem(item_name=IBUPROFEN, gtin="00800000300038", batch="B3",
                         expiry="2027-09", qty=8, uom="EA", category="pharma",
                         sscc="SSCC-CHILD-999"),
    ]

    # ---- Flow 6: mixed pharma (reported + not) + non-pharma ----
    inv6 = Invoice(invoice_number="INV006", sold_to="MPC Drug Store Company L.L.C",
                    ship_to="Exhibition Showroom No1, Jurf Indus, Ajman",
                    invoice_date="2026-08-19", demo_flow=6, source="sap", supplier="MedSupply Distribution FZE")
    inv6.line_items = [
        InvoiceLineItem(item_name=PARACETAMOL, gtin="00300036120018", batch="2120209",
                         expiry="2028-06", qty=12, uom="EA", category="pharma"),
        InvoiceLineItem(item_name=AMOXICILLIN, gtin="00800000200024", batch="B2",
                         expiry="2027-06", qty=10, uom="EA", category="pharma"),
        InvoiceLineItem(item_name=FACE_MASKS, gtin=None, batch="B3",
                         expiry=None, qty=100, uom="EA", category="non_pharma"),
    ]

    # ---- Flow 7: non-pharma only ----
    inv7 = Invoice(invoice_number="INV007", sold_to="MPC Drug Store Company L.L.C",
                    ship_to="Exhibition Showroom No1, Jurf Indus, Ajman",
                    invoice_date="2026-08-19", demo_flow=7, source="sap", supplier="General Trading Supplies Co.")
    inv7.line_items = [
        InvoiceLineItem(item_name=HAND_SANITIZER, gtin=None, batch="B1",
                         expiry=None, qty=100, uom="EA", category="non_pharma"),
        InvoiceLineItem(item_name=COTTON_WOOL, gtin=None, batch="B2",
                         expiry=None, qty=100, uom="EA", category="non_pharma"),
    ]

    # ---- Bonus (not one of the client's 7 flows): Pending status demo ----
    # Proves rule 18's pending-vs-failed branch actually works, not just
    # designed-on-paper — mirrors how rule 5's SSCC logic got a dedicated
    # negative-control proof (see app/routers/demo.py) rather than trusting
    # it untested.
    inv8 = Invoice(invoice_number="INV008", sold_to="MPC Drug Store Company L.L.C",
                    ship_to="Exhibition Showroom No1, Jurf Indus, Ajman",
                    invoice_date="2026-08-19", demo_flow=None, source="sap", supplier="MedSupply Distribution FZE")
    inv8.line_items = [
        InvoiceLineItem(item_name=f"{PARACETAMOL} (Tatmeen reporting in progress)", gtin="00300036120018",
                         batch="2120209", expiry="2028-06", qty=12, uom="EA", category="pharma"),
    ]

    for inv in (inv1, inv2, inv3, inv4, inv5, inv6, inv7, inv8):
        db.add(inv)
    db.commit()

    # ---- Tatmeen dummy database (client doc §8 shape) ----
    tatmeen_rows = [
        # Flow 1 & 4 & 6: Paracetamol reported, matches invoice qty exactly.
        TatmeenRecord(gtin="00300036120018", batch="2120209", serial=None,
                      invoice_number="INV001", reported=True, reported_qty=12,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-17"),
        TatmeenRecord(gtin="00300036120018", batch="2120209", serial=None,
                      invoice_number="INV002", reported=True, reported_qty=12,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-17"),
        TatmeenRecord(gtin="00300036120018", batch="2120209", serial=None,
                      invoice_number="INV004", reported=True, reported_qty=12,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-17"),
        TatmeenRecord(gtin="00300036120018", batch="2120209", serial=None,
                      invoice_number="INV005", reported=True, reported_qty=12,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-17"),
        TatmeenRecord(gtin="00300036120018", batch="2120209", serial=None,
                      invoice_number="INV006", reported=True, reported_qty=12,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-17"),

        # Flow 1 & 4: Amoxicillin reported, matches.
        TatmeenRecord(gtin="00800000200024", batch="B2", serial=None,
                      invoice_number="INV001", reported=True, reported_qty=10,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-17"),
        TatmeenRecord(gtin="00800000200024", batch="B2", serial=None,
                      invoice_number="INV004", reported=True, reported_qty=10,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-17"),
        TatmeenRecord(gtin="00800000200024", batch="B2", serial=None,
                      invoice_number="INV005", reported=True, reported_qty=10,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-17"),

        # Flow 2 & 6: Amoxicillin NOT reported.
        TatmeenRecord(gtin="00800000200024", batch="B2", serial=None,
                      invoice_number="INV002", reported=False, reported_qty=0,
                      sscc=None, sscc_reported=False, reporting_date=None),
        TatmeenRecord(gtin="00800000200024", batch="B2", serial=None,
                      invoice_number="INV006", reported=False, reported_qty=0,
                      sscc=None, sscc_reported=False, reporting_date=None),

        # Flow 4: Ibuprofen reported, SSCC reported.
        TatmeenRecord(gtin="00800000300038", batch="B3", serial=None,
                      invoice_number="INV004", reported=True, reported_qty=12,
                      sscc="SSCC-CHILD-001", sscc_reported=True, reporting_date="2026-08-17"),

        # Flow 5: Ibuprofen reported at item level, but its SSCC is NOT reported.
        TatmeenRecord(gtin="00800000300038", batch="B3", serial=None,
                      invoice_number="INV005", reported=True, reported_qty=8,
                      sscc="SSCC-CHILD-999", sscc_reported=False, reporting_date="2026-08-17"),

        # Bonus (INV008): not yet reported, but Tatmeen shows activity
        # (reporting_date set) — this is what makes rule 18 classify it as
        # Pending rather than Failed. Compare to INV002/INV006 above, which
        # have reporting_date=None and correctly resolve to a hard fail.
        TatmeenRecord(gtin="00300036120018", batch="2120209", serial=None,
                      invoice_number="INV008", reported=False, reported_qty=0,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-18"),

        # Flow 3: OCR-fallback item — matched on Batch+Serial, no GTIN.
        TatmeenRecord(gtin=None, batch="OCR-B5", serial="OCR-SN-000451",
                      invoice_number="INV003", reported=True, reported_qty=1,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-18"),

        # TEST-INV-001 (Test_Invoice_Item1_Item2.pdf, real uploaded-invoice
        # fixture, not one of the 7 SAP demo flows) — pinned explicitly
        # rather than left to the GTIN+Batch fallback match, per user
        # directive: Item 1 reported, Item 2 not reported, and this
        # specific pairing must stay stable regardless of what else is
        # seeded elsewhere. invoice_number-scoped, so it doesn't collide
        # with 206204905 below even though both now genuinely ship the
        # SAME GTIN+Batch (4I016) for their second line — confirmed by the
        # user as the real batch on both real invoices — with two
        # deliberately different Tatmeen outcomes; invoice-scoped matching
        # is exactly what keeps these independent.
        TatmeenRecord(gtin="00300036120018", batch="2120209", serial=None,
                      invoice_number="TEST-INV-001", reported=True, reported_qty=12,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-20"),
        TatmeenRecord(gtin="03664798023251", batch="4I016", serial=None,
                      invoice_number="TEST-INV-001", reported=False, reported_qty=0,
                      sscc=None, sscc_reported=False, reporting_date=None),

        # 206204905 (Invoice_ProductA96_ProductC20.pdf, real uploaded-invoice
        # fixture) — per user directive: BOTH items reported. Product A is
        # the 96-unit MF1204-batch carton, Product C's batch is "4I016" —
        # confirmed by the user as the real, genuine batch code printed on
        # this invoice (a letter I, not a misread digit 1 — deliberately
        # NOT normalized by real_extraction.py's invoice parsers, which
        # take invoice batch text verbatim for exactly this reason). Not
        # the same batch as TEST-INV-001's Item 2 ("41016", Picture2.png's
        # real photographed data) even though both share this GTIN.
        TatmeenRecord(gtin="00840149658751", batch="MF1204", serial=None,
                      invoice_number="206204905", reported=True, reported_qty=96,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-20"),
        TatmeenRecord(gtin="03664798023251", batch="4I016", serial=None,
                      invoice_number="206204905", reported=True, reported_qty=20,
                      sscc=None, sscc_reported=False, reporting_date="2026-08-20"),
    ]
    db.add_all(tatmeen_rows)

    # ---- SSCC hierarchy records (rule 17) ----
    sscc_rows = [
        SSCCRecord(sscc_code="SSCC-MASTER-001", parent_sscc=None,
                   invoice_number="INV004", item_qty=12, reported=True),
        SSCCRecord(sscc_code="SSCC-CHILD-001", parent_sscc="SSCC-MASTER-001",
                   invoice_number="INV004", item_qty=12, reported=True),

        SSCCRecord(sscc_code="SSCC-MASTER-999", parent_sscc=None,
                   invoice_number="INV005", item_qty=8, reported=True),
        SSCCRecord(sscc_code="SSCC-CHILD-999", parent_sscc="SSCC-MASTER-999",
                   invoice_number="INV005", item_qty=8, reported=False),
    ]
    db.add_all(sscc_rows)
    db.commit()

    # ---- Baseline scans, so the Dashboard isn't all-zero on first load ----
    # Runs the REAL pipeline (same rules, same Tatmeen lookups a live scan
    # would use) against a subset of the invoices above, with an
    # ExtractionResult built from each line item's own invoice-declared
    # data — a "perfect scan" that exactly matches the invoice. This isn't
    # fabricated data: every resulting status is genuinely computed by the
    # same code path a real scan takes, just run proactively at seed time
    # instead of waiting for a user to click through the wizard. Marked
    # with the existing "mock:" image_ref sentinel (already used by the
    # /scans/mock endpoint) so it's honestly labeled as seeded, not a real
    # photo, if anyone inspects it.
    #
    # Deliberately only 4 of the 8 invoices (INV001/002/006/007) — a mix
    # chosen to give the dashboard's tiles and Tatmeen chart a realistic
    # spread (validated, exceptions, reported, not-reported) without
    # pre-scanning every invoice, which would leave nothing for a live
    # demo walkthrough. INV003/004/005/008 stay untouched specifically
    # because they're the more interesting ones to click through live
    # (OCR fallback, SSCC hierarchy, Tatmeen pending window).
    for line_item in (*inv1.line_items, *inv2.line_items, *inv6.line_items, *inv7.line_items):
        extraction = ExtractionResult(
            gtin=line_item.gtin, batch=line_item.batch, serials=[], case_sscc=None,
            mfg_date=None, exp_date=line_item.expiry, scanned_qty=line_item.qty,
            confidence=1.0, image_quality_ok=True,
            notes=["Pre-seeded baseline scan for dashboard realism — matches invoice exactly."],
        )
        result, _cumulative = run_pipeline(db, line_item, extraction)
        db.add(ScanEvent(
            invoice_id=line_item.invoice_id, line_item_id=line_item.id,
            image_ref=f"mock:seed-baseline-{line_item.id}",
            extracted_gtin=extraction.gtin, extracted_batch=extraction.batch,
            extracted_expiry=extraction.exp_date, extracted_serials=extraction.serials,
            case_sscc=extraction.case_sscc, scanned_qty=extraction.scanned_qty,
            confidence=extraction.confidence, image_quality_ok=extraction.image_quality_ok,
            notes=extraction.notes,
        ))
        db.add(ValidationResult(
            invoice_id=line_item.invoice_id, line_item_id=line_item.id,
            invoice_match_status=result.invoice_match_status, tatmeen_status=result.tatmeen_status,
            quantity_status=result.quantity_status, sscc_status=result.sscc_status,
            overall_status=result.overall_status,
            findings=[{"rule": f.rule, "severity": f.severity, "message": f.message} for f in result.findings],
        ))
    db.commit()
