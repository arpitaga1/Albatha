"""
Validation rule engine — implements all 19 rules from Claude.md's "Full
Validation Rule Set" and orchestrates them into the client's pipeline:

  Invoice → Item/Box Scan → Invoice Validation → Tatmeen Validation
          → Quantity Validation → SSCC Validation → Final Shipment Status

Rules 1-5 have prior working reference implementations proven in R&D
(Claude.md Rounds 1-14, and sscc_negative_control.py for rule 5 specifically)
— reimplemented here as real, callable functions, not stubs. Rules 6-19 are
new for this build, translating the designs already written up in Claude.md.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from app import config
from app.services.extraction import ExtractionResult


@dataclass
class Finding:
    rule: str
    severity: str  # "pass" | "info" | "warning" | "fail"
    message: str


@dataclass
class LineItemValidation:
    invoice_match_status: str = "pending"   # green | red | pending
    tatmeen_status: str = "n_a"             # green | yellow | red | n_a
    quantity_status: str = "pending"        # green | red | pending
    sscc_status: str = "n_a"                # green | yellow | red | n_a
    overall_status: str = "pending"         # green | yellow | red | pending
    findings: list[Finding] = field(default_factory=list)

    def add(self, rule: str, severity: str, message: str):
        self.findings.append(Finding(rule, severity, message))


# ---------------------------------------------------------------------
# Rule 1 — Count verification
# ---------------------------------------------------------------------
def rule_count_verification(extraction: ExtractionResult, result: LineItemValidation) -> None:
    method = "serial-count cross-check" if extraction.serials else "declared scan quantity"
    if extraction.serials and len(extraction.serials) != extraction.scanned_qty:
        result.add(
            "1-count-verification", "warning",
            f"Scanned quantity ({extraction.scanned_qty}) does not match the number of "
            f"distinct serials found ({len(extraction.serials)}) — treat count as provisional.",
        )
    else:
        result.add(
            "1-count-verification", "pass",
            f"Count = {extraction.scanned_qty} (method: {method}, confidence "
            f"{extraction.confidence:.0%}).",
        )


# ---------------------------------------------------------------------
# Rule 2 — Identity matching hierarchy (GTIN -> Serial, Round 15-confirmed)
# ---------------------------------------------------------------------
def rule_identity_matching(line_item, extraction: ExtractionResult, result: LineItemValidation) -> bool:
    if line_item.gtin and extraction.gtin:
        matched = line_item.gtin == extraction.gtin
        key = "GTIN"
    elif extraction.serials:
        # GTIN missing on one side -> fall back to serial number (Round 15 directive)
        matched = True  # serial presence itself is the match signal at this stage;
        # exact per-unit serial reconciliation happens in rule 5/11.
        key = "Serial Number (GTIN unavailable — fallback per Round 15 directive)"
    else:
        matched = bool(line_item.batch and extraction.batch and line_item.batch == extraction.batch)
        key = "Batch Code (GTIN and Serial both unavailable — extraction-side fallback, Round 9)"

    if matched and line_item.batch != extraction.batch and extraction.batch is not None:
        matched = False
        result.add("2-identity-matching", "fail",
                    f"Batch mismatch: invoice expects '{line_item.batch}', scan found '{extraction.batch}'.")
    elif matched:
        result.add("2-identity-matching", "pass", f"Identity matched on {key}.")
    else:
        result.add("2-identity-matching", "fail", f"No identity match found (checked {key}).")

    result.invoice_match_status = "green" if matched else "red"
    return matched


# ---------------------------------------------------------------------
# Rule 3 — Duplicate-serial integrity check (within one scan)
# ---------------------------------------------------------------------
def rule_duplicate_check(extraction: ExtractionResult, result: LineItemValidation) -> None:
    if not extraction.serials:
        return
    seen = set()
    dupes = set()
    for s in extraction.serials:
        (dupes if s in seen else seen).add(s)
    if dupes:
        result.add("3-duplicate-check", "fail",
                    f"Duplicate serial(s) within this scan: {sorted(dupes)} — possible double-scan or misread.")
    else:
        result.add("3-duplicate-check", "pass", "All serials in this scan are distinct.")


# ---------------------------------------------------------------------
# Rule 4 — Image-quality gate
# ---------------------------------------------------------------------
def rule_image_quality_gate(extraction: ExtractionResult, result: LineItemValidation) -> bool:
    if not extraction.image_quality_ok:
        suggestion = next((n for n in extraction.notes if "reupload" in n.lower() or "retake" in n.lower()),
                           "Please retake or re-upload a clearer photo.")
        result.add("4-image-quality-gate", "fail",
                    f"Image not clear enough to validate the item. {suggestion}")
        return False
    result.add("4-image-quality-gate", "pass", "Image quality acceptable.")
    return True


# ---------------------------------------------------------------------
# Rule 5 — Case/SSCC containment check
# (reference logic proven in sscc_negative_control.py, Round 13-14)
# ---------------------------------------------------------------------
def rule_case_containment(extraction: ExtractionResult, expected_serials: set[str],
                           result: LineItemValidation) -> None:
    if not extraction.case_sscc or not extraction.serials:
        return
    scanned = set(extraction.serials)
    extra = scanned - expected_serials
    missing = expected_serials - scanned
    if extra:
        result.add("5-case-containment", "fail",
                    f"Unexpected serial(s) found in case {extraction.case_sscc}, not on invoice: {sorted(extra)}.")
    if missing:
        result.add("5-case-containment", "fail",
                    f"Serial(s) expected in case {extraction.case_sscc} but not found in scan: {sorted(missing)}.")
    if not extra and not missing:
        result.add("5-case-containment", "pass",
                    f"Case {extraction.case_sscc} contents match invoice exactly ({len(scanned)} units).")


# ---------------------------------------------------------------------
# Rule 6 — GTIN check-digit (Mod-10 / GS1) validation
# ---------------------------------------------------------------------
def gtin_checksum_valid(gtin: str) -> bool:
    digits = [int(c) for c in gtin if c.isdigit()]
    if len(digits) not in (8, 12, 13, 14):
        return False
    payload, check = digits[:-1], digits[-1]
    payload = payload[::-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(payload))
    return (10 - (total % 10)) % 10 == check


def rule_gtin_checksum(extraction: ExtractionResult, result: LineItemValidation) -> None:
    if not extraction.gtin:
        return
    if gtin_checksum_valid(extraction.gtin):
        result.add("6-gtin-checksum", "pass", "GTIN check digit is valid.")
    else:
        result.add("6-gtin-checksum", "warning",
                    f"GTIN '{extraction.gtin}' fails its check-digit — likely an OCR misread, verify manually.")


# ---------------------------------------------------------------------
# Rule 7 — Mfg-before-Exp sanity check
# ---------------------------------------------------------------------
def _parse_partial_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = dt.datetime.strptime(s, fmt)
            return parsed.date()
        except ValueError:
            continue
    return None


def rule_date_sanity(extraction: ExtractionResult, result: LineItemValidation) -> None:
    mfg, exp = _parse_partial_date(extraction.mfg_date), _parse_partial_date(extraction.exp_date)
    if mfg and exp:
        if mfg >= exp:
            result.add("7-date-sanity", "fail",
                        f"Manufacture date ({extraction.mfg_date}) is not before expiry ({extraction.exp_date}) — likely a misread.")
        else:
            result.add("7-date-sanity", "pass", "Manufacture date precedes expiry date.")


# ---------------------------------------------------------------------
# Rule 8 — Signed quantity variance reporting
# ---------------------------------------------------------------------
def rule_quantity_variance(expected: int, actual: int, result: LineItemValidation, label="Invoice") -> bool:
    diff = actual - expected
    if diff == 0:
        result.add("8-quantity-variance", "pass", f"{label} quantity matched: {actual}.")
        result.quantity_status = "green"
        return True
    direction = "over" if diff > 0 else "short"
    result.add("8-quantity-variance", "fail",
                f"{label} quantity mismatch: expected {expected}, found {actual} ({direction} by {abs(diff)}).")
    result.quantity_status = "red"
    return False


# ---------------------------------------------------------------------
# Rule 9 — UOM consistency check
# ---------------------------------------------------------------------
def rule_uom_consistency(invoice_uom: str, scan_implies_uom: str, result: LineItemValidation) -> None:
    if invoice_uom.upper() != scan_implies_uom.upper():
        result.add("9-uom-consistency", "warning",
                    f"Unit mismatch: invoice is in {invoice_uom}, scan appears to be counting {scan_implies_uom} "
                    "— verify before trusting the quantity comparison.")
    else:
        result.add("9-uom-consistency", "pass", f"Units consistent ({invoice_uom}).")


# ---------------------------------------------------------------------
# Rule 10 — Expired / near-expiry flag
# ---------------------------------------------------------------------
def rule_expiry_alert(extraction: ExtractionResult, result: LineItemValidation,
                       near_expiry_days: int = 90, today: dt.date | None = None) -> None:
    exp = _parse_partial_date(extraction.exp_date)
    if not exp:
        return
    today = today or dt.date.today()
    if exp < today:
        result.add("10-expiry-alert", "fail", f"Stock is already expired (expiry {extraction.exp_date}).")
    elif (exp - today).days <= near_expiry_days:
        result.add("10-expiry-alert", "warning",
                    f"Stock is within {near_expiry_days} days of expiry ({extraction.exp_date}).")
    else:
        result.add("10-expiry-alert", "pass", "Not expired, not near-expiry.")


# ---------------------------------------------------------------------
# Rule 11 — Cross-photo duplicate detection
# ---------------------------------------------------------------------
def rule_cross_scan_duplicates(all_prior_serials: set[str], new_serials: list[str],
                                result: LineItemValidation) -> None:
    overlap = all_prior_serials & set(new_serials)
    if overlap:
        result.add("11-cross-scan-duplicates", "fail",
                    f"Serial(s) already counted in a previous scan for this line: {sorted(overlap)} "
                    "— likely the same physical box scanned twice.")
    else:
        result.add("11-cross-scan-duplicates", "pass", "No overlap with previously scanned serials.")


# ---------------------------------------------------------------------
# Rule 12 — Confidence-weighted auto-approval
# ---------------------------------------------------------------------
def rule_confidence_review(extraction: ExtractionResult, result: LineItemValidation) -> bool:
    """Returns True if auto-approved, False if routed to manual review."""
    if extraction.confidence < config.CONFIDENCE_THRESHOLD:
        result.add("12-confidence-review", "warning",
                    f"Extraction confidence {extraction.confidence:.0%} is below the "
                    f"{config.CONFIDENCE_THRESHOLD:.0%} auto-approval threshold — routed to manual review.")
        return False
    result.add("12-confidence-review", "pass",
                f"Extraction confidence {extraction.confidence:.0%} — auto-approved.")
    return True


# ---------------------------------------------------------------------
# Rule 13 — Many-to-many matching
# Structurally enabled by the schema (ScanEvent.line_item_id is a FK, so
# multiple scans can map to one line, and a shipment can span multiple
# invoices sharing a batch/GTIN at the query layer) — this helper just
# reports on it explicitly so it shows up as a checked rule, not silently
# assumed.
# ---------------------------------------------------------------------
def rule_many_to_many_note(scan_count_for_line: int, result: LineItemValidation) -> None:
    result.add("13-many-to-many", "info",
                f"{scan_count_for_line} scan(s) recorded against this line item — "
                "schema supports multiple scans per line and multiple lines per invoice.")


# ---------------------------------------------------------------------
# Rule 14 — Tatmeen reported-status check (pharma only)
#
# Deliberately does NOT record a "fail" finding itself when not reported —
# that decision belongs to rule 18 (pending-window), which distinguishes a
# genuine failure from "still within the grace period." Recording "fail"
# here unconditionally caused a real bug during testing: Flow 2's demo item
# (seeded as definitively not-reported, no reporting_date at all) showed
# tatmeen_status=yellow (from rule 18 running after) while overall_status
# was still red (from this rule's finding) — a contradictory-looking
# dashboard result. Splitting the decision fixes it.
# ---------------------------------------------------------------------
def rule_tatmeen_reported(tatmeen_record, result: LineItemValidation) -> bool:
    if tatmeen_record is not None and tatmeen_record.reported:
        result.add("14-tatmeen-reported", "pass", "Item is reported in Tatmeen.")
        return True
    return False


# ---------------------------------------------------------------------
# Rule 15 — Tatmeen quantity validation (configurable exact vs gte)
# ---------------------------------------------------------------------
def rule_tatmeen_quantity(invoice_qty: int, tatmeen_qty: int, result: LineItemValidation) -> None:
    ok = (tatmeen_qty >= invoice_qty) if config.TATMEEN_QTY_MODE == "gte" else (tatmeen_qty == invoice_qty)
    if ok:
        result.add("15-tatmeen-quantity", "pass",
                    f"Tatmeen quantity ({tatmeen_qty}) satisfies invoice quantity ({invoice_qty}), "
                    f"mode={config.TATMEEN_QTY_MODE}.")
        result.tatmeen_status = "green"
    else:
        result.add("15-tatmeen-quantity", "fail",
                    f"Tatmeen quantity ({tatmeen_qty}) does not satisfy invoice quantity ({invoice_qty}), "
                    f"mode={config.TATMEEN_QTY_MODE}. Manual intervention required.")
        result.tatmeen_status = "red"


# ---------------------------------------------------------------------
# Rule 16 — Pharma / Non-Pharma conditional branching
# ---------------------------------------------------------------------
def is_pharma(line_item) -> bool:
    return line_item.category == "pharma"


# ---------------------------------------------------------------------
# Rule 17 — SSCC hierarchy validation (master/child)
# ---------------------------------------------------------------------
def rule_sscc_hierarchy(sscc_records: list, result: LineItemValidation) -> None:
    """sscc_records: all SSCCRecord rows relevant to this shipment/line."""
    if not sscc_records:
        return
    children = [r for r in sscc_records if r.parent_sscc]
    masters = {r.sscc_code: r for r in sscc_records if not r.parent_sscc}

    not_reported = [r for r in sscc_records if not r.reported]
    if not_reported:
        codes = [r.sscc_code for r in not_reported]
        result.add("17-sscc-hierarchy", "fail", f"SSCC not reported in Tatmeen: {codes}.")
        result.sscc_status = "red"
        return

    for parent_code, master in masters.items():
        child_sum = sum(c.item_qty for c in children if c.parent_sscc == parent_code)
        if children and child_sum != master.item_qty:
            result.add("17-sscc-hierarchy", "fail",
                        f"Child SSCC quantities under {parent_code} sum to {child_sum}, "
                        f"master SSCC declares {master.item_qty}.")
            result.sscc_status = "red"
            return

    result.add("17-sscc-hierarchy", "pass", "SSCC reported and quantity hierarchy is consistent.")
    result.sscc_status = "green"


# ---------------------------------------------------------------------
# Rule 18 — Time-window Pending-status logic
#
# Called only when rule 14 found the item NOT reported. Makes the actual
# fail-vs-pending call and records the one finding that decides
# tatmeen_status for this case (see the note on rule 14 above for why the
# finding moved here). "Pending" requires positive evidence the item is
# genuinely mid-pipeline (a reporting_date present despite reported=False —
# e.g. Tatmeen has acknowledged receipt but not yet confirmed). No evidence
# at all (reporting_date is None) means a hard fail, not an assumed grace
# period — matches every one of the client's 7 demo flows, which all expect
# a deterministic red result for "not reported," never a yellow one.
# ---------------------------------------------------------------------
def rule_pending_window(tatmeen_record, result: LineItemValidation, today: dt.date | None = None) -> bool:
    """Returns True if pending (not a hard failure), False if a genuine failure."""
    if tatmeen_record is not None and tatmeen_record.reporting_date:
        today = today or dt.date.today()
        result.add("18-pending-window", "info",
                    f"Not yet confirmed reported, but Tatmeen shows activity as of "
                    f"{tatmeen_record.reporting_date} — within the assumed "
                    f"{config.TATMEEN_GRACE_DAYS}-day reporting grace window "
                    "(window length unconfirmed with client — Claude.md open question #5).")
        result.tatmeen_status = "yellow"
        return True

    batch = tatmeen_record.batch if tatmeen_record is not None else "unknown"
    result.add("18-pending-window", "fail",
                f"Item is not reported in Tatmeen for Batch {batch}. Manual intervention required.")
    result.tatmeen_status = "red"
    return False


# ---------------------------------------------------------------------
# Rule 19 — Cumulative / partial-scan tracking
# ---------------------------------------------------------------------
@dataclass
class CumulativeScanState:
    previously_scanned: int
    current_scan: int
    total_scanned: int
    remaining: int
    status: str  # "green" | "pending"


def rule_cumulative_scan(invoice_qty: int, prior_total: int, current_scan_qty: int) -> CumulativeScanState:
    total = prior_total + current_scan_qty
    remaining = max(invoice_qty - total, 0)
    status = "green" if total >= invoice_qty else "pending"
    return CumulativeScanState(
        previously_scanned=prior_total, current_scan=current_scan_qty,
        total_scanned=total, remaining=remaining, status=status,
    )


# ---------------------------------------------------------------------
# Orchestration — the client's end-to-end pipeline (requirements doc §13)
# ---------------------------------------------------------------------
def finalize_overall_status(result: LineItemValidation) -> None:
    if any(f.severity == "fail" for f in result.findings):
        result.overall_status = "red"
    elif result.tatmeen_status == "yellow":
        result.overall_status = "yellow"
    elif any(f.severity == "warning" for f in result.findings):
        result.overall_status = "yellow"
    else:
        result.overall_status = "green"
