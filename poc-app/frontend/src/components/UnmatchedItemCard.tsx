import { useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, Image as ImageIcon, ExternalLink, UserCheck, ScanSearch } from "lucide-react";
import { api, fileUrl } from "../api";
import type { Invoice, UnmatchedBarcode, ValidationResult } from "../types";

/**
 * An "unexpected item" — a photo OpenCV+OCR or barcode decode processed but
 * couldn't tie to an invoice line, either because the identity it read
 * doesn't match anything on the invoice, or (the more common real case)
 * because it couldn't read a GTIN/batch at all. Previously this only ever
 * showed as flat text in a red banner, with no way to act on it and no way
 * to tell which invoice item it probably was — a real dead end. This turns
 * each one into its own card: view the source photo, pick which invoice
 * line it actually is, correct any fields that were misread, and submit —
 * real human intervention instead of a message with nowhere to go.
 */
export default function UnmatchedItemCard({
  item, invoice, onAssigned,
}: {
  item: UnmatchedBarcode;
  invoice: Invoice;
  onAssigned: (result: ValidationResult) => void;
}) {
  const [lineItemId, setLineItemId] = useState<string>("");
  const [gtin, setGtin] = useState(item.gtin ?? "");
  const [batch, setBatch] = useState(item.batch ?? "");
  const [qty, setQty] = useState(String(item.count));
  const [expiry, setExpiry] = useState(item.expiry ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const photoUrl = fileUrl(item.image_name);
  const annotatedUrl = fileUrl(item.annotated_image_name);

  async function assign() {
    if (!lineItemId) {
      setError("Pick which invoice item this actually is first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await api.manualAssign(invoice.invoice_number, Number(lineItemId), { gtin, batch, qty, expiry, note });
      onAssigned(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border p-5" style={{ borderColor: "var(--color-red)", background: "var(--color-red-tint)" }}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--color-red)" }}>
          <AlertTriangle size={14} strokeWidth={2.5} />
          Unidentified item - needs manual review
        </div>
        <div className="flex items-center gap-2">
          {photoUrl && (
            <a
              href={photoUrl} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full"
              style={{ background: "white", color: "var(--color-red)", border: "1px solid var(--color-red)" }}
            >
              <ImageIcon size={11} strokeWidth={2.5} />
              View photo
              <ExternalLink size={10} strokeWidth={2.5} />
            </a>
          )}
          {annotatedUrl && (
            <a
              href={annotatedUrl} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full"
              style={{ background: "white", color: "var(--color-red)", border: "1px solid var(--color-red)" }}
              title="See exactly which regions OpenCV detected as individual items, numbered in detection order."
            >
              <ScanSearch size={11} strokeWidth={2.5} />
              View detected boxes
              <ExternalLink size={10} strokeWidth={2.5} />
            </a>
          )}
        </div>
      </div>
      <p className="text-sm mb-3" style={{ color: "var(--color-red)" }}>{item.message}</p>

      <div className="rounded-lg p-3 mb-3" style={{ background: "white", border: "1px solid var(--color-red)" }}>
        <label className="block mb-2">
          <span className="block text-[10px] font-semibold uppercase tracking-wide mb-0.5" style={{ color: "var(--color-muted)" }}>
            Which invoice item is this?
          </span>
          <select
            value={lineItemId}
            onChange={(e) => setLineItemId(e.target.value)}
            className="w-full rounded-md px-2 py-1.5 text-sm border"
            style={{ borderColor: "var(--color-line)" }}
          >
            <option value="">Select an item…</option>
            {invoice.line_items.map((li) => (
              <option key={li.id} value={li.id}>{li.item_name} (GTIN {li.gtin ?? "-"} / Batch {li.batch})</option>
            ))}
          </select>
        </label>

        <div className="grid sm:grid-cols-4 gap-2 mb-2">
          <MiniField label="GTIN" value={gtin} onChange={setGtin} />
          <MiniField label="Batch" value={batch} onChange={setBatch} />
          <MiniField label="Quantity" value={qty} onChange={setQty} type="number" />
          <MiniField label="Expiry (YYYY-MM-DD)" value={expiry} onChange={setExpiry} />
        </div>

        <label className="block">
          <span className="block text-[10px] font-semibold uppercase tracking-wide mb-0.5" style={{ color: "var(--color-muted)" }}>
            Reviewer note
          </span>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Confirmed visually - this is the AURA lotion carton, batch was misread by OCR."
            className="w-full rounded-md px-2 py-1.5 text-sm border"
            style={{ borderColor: "var(--color-line)" }}
          />
        </label>
      </div>

      {error && <p className="text-xs mb-2" style={{ color: "var(--color-red)" }}>{error}</p>}

      <button
        onClick={assign}
        disabled={busy}
        className="inline-flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-lg text-white disabled:opacity-50"
        style={{ background: "var(--color-red)" }}
      >
        <UserCheck size={13} strokeWidth={2.5} />
        {busy ? "Assigning…" : "Assign & Validate"}
      </button>
    </motion.div>
  );
}

function MiniField({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (v: string) => void; type?: string }) {
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
