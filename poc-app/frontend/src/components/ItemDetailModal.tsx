import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Image as ImageIcon, ExternalLink, ScanSearch, Pencil, X } from "lucide-react";
import Modal from "./Modal";
import StatusBadge from "./StatusBadge";
import { fileUrl } from "../api";
import { formatDate } from "../format";
import type { Finding, LineItem, ValidationResult } from "../types";

export interface Corrections {
  gtin?: string;
  batch?: string;
  qty?: string;
  expiry?: string;
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

const FIELD_META: Record<string, { field: string; action: string }> = {
  "2-identity-matching": { field: "Identity (GTIN/Batch)", action: "Verify the scanned label matches the invoice item; re-scan if it may have been misread." },
  "6-gtin-checksum": { field: "GTIN", action: "Re-scan - the barcode's check digit failed, which usually means a misread." },
  "7-date-sanity": { field: "Manufacture/Expiry Dates", action: "Re-scan the label - the dates read as inconsistent, likely an OCR/decode error." },
  "8-quantity-variance": { field: "Quantity", action: "Recount the physical stock and confirm the shortage/overage with the warehouse team." },
  "9-uom-consistency": { field: "Unit of Measure", action: "Confirm whether the invoice line means cartons or individual units before comparing quantity." },
  "10-expiry-alert": { field: "Expiry Date", action: "Quarantine the stock - do not proceed with a shipment containing expired product." },
  "3-duplicate-check": { field: "Serial Number", action: "Investigate - two units in this scan share a serial (possible relabeling or misread)." },
  "11-cross-scan-duplicates": { field: "Serial Number", action: "Investigate - this serial was already counted in a previous scan for this item." },
  "14-tatmeen-reported": { field: "Tatmeen Reporting", action: "Contact the supplier to confirm this batch has been reported to Tatmeen." },
  "18-pending-window": { field: "Tatmeen Reporting", action: "Not reported yet, but within the grace window - check back before escalating." },
  "15-tatmeen-quantity": { field: "Tatmeen Quantity", action: "Reconcile the quantity Tatmeen has on record against the invoice with the supplier." },
  "17-sscc-hierarchy": { field: "SSCC", action: "Verify case-level packaging and confirm the SSCC's reported status in Tatmeen." },
  "4-image-quality-gate": { field: "Image Quality", action: "Retake the photo - straight-on, closer, better lit." },
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
        expected = `${lineItem.qty} ${lineItem.uom}`;
        detected = `${result.cumulative.total_scanned} ${lineItem.uom}`;
        const shortfallRatio = lineItem.qty > 0 ? result.cumulative.total_scanned / lineItem.qty : 1;
        if (shortfallRatio < 0.85) {
          action = "For a densely packed carton, a gap this size can come from the photo's resolution " +
            "limiting how many codes are legible, not necessarily missing stock. Retake in closer, " +
            "smaller sections (fewer boxes per photo) - multiple photos combine into one result " +
            "automatically - or recount physically if the photo is already as close as possible.";
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
  const [reason, setReason] = useState("");
  const [editing, setEditing] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [editGtin, setEditGtin] = useState(scanned?.gtin ?? "");
  const [editBatch, setEditBatch] = useState(scanned?.batch ?? "");
  const [editQty, setEditQty] = useState(String(result?.cumulative.total_scanned ?? ""));
  const [editExpiry, setEditExpiry] = useState(scanned?.expiry ?? "");

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
    setUpdateError(null);
    setEditing(true);
  }

  async function submitUpdate() {
    setUpdating(true);
    setUpdateError(null);
    try {
      await onUpdate({ gtin: editGtin, batch: editBatch, qty: editQty, expiry: editExpiry }, reason);
      setEditing(false);
      setReason("");
    } catch (e) {
      setUpdateError(String(e));
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
        </div>

        {/* --- Right: everything else, ~75% --- */}
        <div className="lg:w-3/4 min-w-0">
      <div className="flex items-center justify-end mb-3">
        <StatusBadge status={r.overall_status} />
      </div>

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
              scanned={scanned?.gtin ?? "-"}
              ok={!lineItem.gtin || !scanned?.gtin ? null : scanned.gtin === lineItem.gtin}
            />
            <Row
              label="Batch"
              invoice={lineItem.batch}
              scanned={scanned?.batch ?? "-"}
              ok={!lineItem.batch || !scanned?.batch ? null : scanned.batch === lineItem.batch}
            />
            <Row label="Quantity" invoice={`${lineItem.qty} ${lineItem.uom}`} scanned={`${r.cumulative.total_scanned} ${lineItem.uom}`} ok={r.quantity_status === "green"} />
            <Row
              label="Expiry Date"
              invoice={formatDate(lineItem.expiry)}
              scanned={formatDate(scanned?.expiry)}
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
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-semibold" style={{ color: bannerColor }}>
              {isCritical ? "Discrepancies Found - Human Intervention Required" : "Discrepancies Found - Review Recommended"}
            </div>
            <button
              onClick={() => (editing ? setEditing(false) : startEditing())}
              className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-md"
              style={editing
                ? { background: bannerColor, color: "white" }
                : { border: `1px solid ${bannerColor}`, color: bannerColor }}
            >
              {editing ? <X size={11} strokeWidth={2.5} /> : <Pencil size={11} strokeWidth={2.5} />}
              {editing ? "Cancel edit" : "Edit values"}
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs mb-3">
              <thead>
                <tr className="text-left" style={{ color: bannerColor }}>
                  <th className="pb-1 pr-3 font-medium">Field</th>
                  <th className="pb-1 pr-3 font-medium">Expected</th>
                  <th className="pb-1 pr-3 font-medium">Detected</th>
                  <th className="pb-1 pr-3 font-medium">Reason</th>
                  <th className="pb-1 font-medium">Recommended Action</th>
                </tr>
              </thead>
              <tbody style={{ color: bannerColor }}>
                {rows.map((row, i) => (
                  <tr key={i} className="align-top">
                    <td className="py-1 pr-3 font-medium whitespace-nowrap">{row.field}</td>
                    <td className="py-1 pr-3 mono whitespace-nowrap">{row.expected}</td>
                    <td className="py-1 pr-3 mono whitespace-nowrap">{row.detected}</td>
                    <td className="py-1 pr-3">{row.reason}</td>
                    <td className="py-1">{row.action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <AnimatePresence mode="wait">
            {editing ? (
              <motion.div key="edit" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <div
                  className="grid sm:grid-cols-4 gap-2 mb-2 rounded-md p-2.5"
                  style={{ background: "white", border: `1px solid ${bannerColor}` }}
                >
                  <EditField label="GTIN" value={editGtin} onChange={setEditGtin} />
                  <EditField label="Batch" value={editBatch} onChange={setEditBatch} />
                  <EditField label="Quantity" value={editQty} onChange={setEditQty} type="number" />
                  <EditField label="Expiry (YYYY-MM-DD)" value={editExpiry} onChange={setEditExpiry} />
                </div>
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="e.g. Corrected batch from a misread barcode - verified against the physical label."
                  className="w-full rounded-md px-2.5 py-1.5 text-sm mb-2 border"
                  style={{ borderColor: bannerColor, background: "white" }}
                />
                {updateError && <p className="text-xs mb-2" style={{ color: bannerColor }}>{updateError}</p>}
                <div className="flex gap-2">
                  <button
                    onClick={submitUpdate}
                    disabled={updating}
                    className="text-xs font-semibold px-3 py-1.5 rounded-lg text-white disabled:opacity-50"
                    style={{ background: "var(--color-accent)" }}
                  >
                    {updating ? "Updating…" : "Update Data"}
                  </button>
                  <button
                    onClick={() => setEditing(false)}
                    className="text-xs font-semibold px-3 py-1.5 rounded-lg"
                    style={{ border: `1px solid ${bannerColor}`, color: bannerColor }}
                  >
                    Cancel
                  </button>
                </div>
              </motion.div>
            ) : (
              <motion.div key="resolve" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
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
          </AnimatePresence>
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

function EditField({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (v: string) => void; type?: string }) {
  return (
    <label className="block">
      <span className="block text-[10px] font-semibold uppercase tracking-wide mb-0.5" style={{ color: "var(--color-muted)" }}>{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md px-2 py-1.5 text-sm border mono"
        style={{ borderColor: "var(--color-line)" }}
      />
    </label>
  );
}

function Row({ label, invoice, scanned, ok }: { label: string; invoice: string; scanned: string; ok: boolean | null }) {
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
