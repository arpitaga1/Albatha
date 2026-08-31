import { useState } from "react";
import { motion } from "framer-motion";
import { Pencil, Check, X, Loader2, ShieldCheck, Clock, CheckCircle2, XCircle } from "lucide-react";
import StatusDot from "./StatusDot";
import ItemDetailModal, { type Corrections } from "./ItemDetailModal";
import { rowStatus } from "../format";
import type { Invoice, LineItem, ValidationResult } from "../types";

/**
 * The main scan-results table, shared by RealScanFlow and MockScanFlow.
 *
 * Per client feedback (an invoice can carry up to 150 line items):
 * - Stays a fast, concise summary table - full per-item detail lives in a
 *   popup (ItemDetailModal), opened on demand per row, not rendered inline
 *   for every item at once.
 * - Gains its "post-scan" columns (Scanned Qty, richer Status, Details)
 *   only once at least one item has actually been scanned - before that
 *   it's exactly the plain Item/GTIN/Batch/Expected Qty/Status table.
 * - Scanned Qty is editable directly in the cell - no need to open the
 *   popup just to correct a miscounted quantity.
 * - Tatmeen validation is a single bulk action for every item that's
 *   currently eligible (matched, or has a recorded reviewer decision) and
 *   not yet validated - not a per-item button. Re-enables itself as more
 *   items become eligible after a reviewer fixes them via the popup.
 */
export default function ItemsTable({
  invoice, results, tatmeenRevealed, tatmeenChecking, onResolve, onUpdate, onRevealTatmeenBulk,
}: {
  invoice: Invoice;
  results: Record<number, ValidationResult>;
  tatmeenRevealed: Set<number>;
  tatmeenChecking: Set<number>;
  onResolve: (lineItemId: number, action: "accepted" | "rejected", note: string) => void;
  onUpdate: (lineItemId: number, corrections: Corrections, note: string) => Promise<void>;
  onRevealTatmeenBulk: (lineItemIds: number[]) => void;
}) {
  const [openItemId, setOpenItemId] = useState<number | null>(null);
  // Separate from openItemId so closing the modal (setOpenItemId(null))
  // doesn't also rip its content out of the tree before Modal's own exit
  // animation gets to play - this keeps rendering the last-opened item's
  // detail while `open={false}` animates the popup away, instead of it
  // just vanishing instantly.
  const [lastOpenItemId, setLastOpenItemId] = useState<number | null>(null);
  const scannedCount = Object.keys(results).length;
  const displayItem = invoice.line_items.find((li) => li.id === (openItemId ?? lastOpenItemId));

  function openDetails(id: number) {
    setLastOpenItemId(id);
    setOpenItemId(id);
  }

  const eligibleForTatmeen = invoice.line_items.filter((li) => {
    const r = results[li.id];
    if (!r || tatmeenRevealed.has(li.id) || tatmeenChecking.has(li.id)) return false;
    if (li.category !== "pharma") return false;
    const dataMatches = r.invoice_match_status === "green" && r.quantity_status === "green";
    return dataMatches || r.resolution_action != null;
  });

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          Invoice - extracted line items (real OCR)
        </div>
        {eligibleForTatmeen.length > 0 && (
          <motion.button
            initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
            onClick={() => onRevealTatmeenBulk(eligibleForTatmeen.map((li) => li.id))}
            className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-semibold text-white"
            style={{ background: "var(--color-accent-ink, #0a5e6d)" }}
          >
            <ShieldCheck size={13} strokeWidth={2.5} />
            Validate in Tatmeen ({eligibleForTatmeen.length})
          </motion.button>
        )}
      </div>

      <div className="rounded-xl border bg-white overflow-hidden" style={{ borderColor: "var(--color-line)" }}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-[var(--color-muted)] border-b" style={{ borderColor: "var(--color-line)" }}>
                <th className="py-2 px-4">Item</th>
                <th className="py-2 px-4">GTIN</th>
                <th className="py-2 px-4">Batch</th>
                <th className="py-2 px-4">Expected Qty</th>
                {scannedCount > 0 && <th className="py-2 px-4">Scanned Qty</th>}
                <th className="py-2 px-4">Status</th>
                {scannedCount > 0 && <th className="py-2 px-4">Tatmeen</th>}
                {scannedCount > 0 && <th className="py-2 px-4"></th>}
              </tr>
            </thead>
            <tbody>
              {invoice.line_items.map((li) => (
                <ItemRow
                  key={li.id}
                  lineItem={li}
                  result={results[li.id]}
                  showPostScanColumns={scannedCount > 0}
                  tatmeenRevealed={tatmeenRevealed.has(li.id)}
                  tatmeenChecking={tatmeenChecking.has(li.id)}
                  onEditQty={(newQty) => onUpdate(li.id, { qty: String(newQty) }, "Scanned quantity corrected inline from the items table.")}
                  onOpenDetails={() => openDetails(li.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {displayItem && (
        <ItemDetailModal
          open={openItemId != null}
          lineItem={displayItem}
          result={results[displayItem.id]}
          tatmeenChecking={tatmeenChecking.has(displayItem.id)}
          tatmeenRevealed={tatmeenRevealed.has(displayItem.id)}
          onResolve={(action, note) => onResolve(displayItem.id, action, note)}
          onUpdate={(corrections, note) => onUpdate(displayItem.id, corrections, note)}
          onClose={() => setOpenItemId(null)}
        />
      )}
    </div>
  );
}

function ItemRow({
  lineItem, result, showPostScanColumns, tatmeenRevealed, tatmeenChecking, onEditQty, onOpenDetails,
}: {
  lineItem: LineItem;
  result: ValidationResult | undefined;
  showPostScanColumns: boolean;
  tatmeenRevealed: boolean;
  tatmeenChecking: boolean;
  onEditQty: (newQty: number) => Promise<void>;
  onOpenDetails: () => void;
}) {
  const scanned = result?.scanned;
  const gtinMismatch = !!(lineItem.gtin && scanned?.gtin && scanned.gtin !== lineItem.gtin);
  const batchMismatch = !!(lineItem.batch && scanned?.batch && scanned.batch !== lineItem.batch);
  const status = rowStatus(result);
  const hasIssue = status === "red" || status === "orange";

  return (
    <tr className="border-b last:border-0 hover:bg-[var(--color-paper)] transition-colors" style={{ borderColor: "var(--color-line)" }}>
      <td className="py-2 px-4 font-medium">{lineItem.item_name}</td>
      <td className="py-2 px-4">
        <FieldValue value={lineItem.gtin ?? "-"} mismatch={gtinMismatch} />
      </td>
      <td className="py-2 px-4">
        <FieldValue value={lineItem.batch} mismatch={batchMismatch} />
      </td>
      <td className="py-2 px-4">{lineItem.qty} {lineItem.uom}</td>
      {showPostScanColumns && (
        <td className="py-2 px-4">
          {result ? (
            <EditableQty value={result.cumulative.total_scanned} uom={lineItem.uom} onSave={onEditQty} />
          ) : (
            <span className="text-[var(--color-muted)]">-</span>
          )}
        </td>
      )}
      <td className="py-2 px-4">
        <StatusDot status={status} />
      </td>
      {showPostScanColumns && (
        <td className="py-2 px-4">
          <TatmeenCell
            category={lineItem.category}
            result={result}
            revealed={tatmeenRevealed}
            checking={tatmeenChecking}
          />
        </td>
      )}
      {showPostScanColumns && (
        <td className="py-2 px-4">
          {result && (
            <button
              onClick={onOpenDetails}
              className="text-xs font-semibold whitespace-nowrap"
              style={{ color: hasIssue ? "var(--color-red)" : "var(--color-accent-ink, #0a5e6d)" }}
            >
              {hasIssue ? "Show Full Details" : "View Details"}
            </button>
          )}
        </td>
      )}
    </tr>
  );
}

// Per client feedback: the table should show the Tatmeen result too, not
// just the invoice-match status - "Not Verified" before the bulk action
// has run, then "Valid"/"Invalid" (or "Pending" for the grace-window
// case) once it has. Non-pharma items never go through Tatmeen at all
// (rule 16), so they read "N/A" rather than an unexplained blank cell.
function TatmeenCell({
  category, result, revealed, checking,
}: {
  category: LineItem["category"];
  result: ValidationResult | undefined;
  revealed: boolean;
  checking: boolean;
}) {
  if (category !== "pharma") {
    return <span className="text-xs text-[var(--color-muted)]">N/A</span>;
  }
  if (!result) {
    return <span className="text-xs text-[var(--color-muted)]">-</span>;
  }
  if (checking) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--color-muted)]">
        <Loader2 size={12} className="animate-spin" />
        Checking…
      </span>
    );
  }
  if (!revealed) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--color-muted)]">
        <Clock size={12} strokeWidth={2.5} />
        Not Verified
      </span>
    );
  }
  if (result.tatmeen_status === "green") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold" style={{ color: "var(--color-green)" }}>
        <CheckCircle2 size={13} strokeWidth={2.5} />
        Valid
      </span>
    );
  }
  if (result.tatmeen_status === "yellow") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold" style={{ color: "var(--color-yellow)" }}>
        <Clock size={13} strokeWidth={2.5} />
        Pending
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold" style={{ color: "var(--color-red)" }}>
      <XCircle size={13} strokeWidth={2.5} />
      Invalid
    </span>
  );
}

function FieldValue({ value, mismatch }: { value: string; mismatch: boolean }) {
  return (
    <span className="mono text-xs inline-flex items-center gap-1.5">
      {value}
      {mismatch && (
        <span
          className="h-1.5 w-1.5 rounded-full shrink-0"
          style={{ background: "var(--color-red)" }}
          title="Doesn't match the scanned value"
        />
      )}
    </span>
  );
}

function EditableQty({ value, uom, onSave }: { value: number; uom: string; onSave: (newValue: number) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(value));
  const [saving, setSaving] = useState(false);

  function startEditing() {
    setDraft(String(value));
    setEditing(true);
  }

  async function commit() {
    const parsed = Number(draft);
    if (!Number.isFinite(parsed) || parsed < 0) return;
    if (parsed === value) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onSave(parsed);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1">
        <input
          type="number"
          min={0}
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") setEditing(false);
          }}
          disabled={saving}
          className="w-16 rounded-md border px-1.5 py-1 text-xs mono"
          style={{ borderColor: "var(--color-accent)" }}
        />
        <span className="text-xs text-[var(--color-muted)]">{uom}</span>
        {saving ? (
          <Loader2 size={13} className="animate-spin" style={{ color: "var(--color-accent)" }} />
        ) : (
          <>
            <button onClick={commit} title="Save" className="text-[var(--color-green)]"><Check size={14} strokeWidth={2.75} /></button>
            <button onClick={() => setEditing(false)} title="Cancel" className="text-[var(--color-muted)]"><X size={14} strokeWidth={2.75} /></button>
          </>
        )}
      </span>
    );
  }

  return (
    <button
      onClick={startEditing}
      className="inline-flex items-center gap-1 text-xs mono hover:underline"
      title="Click to correct the scanned quantity"
    >
      {value} {uom}
      <Pencil size={10} strokeWidth={2.5} className="text-[var(--color-muted)]" />
    </button>
  );
}
