import type { ValidationResult } from "./types";

export type RowStatus = "pending" | "green" | "orange" | "red";

// The main scan table's compact per-item status, per client feedback:
// green = clean match, red = a real GTIN/Batch/Quantity (or other hard)
// mismatch, orange = the item otherwise matches but has an expiry issue
// (already expired, or within the near-expiry window) - worth a reviewer's
// attention without being lumped in with a genuine identity/quantity
// mismatch. Backend confirmation this is grounded in real fields, not
// guessed: rule_expiry_alert (validation_engine.py) only ever appends a
// "10-expiry-alert" finding - it never touches invoice_match_status - so
// an expired item can still show invoice_match_status="green" while
// overall_status goes red/yellow from the finding alone. This function is
// what tells those two real cases apart for the table's single status dot.
// A reviewer's "accepted" override always reads as resolved (green); a
// "rejected" override keeps it red - both are real decisions, not a status
// still awaiting one.
export function rowStatus(result: ValidationResult | undefined): RowStatus {
  if (!result) return "pending";
  if (result.resolution_action === "accepted") return "green";
  if (result.resolution_action === "rejected") return "red";

  const failFindings = result.findings.filter((f) => f.severity === "fail");
  const hasNonExpiryFail = failFindings.some((f) => f.rule !== "10-expiry-alert");
  if (hasNonExpiryFail) return "red";

  const expiryIssue = result.findings.some(
    (f) => f.rule === "10-expiry-alert" && (f.severity === "fail" || f.severity === "warning")
  );
  if (expiryIssue) return "orange";

  return "green";
}

// Every date value coming from the backend is ISO-shaped (YYYY-MM-DD, or
// YYYY-MM when only a month is known - some pharma expiry fields are
// month-only, e.g. seed data's "2028-06"). Display convention across this
// app is dd-mm-yyyy; this is the one place that conversion happens, so
// every date on screen is consistent no matter which field it came from.
export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";

  const full = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (full) {
    const [, yyyy, mm, dd] = full;
    return `${dd}-${mm}-${yyyy}`;
  }

  const monthOnly = value.match(/^(\d{4})-(\d{2})$/);
  if (monthOnly) {
    const [, yyyy, mm] = monthOnly;
    return `${mm}-${yyyy}`; // no day to show - never fabricate one
  }

  return value; // not a recognized date shape - show as-is rather than mangle it
}
