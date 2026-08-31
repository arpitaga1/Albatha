import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, ArrowRight, ArrowLeft, ExternalLink } from "lucide-react";
import { api, fileUrl } from "../api";
import ScannerFrame from "./ScannerFrame";
import ItemsTable from "./ItemsTable";
import type { Corrections } from "./ItemDetailModal";
import UnmatchedItemCard from "./UnmatchedItemCard";
import FinalSummary from "./FinalSummary";
import type { Invoice, RealScanResponse, UnmatchedBarcode, ValidationResult } from "../types";

type Stage = "scan" | "summary";

export default function RealScanFlow({ invoice }: { invoice: Invoice }) {
  const [results, setResults] = useState<Record<number, ValidationResult>>({});
  const [unmatched, setUnmatched] = useState<UnmatchedBarcode[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [tatmeenRevealed, setTatmeenRevealed] = useState<Set<number>>(new Set());
  const [tatmeenChecking, setTatmeenChecking] = useState<Set<number>>(new Set());
  const [loaded, setLoaded] = useState(false);
  const [stage, setStage] = useState<Stage>("scan");

  // State persistence: on opening this invoice, load any results that
  // already exist server-side instead of starting blank.
  useEffect(() => {
    api.getResultsForInvoice(invoice.invoice_number).then((r) => {
      setResults(r);
      const revealed = new Set(
        Object.values(r).filter((v) => v.tatmeen_status !== "n_a").map((v) => v.line_item_id)
      );
      setTatmeenRevealed(revealed);
      setLoaded(true);
    }).catch(() => setLoaded(true));
  }, [invoice.invoice_number]);

  function addFiles(newFiles: File[]) {
    setError(null);
    setScanMessage(null);
    setFiles((prev) => [...prev, ...newFiles]);
    setPreviews((prev) => [...prev, ...newFiles.map((f) => URL.createObjectURL(f))]);
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setPreviews((prev) => {
      URL.revokeObjectURL(prev[index]);
      return prev.filter((_, i) => i !== index);
    });
  }

  async function submitScan() {
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    setScanMessage(null);
    try {
      const res: RealScanResponse = await api.uploadRealScan(invoice.invoice_number, files);
      if (res.message) setScanMessage(res.message);
      setResults((prev) => {
        const next = { ...prev };
        for (const r of res.results) next[r.line_item_id] = r;
        return next;
      });
      setUnmatched(res.unmatched);
      previews.forEach((p) => URL.revokeObjectURL(p));
      setFiles([]);
      setPreviews([]);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function resolve(lineItemId: number, action: "accepted" | "rejected", note: string) {
    const r = await api.resolveDiscrepancy(lineItemId, action, note);
    setResults((prev) => ({ ...prev, [lineItemId]: r }));
  }

  async function update(lineItemId: number, corrections: Corrections, note: string) {
    const r = await api.correctScan(lineItemId, corrections, note);
    setResults((prev) => ({ ...prev, [lineItemId]: r }));
  }

  function handleAssigned(index: number, result: ValidationResult) {
    setUnmatched((prev) => prev.filter((_, i) => i !== index));
    setResults((prev) => ({ ...prev, [result.line_item_id]: result }));
  }

  // Bulk Tatmeen validation, per client feedback: every item that's
  // currently eligible (matched, or has a recorded reviewer decision) and
  // not yet validated gets checked together in one action, rather than
  // one button per item. The underlying result data is already computed
  // server-side as part of the original scan/resolve/correct response —
  // this "check" is a client-side reveal animation (same as the previous
  // per-item version), just applied to a whole batch of IDs at once.
  function revealTatmeenBulk(lineItemIds: number[]) {
    setTatmeenChecking((prev) => new Set([...prev, ...lineItemIds]));
    setTimeout(() => {
      setTatmeenChecking((prev) => {
        const next = new Set(prev);
        lineItemIds.forEach((id) => next.delete(id));
        return next;
      });
      setTatmeenRevealed((prev) => new Set([...prev, ...lineItemIds]));
    }, 1400);
  }

  if (!loaded) return <p className="text-sm text-[var(--color-muted)]">Loading…</p>;

  const scannedCount = Object.keys(results).length;
  const allResolved = invoice.line_items.length > 0 && invoice.line_items.every((li) => {
    const r = results[li.id];
    return r && (r.overall_status !== "red" || r.resolution_action != null);
  });
  const invoiceFileUrl = fileUrl(invoice.source_file_name);

  return (
    <AnimatePresence mode="wait">
      {stage === "scan" && (
        <motion.div key="scan" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}>
          {scannedCount > 0 && (
            <div className="flex items-center justify-end mb-4">
              <button
                onClick={() => setStage("summary")}
                className="rounded-lg px-4 py-2 text-sm font-semibold text-white flex items-center gap-2"
                style={{ background: "linear-gradient(135deg, var(--color-accent), #0a5e6d)" }}
              >
                Complete Validation - View Summary <ArrowRight size={14} strokeWidth={2.5} />
              </button>
            </div>
          )}
          {invoiceFileUrl && (
            <div className="flex items-center justify-end mb-2">
              <a
                href={invoiceFileUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full transition-colors"
                style={{ background: "var(--color-accent-tint, #e2efef)", color: "var(--color-accent-ink, #0a5e6d)" }}
              >
                <FileText size={12} strokeWidth={2.5} />
                View uploaded invoice
                <ExternalLink size={11} strokeWidth={2.5} />
              </a>
            </div>
          )}
          <ItemsTable
            invoice={invoice}
            results={results}
            tatmeenRevealed={tatmeenRevealed}
            tatmeenChecking={tatmeenChecking}
            onResolve={resolve}
            onUpdate={update}
            onRevealTatmeenBulk={revealTatmeenBulk}
          />

          <div className="mb-6">
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-2">
              Scan box / item - one or multiple photos
            </div>
            <ScannerFrame
              files={files}
              previews={previews}
              onAddFiles={addFiles}
              onRemoveFile={removeFile}
              status={
                busy ? "Decoding barcode(s)…"
                  : error ? "Scan failed"
                  : files.length > 0 ? "Photo(s) captured - ready to scan"
                  : "Ready to scan - add one photo, or several, then Scan Photos"
              }
              statusVariant={busy ? "active" : error ? "error" : files.length > 0 ? "success" : "idle"}
            >
              {files.length > 0 && (
                <button
                  onClick={submitScan}
                  disabled={busy}
                  className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  style={{ background: "var(--color-accent)" }}
                >
                  {busy ? "Decoding…" : files.length > 1 ? `Scan ${files.length} Photos` : "Scan Photo"}
                </button>
              )}
            </ScannerFrame>
            {error && <p className="text-sm text-[var(--color-red)] mt-2">{error}</p>}
            {scanMessage && (
              <p className="text-sm rounded-lg p-3 mt-2" style={{ background: "var(--color-yellow-tint)", color: "var(--color-yellow)" }}>
                {scanMessage}
              </p>
            )}
          </div>

          {unmatched.length > 0 && (
            <div className="space-y-3 mb-6">
              {unmatched.map((u, i) => (
                <UnmatchedItemCard key={i} item={u} invoice={invoice} onAssigned={(result) => handleAssigned(i, result)} />
              ))}
            </div>
          )}

          {scannedCount > 0 && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-3">
              <button
                onClick={() => setStage("summary")}
                className="rounded-lg px-5 py-2.5 text-sm font-semibold text-white flex items-center gap-2"
                style={{ background: "linear-gradient(135deg, var(--color-accent), #0a5e6d)" }}
              >
                Complete Validation - View Summary <ArrowRight size={14} strokeWidth={2.5} />
              </button>
              {!allResolved && (
                <span className="text-xs text-[var(--color-muted)]">
                  Some items still need attention - you can still view the summary now, or resolve them first.
                </span>
              )}
            </motion.div>
          )}
        </motion.div>
      )}

      {stage === "summary" && (
        <motion.div key="summary" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}>
          <div className="mb-4">
            <FinalSummary invoice={invoice} results={results} unmatched={unmatched} />
          </div>
          <button
            onClick={() => setStage("scan")}
            className="rounded-lg px-4 py-2 text-sm font-semibold flex items-center gap-2"
            style={{ border: "1px solid var(--color-line)", color: "var(--color-ink)" }}
          >
            <ArrowLeft size={14} strokeWidth={2.5} /> Back to items
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
