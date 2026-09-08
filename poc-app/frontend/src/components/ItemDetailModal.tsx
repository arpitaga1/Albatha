import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Image as ImageIcon, ExternalLink, ScanSearch, Pencil, X, History, User, ArrowRight } from "lucide-react";
import Modal from "./Modal";
import StatusBadge from "./StatusBadge";
import { api, fileUrl } from "../api";
import { formatApiError } from "../errors";
import { formatDate } from "../format";
import type { Finding, LineItem, ValidationResult } from "../types";

export interface Corrections {
  gtin?: string;
  batch?: string;
  qty?: string;
  expiry?: string;
}

interface ParsedCorrection {
  editor: string;
  changes: { field: string; from: string; to: string }[];
  reason: string | null;
}

// Parses the backend's single-sentence correction note (see scans.py's
// _apply_correction, e.g. "Manually corrected by Sara Al Mansoori: Quantity
// 3 → 4. Reason: recount confirmed.") back into structured pieces, so the
// Edit History list can render each field change as its own clear row
// instead of one dense run-on sentence.
function parseCorrectionNote(note: string): ParsedCorrection | null {
  const m = note.match(/^Manually corrected by (.+?): (.+?)\.(?: Reason: ([\s\S]*))?$/);
  if (!m) return null;
  const [, editor, summaryRaw, reason] = m;
  const changes: ParsedCorrection["changes"] = [];
  if (summaryRaw !== "no field values actually changed") {
    for (const part of summaryRaw.split("; ")) {
      const cm = part.match(/^(\w+) (.+?) → (.+)$/);
      if (!cm) continue;
      const [, field, from, to] = cm;
      const unquote = (v: string) => v.replace(/^'(.*)'$/, "$1");
      changes.push({ field, from: unquote(from), to: unquote(to) });
    }
  }
  return { editor, changes, reason: reason || null };
}

/**
 * Per-item detail popup: field-by-field compare table, structured
 * discrepancy table with a real reason field, and the Tatmeen result once
 * validated. This is the old always-inline ScanResultCard's content,
 * relocated into a Modal per client feedback (an invoice can carry up to
 * 150 items - rendering every one of these inline made the page long and
 * slow; the main table is the fast summary now, this is the on-demand
 * detail view for one item at a time).
 *
 * Deliberately has NO individual "Validate with Tatmeen" button - that's
 * now a single bulk action on the main table (client feedback: validate
 * every ready item together instead of one at a time). This still shows
 * the Tatmeen result once the bulk action has run, exactly as before.
 */

// Recommended Action is deliberately short (a few words) per client
// feedback - the full explanation lives in the Reason column instead.
const FIELD_META: Record<string, { field: string; action: string }> = {
  "2-identity-matching": { field: "Identity (GTIN/Batch)", action: "Re-scan & verify" },
  "6-gtin-checksum": { field: "GTIN", action: "Re-scan barcode" },
  "7-date-sanity": { field: "Manufacture/Expiry Dates", action: "Re-scan label" },
  "8-quantity-variance": { field: "Quantity", action: "Recount stock" },
  "9-uom-consistency": { field: "Unit of Measure", action: "Confirm unit type" },
  "10-expiry-alert": { field: "Expiry Date", action: "Quarantine stock" },
  "3-duplicate-check": { field: "Serial Number", action: "Investigate duplicate" },
  "11-cross-scan-duplicates": { field: "Serial Number", action: "Investigate duplicate" },
  "14-tatmeen-reported": { field: "Tatmeen Reporting", action: "Confirm with supplier" },
  "18-pending-window": { field: "Tatmeen Reporting", action: "Check back later" },
  "15-tatmeen-quantity": { field: "Tatmeen Quantity", action: "Reconcile with supplier" },
  "17-sscc-hierarchy": { field: "SSCC", action: "Verify packaging" },
  "4-image-quality-gate": { field: "Image Quality", action: "Retake photo" },
};

// Whether the invoice's expiry and the scanned expiry actually AGREE with
// each other — deliberately separate from whether the stock is expired
// (that's rule 10-expiry-alert's job, shown in the Discrepancies table
// below). One side may only carry month precision (invoice OCR, e.g.
// "2026-05") while the other has a full decoded date ("2026-05-31") —
// treated as agreeing, not a mismatch.
function expiryAgrees(invoiceExpiry: string | null, scannedExpiry: string | null | undefined): boolean | null {
  if (!invoiceExpiry || !scannedExpiry) return null;
  if (invoiceExpiry === scannedExpiry) return true;
  const [shorter, longer] = invoiceExpiry.length <= scannedExpiry.length
    ? [invoiceExpiry, scannedExpiry] : [scannedExpiry, invoiceExpiry];
  return longer.startsWith(shorter);
}

function discrepancyRows(lineItem: LineItem, result: ValidationResult) {
  return result.findings
    .filter((f): f is Finding => f.severity === "fail")
    .map((f) => {
      const meta = FIELD_META[f.rule] ?? { field: "Other", action: "Manual review required." };
      let expected = "-";
      let detected = "-";
      let action = meta.action;
      if (f.rule === "8-quantity-variance") {
        expected = `${lineItem.qty}`;
        detected = `${result.cumulative.total_scanned}`;
        const shortfallRatio = lineItem.qty > 0 ? result.cumulative.total_scanned / lineItem.qty : 1;
        if (shortfallRatio < 0.85) {
          action = "Retake closer photos";
        }
      } else if (f.rule === "2-identity-matching" || f.rule === "6-gtin-checksum") {
        expected = lineItem.gtin ?? lineItem.batch;
        detected = result.scanned?.gtin ?? result.scanned?.batch ?? "not recovered";
      } else if (f.rule === "10-expiry-alert") {
        expected = "Not expired";
        detected = formatDate(result.scanned?.expiry);
      }
      return { field: meta.field, expected, detected, reason: f.message, action };
    });
}

export default function ItemDetailModal({
  open, lineItem, result, tatmeenChecking, tatmeenRevealed, onResolve, onUpdate, onClose,
}: {
  open: boolean;
  lineItem: LineItem;
  result: ValidationResult | undefined;
  tatmeenChecking: boolean;
  tatmeenRevealed: boolean;
  onResolve: (action: "accepted" | "rejected", note: string) => void;
  onUpdate: (corrections: Corrections, note: string) => Promise<void>;
  onClose: () => void;
}) {
  // All hooks called unconditionally, before any early return - the
  // "not scanned yet" case below still has to hit every useState call in
  // the same order every render, so the edit-field state is initialized
  // from optional-chained defaults here rather than after a `if (!result)
  // return` guard (which would violate React's Rules of Hooks the moment
  // this component ever renders once without a result and once with one).
  const scanned = result?.scanned;
  // Two separate reason fields, deliberately not shared - "reason" is the
  // resolve-a-discrepancy Justification input, "editReason" is the
  // edit-details toolbar's own optional reason. Typing in one must not
  // echo into the other.
  const [reason, setReason] = useState("");
  const [editReason, setEditReason] = useState("");
  const [editing, setEditing] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [editGtin, setEditGtin] = useState(scanned?.gtin ?? "");
  const [editBatch, setEditBatch] = useState(scanned?.batch ?? "");
  const [editQty, setEditQty] = useState(String(result?.cumulative.total_scanned ?? ""));
  const [editExpiry, setEditExpiry] = useState(scanned?.expiry ?? "");
  // Edit history: every ScanEvent this line item has ever had, including
  // superseded ones (see GET /scans/{id}/history) - always visible once the
  // item has been edited (no click-to-expand), filtered down to just the
  // human corrections below (not every internal system/OCR note).
  const [history, setHistory] = useState<Awaited<ReturnType<typeof api.getScanHistory>> | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const wasEdited = scanned?.notes?.some((n) => n.includes("Manually corrected by")) ?? false;

  useEffect(() => {
    if (!wasEdited || history !== null) return;
    setHistoryLoading(true);
    api.getScanHistory(lineItem.id).then(setHistory).finally(() => setHistoryLoading(false));
  }, [wasEdited, history, lineItem.id]);

  const corrections = (history ?? []).filter((h) => h.is_correction);

  if (!result) {
    return (
      <Modal open={open} onClose={onClose} title={lineItem.item_name} fullScreen>
        <p className="text-sm text-[var(--color-muted)]">Not scanned yet - upload or scan a photo covering this item first.</p>
      </Modal>
    );
  }

  const r = result;
  const resolved = r.resolution_action != null;
  const rows = discrepancyRows(lineItem, r);
  const photoUrl = fileUrl(scanned?.image_name);
  const annotatedUrl = fileUrl(scanned?.annotated_image_name);
  // "Human Intervention Required" (red) is reserved for a real
  // item-count/GTIN/batch/serial mismatch - overall_status is already
  // red-only-for-those per validation_engine.py's finalize_overall_status.
  // Any other issue (expiry, date-sanity, Tatmeen, SSCC, ...) still shows
  // here, just as a warning rather than a critical/red banner.
  const isCritical = r.overall_status === "red";
  const bannerColor = isCritical ? "var(--color-red)" : "var(--color-yellow)";
  const bannerTint = isCritical ? "var(--color-red-tint)" : "var(--color-yellow-tint)";

  function startEditing() {
    setEditGtin(scanned?.gtin ?? "");
    setEditBatch(scanned?.batch ?? "");
    setEditQty(String(r.cumulative.total_scanned));
    setEditExpiry(scanned?.expiry ?? "");
    setEditReason("");
    setUpdateError(null);
    setEditing(true);
  }

  async function submitUpdate() {
    setUpdating(true);
    setUpdateError(null);
    try {
      await onUpdate({ gtin: editGtin, batch: editBatch, qty: editQty, expiry: editExpiry }, editReason);
      setEditing(false);
      setEditReason("");
      // Force the Edit History section to refetch (it only fetches once,
      // when null) so the new correction shows up immediately - no page
      // reload needed.
      setHistory(null);
    } catch (e) {
      setUpdateError(formatApiError(e));
    } finally {
      setUpdating(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={lineItem.item_name} fullScreen>
      <div className="flex flex-col lg:flex-row gap-5">
        {/* --- Left: the actual scanned photo, ~25% --- */}
        <div className="lg:w-1/4 shrink-0">
          {photoUrl ? (
            <div className="rounded-lg overflow-hidden border" style={{ borderColor: "var(--color-line)" }}>
              <img src={photoUrl} alt={`Scanned photo for ${lineItem.item_name}`} className="w-full block" />
              <div className="p-2.5 flex flex-col gap-1.5" style={{ background: "var(--color-paper)" }}>
                <a
                  href={photoUrl} target="_blank" rel="noreferrer"
                  className="inline-flex items-center justify-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-full transition-colors"
                  style={{ background: "var(--color-accent-tint, #e2efef)", color: "var(--color-accent-ink, #0a5e6d)" }}
                >
                  <ImageIcon size={11} strokeWidth={2.5} />
                  Open full size
                  <ExternalLink size={10} strokeWidth={2.5} />
                </a>
                {annotatedUrl && (
                  <a
                    href={annotatedUrl} target="_blank" rel="noreferrer"
                    className="inline-flex items-center justify-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-full transition-colors"
                    style={{ background: "var(--color-yellow-tint)", color: "var(--color-yellow)" }}
                    title="See exactly which regions OpenCV detected as individual items, numbered in detection order."
                  >
                    <ScanSearch size={11} strokeWidth={2.5} />
                    View detected boxes
                    <ExternalLink size={10} strokeWidth={2.5} />
                  </a>
                )}
                {scanned?.method === "opencv" && (
                  <span
                    className="inline-flex items-center justify-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-full"
                    style={{ background: "var(--color-yellow-tint)", color: "var(--color-yellow)" }}
                    title="Barcode was not decodable in this photo - detected via OpenCV + local OCR instead (no AI vision, no API key)."
                  >
                    <ScanSearch size={11} strokeWidth={2.5} />
                    Detected via OpenCV
                  </span>
                )}
              </div>
            </div>
          ) : (
            <div
              className="rounded-lg border flex items-center justify-center py-16 px-4 text-center text-xs text-[var(--color-muted)]"
              style={{ borderColor: "var(--color-line)" }}
            >
              No photo available for this scan.
            </div>
          )}

          {wasEdited && (
            <div className="rounded-lg border p-3 mt-3" style={{ borderColor: "var(--color-line)", background: "var(--color-paper)" }}>
              <div className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-muted)" }}>
                Edit History
              </div>
              {historyLoading && <p className="text-xs text-[var(--color-muted)]">Loading…</p>}
              {!historyLoading && corrections.length === 0 && (
                <p className="text-xs text-[var(--color-muted)]">No manual edits recorded.</p>
              )}
              {corrections.length > 0 && (
                <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                  {/* Most recent edit first - corrections is fetched oldest-first from the API. */}
                  {[...corrections].reverse().map((h) => {
                    const parsed = h.notes.map(parseCorrectionNote).find((p) => p != null);
                    return (
                      <div key={h.id} className="rounded-md border bg-white p-2.5" style={{ borderColor: "var(--color-line)" }}>
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <span className="inline-flex items-center gap-1.5 text-xs font-semibold">
                            <User size={12} strokeWidth={2.5} style={{ color: "var(--color-muted)" }} />
                            {parsed?.editor ?? "A reviewer"}
                          </span>
                          <span className="text-[10px] shrink-0" style={{ color: "var(--color-muted)" }}>
                            {h.created_at ? new Date(h.created_at).toLocaleString() : "Unknown time"}
                          </span>
                        </div>
                        {h.superseded && (
                          <span
                            className="inline-block text-[9px] font-semibold px-1.5 py-0.5 rounded-full mb-1.5"
                            style={{ background: "var(--color-line)", color: "var(--color-muted)" }}
                          >
                            Superseded
                          </span>
                        )}
                        {parsed && parsed.changes.length > 0 ? (
                          <div className="flex flex-col gap-1 mb-1">
                            {parsed.changes.map((c, i) => (
                              <div key={i} className="flex items-center gap-1.5 text-xs">
                                <span className="font-medium shrink-0">{c.field}:</span>
                                <span className="mono line-through" style={{ color: "var(--color-muted)" }}>{c.from}</span>
                                <ArrowRight size={11} strokeWidth={2.5} style={{ color: "var(--color-muted)" }} className="shrink-0" />
                                <span className="mono font-semibold" style={{ color: "var(--color-accent-ink, #0a5e6d)" }}>{c.to}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          h.notes.filter((n) => n.includes("Manually corrected by")).map((n, i) => (
                            <p key={i} className="text-xs mb-1" style={{ color: "var(--color-ink)" }}>{n}</p>
                          ))
                        )}
                        {parsed?.reason && (
                          <p className="text-xs italic pt-1 mt-1 border-t" style={{ color: "var(--color-muted)", borderColor: "var(--color-line)" }}>
                            "{parsed.reason}"
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* --- Right: everything else, ~75% --- */}
        <div className="lg:w-3/4 min-w-0">
      <div className="flex items-center justify-end gap-2 flex-wrap mb-2">
        {wasEdited && (
          <span
            className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full"
            style={{ background: "var(--color-yellow-tint)", color: "var(--color-yellow)" }}
            title="This item's data was manually edited - see the edit history below."
          >
            <History size={12} strokeWidth={2.5} />
            Edited
          </span>
        )}
        <StatusBadge status={r.overall_status} />
        {editing && (
          <input
            value={editReason}
            onChange={(e) => setEditReason(e.target.value)}
            placeholder="Reason for this change (optional)"
            className="flex-1 min-w-[160px] rounded-md border px-2.5 py-1.5 text-xs"
            style={{ borderColor: "var(--color-accent)" }}
          />
        )}
        {editing && (
          <button
            onClick={submitUpdate}
            disabled={updating}
            className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full text-white disabled:opacity-50"
            style={{ background: "var(--color-accent)" }}
          >
            {updating ? "Updating…" : "Update Data"}
          </button>
        )}
        <button
          onClick={() => (editing ? setEditing(false) : startEditing())}
          className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full transition-colors"
          style={{ border: "1px solid var(--color-accent)", color: "var(--color-accent)" }}
        >
          {editing ? <X size={11} strokeWidth={2.5} /> : <Pencil size={11} strokeWidth={2.5} />}
          {editing ? "Cancel edit" : "Edit Details"}
        </button>
      </div>
      {updateError && <p className="text-xs mb-2 text-right" style={{ color: "var(--color-red)" }}>{updateError}</p>}

      <div className="overflow-x-auto mb-1">
        <table className="w-full text-sm mb-3">
          <thead>
            <tr className="text-left text-xs text-[var(--color-muted)] font-medium">
              <th className="pb-1 pr-3">Field</th>
              <th className="pb-1 pr-3">Invoice</th>
              <th className="pb-1 pr-3">Scanned</th>
              <th className="pb-1">Result</th>
            </tr>
          </thead>
          <tbody>
            <Row
              label="GTIN"
              invoice={lineItem.gtin ?? "-"}
              scanned={editing ? <RowEditInput value={editGtin} onChange={setEditGtin} /> : (scanned?.gtin ?? "-")}
              ok={!lineItem.gtin || !scanned?.gtin ? null : scanned.gtin === lineItem.gtin}
            />
            <Row
              label="Batch"
              invoice={lineItem.batch}
              scanned={editing ? <RowEditInput value={editBatch} onChange={setEditBatch} /> : (scanned?.batch ?? "-")}
              ok={!lineItem.batch || !scanned?.batch ? null : scanned.batch === lineItem.batch}
            />
            <Row
              label="Quantity"
              invoice={`${lineItem.qty}`}
              scanned={editing ? <RowEditInput value={editQty} onChange={setEditQty} type="number" /> : `${r.cumulative.total_scanned}`}
              ok={r.quantity_status === "green"}
            />
            <Row
              label="Expiry Date"
              invoice={formatDate(lineItem.expiry)}
              scanned={editing ? <RowEditInput value={editExpiry} onChange={setEditExpiry} placeholder="YYYY-MM-DD" /> : formatDate(scanned?.expiry)}
              ok={expiryAgrees(lineItem.expiry, scanned?.expiry)}
            />
            {lineItem.sscc && (
              <Row label="SSCC" invoice={lineItem.sscc} scanned={scanned?.case_sscc ?? "-"} ok={r.sscc_status === "green"} />
            )}
          </tbody>
        </table>
      </div>

      {rows.length > 0 && !resolved && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="rounded-lg p-3 mb-3" style={{ background: bannerTint }}>
          <div className="text-sm font-semibold mb-2" style={{ color: bannerColor }}>
            {isCritical ? "Discrepancies Found - Human Intervention Required" : "Discrepancies Found - Review Recommended"}
          </div>
          <div className="grid gap-2 mb-3 sm:grid-cols-2">
            {rows.map((row, i) => (
              <div
                key={i}
                className="rounded-lg p-2.5"
                style={{ background: "white", border: `1px solid ${bannerColor}` }}
              >
                <div className="flex items-center justify-between gap-2 flex-wrap mb-1.5">
                  <span
                    className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
                    style={{ background: bannerTint, color: bannerColor }}
                  >
                    {row.field}
                  </span>
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full text-white" style={{ background: bannerColor }}>
                    {row.action}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs mb-1.5">
                  <div>
                    <span className="text-[10px] uppercase tracking-wide" style={{ color: "var(--color-muted)" }}>Expected: </span>
                    <span className="mono">{row.expected}</span>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase tracking-wide" style={{ color: "var(--color-muted)" }}>Detected: </span>
                    <span className="mono">{row.detected}</span>
                  </div>
                </div>
                <p className="text-xs" style={{ color: "var(--color-muted)" }}>{row.reason}</p>
              </div>
            ))}
          </div>

          <label className="block text-xs font-medium mb-1" style={{ color: bannerColor }}>
            Justification
          </label>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Confirmed 10 physical units on the shelf; short delivery accepted."
            className="w-full rounded-md px-2.5 py-1.5 text-sm mb-2 border"
            style={{ borderColor: bannerColor, background: "white" }}
          />
          <div className="flex gap-2">
            <button onClick={() => onResolve("accepted", reason)} className="text-xs font-semibold px-3 py-1.5 rounded-lg text-white" style={{ background: "var(--color-green)" }}>
              Accept
            </button>
            <button onClick={() => onResolve("rejected", reason)} className="text-xs font-semibold px-3 py-1.5 rounded-lg" style={{ border: `1px solid ${bannerColor}`, color: bannerColor }}>
              Reject
            </button>
          </div>
        </motion.div>
      )}

      {resolved && (
        <div className="text-xs mb-3 rounded-lg px-3 py-2" style={{ background: "var(--color-line)", color: "var(--color-muted)" }}>
          <div>Reviewer decision: <b>{r.resolution_action}</b></div>
          {r.resolution_note && <div className="mt-0.5 italic">"{r.resolution_note}"</div>}
        </div>
      )}

      {tatmeenChecking && (
        <div className="flex items-center gap-3">
          <motion.span className="h-4 w-4 rounded-full border-2 border-[var(--color-accent)] border-t-transparent" animate={{ rotate: 360 }} transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }} />
          <span className="text-sm text-[var(--color-muted)]">Checking Tatmeen (simulated database)…</span>
        </div>
      )}

      <AnimatePresence>
        {tatmeenRevealed && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="pt-3 mt-1 border-t" style={{ borderColor: "var(--color-line)" }}>
            <div className="flex items-center gap-2">
              <StatusBadge status={r.tatmeen_status} />
              <span className="text-sm font-medium">
                {r.tatmeen_status === "green" && "Reported on Tatmeen - Validated"}
                {r.tatmeen_status === "yellow" && "Reported on Tatmeen - pending confirmation"}
                {r.tatmeen_status === "red" && (
                  r.findings.some((f) => f.message.startsWith("Tatmeen Validation Failed"))
                    ? "Tatmeen Validation Failed"
                    : "Not Reported on Tatmeen"
                )}
                {r.tatmeen_status === "n_a" && "Tatmeen Not Checked"}
              </span>
            </div>
            <p className="text-xs text-[var(--color-muted)] mt-1">
              {r.findings.find((f) => f.rule.startsWith("14-") || f.rule.startsWith("15-") || f.rule.startsWith("18-"))?.message}
            </p>

            {lineItem.sscc && (
              <div className="flex items-center gap-2 mt-2.5 pt-2.5 border-t" style={{ borderColor: "var(--color-line)" }}>
                <StatusBadge status={r.sscc_status} />
                <span className="text-sm font-medium">
                  {r.sscc_status === "green" && "SSCC Reported"}
                  {r.sscc_status === "red" && "SSCC Not Reported"}
                  {r.sscc_status === "yellow" && "SSCC Reported - pending confirmation"}
                  {r.sscc_status === "n_a" && "SSCC Not Checked"}
                </span>
              </div>
            )}
          </motion.div>
        )}
        {!tatmeenRevealed && !tatmeenChecking && lineItem.category === "pharma" && (
          <p className="text-xs text-[var(--color-muted)]">
            Not yet validated against Tatmeen - use the "Validate in Tatmeen" bulk action on the
            main table once this item's data is fully matched (or a reviewer decision is recorded).
          </p>
        )}
      </AnimatePresence>
        </div>
      </div>
    </Modal>
  );
}

// Compact inline input used directly inside the compare table's Scanned
// column while editing - replaces the old separate "Edit scanned item
// details" panel, per user feedback (edit in place, not in a new section).
function RowEditInput({ value, onChange, type = "text", placeholder }: { value: string; onChange: (v: string) => void; type?: string; placeholder?: string }) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full max-w-[160px] rounded-md px-2 py-1 text-xs border mono"
      style={{ borderColor: "var(--color-accent)" }}
    />
  );
}

function Row({ label, invoice, scanned, ok }: { label: string; invoice: string; scanned: React.ReactNode; ok: boolean | null }) {
  return (
    <tr className="border-t" style={{ borderColor: "var(--color-line)" }}>
      <td className="py-1.5 pr-3 font-medium">{label}</td>
      <td className="py-1.5 pr-3 mono">{invoice}</td>
      <td className="py-1.5 pr-3 mono">{scanned}</td>
      <td className="py-1.5">
        {ok === null ? (
          <span style={{ color: "var(--color-muted)" }}>- Not captured</span>
        ) : ok ? (
          <span style={{ color: "var(--color-green)" }}>✓ Matched</span>
        ) : (
          <span style={{ color: "var(--color-red)" }}>⚠ Mismatch</span>
        )}
      </td>
    </tr>
  );
}
