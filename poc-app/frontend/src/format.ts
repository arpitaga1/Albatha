import type { ValidationResult } from "./types";

export type RowStatus = "pending" | "green" | "orange" | "red";

// The main scan table's compact per-item status, per client feedback:
// green = clean match, red = "Manual Intervention Required" (a real
// item-count/GTIN/batch/serial-number mismatch - the only things the
// backend's finalize_overall_status treats as red-worthy), orange = any
// other real issue (expiry, date-sanity, Tatmeen reporting, SSCC, ...) -
// worth a reviewer's attention without being lumped in with a genuine
// identity/quantity mismatch. Deliberately just mirrors the backend's own
// overall_status (validation_engine.py's finalize_overall_status is the
// single source of truth for red-vs-yellow) rather than re-deriving the
// same classification independently here. A reviewer's "accepted"
// override always reads as resolved (green); a "rejected" override keeps
// it red - both are real decisions, not a status still awaiting one.
export function rowStatus(result: ValidationResult | undefined): RowStatus {
  if (!result) return "pending";
  if (result.resolution_action === "accepted") return "green";
  if (result.resolution_action === "rejected") return "red";

  if (result.overall_status === "red") return "red";
  if (result.overall_status === "yellow") return "orange";
  if (result.overall_status === "green") return "green";
  return "pending";
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
