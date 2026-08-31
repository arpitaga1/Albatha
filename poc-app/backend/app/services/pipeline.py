"""
Orchestrates the client's end-to-end pipeline (requirements doc §13):

  Invoice -> Item/Box Scan -> Image Quality -> Invoice Validation
  -> [Pharma?] -> Tatmeen Validation -> Quantity Validation
  -> SSCC Validation -> Final Shipment Status

Ties together app.services.extraction (produces an ExtractionResult) and
app.services.validation_engine (the 19 rule functions) against one
InvoiceLineItem, using data already committed for that item (prior scans,
matching Tatmeen record, related SSCC records).
"""
from sqlalchemy.orm import Session

from app.models import InvoiceLineItem
from app.services.extraction import ExtractionResult
from app.services import validation_engine as ve
from app.services.tatmeen_adapter import TatmeenAdapter


def run_pipeline(db: Session, line_item: InvoiceLineItem, extraction: ExtractionResult) -> tuple[ve.LineItemValidation, ve.CumulativeScanState]:
    result = ve.LineItemValidation()
    active_scan_events = [se for se in line_item.scan_events if not se.superseded]

    # --- Image quality gate (rule 4) — first, before anything else ---
    quality_ok = ve.rule_image_quality_gate(extraction, result)
    if not quality_ok:
        ve.finalize_overall_status(result)
        cumulative = ve.CumulativeScanState(0, 0, sum(s.scanned_qty for s in active_scan_events), 0, "pending")
        return result, cumulative

    # --- Confidence-weighted review (rule 12) ---
    ve.rule_confidence_review(extraction, result)

    # --- Count verification (rule 1) ---
    ve.rule_count_verification(extraction, result)

    # --- Invoice Validation stage: identity match (rule 2), duplicates (3),
    #     GTIN checksum (6), date sanity (7), expiry alert (10), UOM (9) ---
    ve.rule_identity_matching(line_item, extraction, result)
    ve.rule_duplicate_check(extraction, result)
    ve.rule_gtin_checksum(extraction, result)
    ve.rule_date_sanity(extraction, result)
    ve.rule_expiry_alert(extraction, result)
    ve.rule_uom_consistency(line_item.uom, "EA", result)

    prior_serials: set[str] = set()
    for se in active_scan_events:
        prior_serials.update(se.extracted_serials or [])
    ve.rule_cross_scan_duplicates(prior_serials, extraction.serials, result)
    ve.rule_many_to_many_note(len(active_scan_events) + 1, result)

    # --- Quantity Validation (rule 8), using cumulative tracking (rule 19) ---
    prior_total = sum(se.scanned_qty for se in active_scan_events)
    cumulative = ve.rule_cumulative_scan(line_item.qty, prior_total, extraction.scanned_qty)
    ve.rule_quantity_variance(line_item.qty, cumulative.total_scanned, result, label="Invoice (cumulative)")

    # --- Tatmeen Validation stage (rules 14, 15, 18) — pharma only (rule 16) ---
    # Goes through the TatmeenAdapter exclusively — see tatmeen_adapter.py.
    # A real Tatmeen API integration later only requires changing that one
    # module; nothing here needs to know the difference.
    if ve.is_pharma(line_item):
        adapter = TatmeenAdapter(db)
        check = adapter.check_item(line_item.gtin, line_item.batch, line_item.invoice.invoice_number, line_item.qty)

        if check.failed:
            # "Tatmeen Validation Failed" (spec §9) — the system could not
            # complete the check at all, distinct from a business "not
            # reported" result.
            result.add("14-tatmeen-reported", "fail",
                        f"Tatmeen Validation Failed — the system could not complete this check ({check.failure_reason}).")
            result.tatmeen_status = "red"
        else:
            reported = ve.rule_tatmeen_reported(check.record, result)
            if not reported:
                ve.rule_pending_window(check.record, result)
            else:
                ve.rule_tatmeen_quantity(line_item.qty, check.record.reported_qty, result)

        # --- SSCC Validation stage (rule 17) ---
        if line_item.sscc:
            sscc_records = adapter.check_sscc_hierarchy(line_item.invoice.invoice_number)
            ve.rule_sscc_hierarchy(sscc_records, result)
    else:
        result.tatmeen_status = "n_a"
        result.sscc_status = "n_a"

    ve.finalize_overall_status(result)
    return result, cumulative
