import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, ArrowRight, ArrowLeft, Image as ImageIcon, Layers, ScanLine, Package, ShieldCheck } from "lucide-react";
import { api, fileUrl } from "../api";
import { formatApiError } from "../errors";
import { useAuth } from "../context/AuthContext";
import ScannerFrame from "./ScannerFrame";
import RecaptureModal from "./RecaptureModal";
import AnalyzingModal from "./AnalyzingModal";
import Modal from "./Modal";
import ItemsTable from "./ItemsTable";
import type { Corrections } from "./ItemDetailModal";
import UnmatchedItemCard from "./UnmatchedItemCard";
import FinalSummary from "./FinalSummary";
import type { Invoice, RealScanResponse, UnmatchedBarcode, ValidationResult } from "../types";

type Stage = "scan" | "summary";

export default function RealScanFlow({ invoice }: { invoice: Invoice }) {
  const { user } = useAuth();
  const [results, setResults] = useState<Record<number, ValidationResult>>({});
  const [unmatched, setUnmatched] = useState<UnmatchedBarcode[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  // A rejected scan (nothing recorded server-side) - shown as a blocking
  // popup with the actual offending photo, per user directive, rather
  // than the passive inline scanMessage banner. Cleared only by Re-capture.
  const [rejection, setRejection] = useState<{ message: string } | null>(null);
  const [tatmeenRevealed, setTatmeenRevealed] = useState<Set<number>>(new Set());
  const [tatmeenChecking, setTatmeenChecking] = useState<Set<number>>(new Set());
  const [loaded, setLoaded] = useState(false);
  const [stage, setStage] = useState<Stage>("scan");
  // Most recently scanned photo's saved filename - powers the header's
  // "View Image" shortcut. Seeded from whatever's already on the invoice
  // when reopening it, then kept current after every new scan submission.
  const [lastScannedImage, setLastScannedImage] = useState<string | null>(null);
  // "View Image" / "View Invoice" open a preview popup on this same page
  // instead of a new browser tab, per user request.
  const [preview, setPreview] = useState<{ url: string; title: string } | null>(null);

  // State persistence: on opening this invoice, load any results that
  // already exist server-side instead of starting blank.
  useEffect(() => {
    api.getResultsForInvoice(invoice.invoice_number).then((r) => {
      setResults(r);
      const revealed = new Set(
        Object.values(r).filter((v) => v.tatmeen_status !== "n_a").map((v) => v.line_item_id)
      );
      setTatmeenRevealed(revealed);
      const withImage = Object.values(r).find((v) => v.scanned?.image_name);
      if (withImage?.scanned?.image_name) setLastScannedImage(withImage.scanned.image_name);
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
      // Per user directive, the details page's re-scan flow now runs the
      // same hybrid extraction as "Start Validation" - Gemini vision for
      // the count, classical barcode/OCR (unchanged) for the field data.
      const res: RealScanResponse = await api.uploadGeminiScan(invoice.invoice_number, files);
      if (res.results.length === 0 && res.message) {
        // Nothing was recorded server-side - the table stays exactly as
        // it was (nothing to merge in). Show why as a blocking popup with
        // the actual photo instead of the passive inline banner; keep the
        // rejected photo in the scanner so the popup can display it, and
        // only clear it once the user hits Re-capture.
        setRejection({ message: res.message });
        setBusy(false);
        return;
      }
      if (res.message) setScanMessage(res.message);
      setResults((prev) => {
        const next = { ...prev };
        for (const r of res.results) next[r.line_item_id] = r;
        return next;
      });
      const freshImage = res.results.find((r) => r.scanned?.image_name)?.scanned?.image_name;
      if (freshImage) setLastScannedImage(freshImage);
      setUnmatched(res.unmatched);
      previews.forEach((p) => URL.revokeObjectURL(p));
      setFiles([]);
      setPreviews([]);
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  // Closes the rejection popup, discards the rejected photo(s), and leaves
  // the (already continuously-live) camera ready for a fresh capture.
  function handleRecapture() {
    setRejection(null);
    previews.forEach((p) => URL.revokeObjectURL(p));
    setFiles([]);
    setPreviews([]);
  }

  async function resolve(lineItemId: number, action: "accepted" | "rejected", note: string) {
    const r = await api.resolveDiscrepancy(lineItemId, action, note, undefined, user?.name);
    setResults((prev) => ({ ...prev, [lineItemId]: r }));
  }

  async function update(lineItemId: number, corrections: Corrections, note: string) {
    const r = await api.correctScan(lineItemId, corrections, note, user?.name);
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
  const invoiceFileUrl = fileUrl(invoice.source_file_name);
  const lastScannedImageUrl = fileUrl(lastScannedImage);
  // Every line item scanned, and every one's quantity matched - nothing
  // left to scan for the first time, so the scanner's label reads as a
  // re-scan action instead of the initial "go scan this" instruction.
  const allQuantitiesMatched =
    invoice.line_items.length > 0 &&
    invoice.line_items.every((li) => results[li.id]?.quantity_status === "green");

  // Top-of-page KPI strip - per user request, the same "stat card" pattern
  // already used on Start Validation, summarizing THIS invoice's real
  // scan/validation progress rather than the whole system's.
  const totalLineItems = invoice.line_items.length;
  const unitsTracked = Object.values(results).reduce((s, r) => s + r.cumulative.total_scanned, 0);
  const pharmaCount = invoice.line_items.filter((li) => li.category === "pharma").length;
  const tatmeenValidatedCount = Object.values(results).filter((r) => r.tatmeen_status === "green").length;
  const statCards = [
    { label: "Line Items", value: totalLineItems, Icon: Layers, accent: "var(--color-accent)" },
    { label: "Items Scanned", value: `${scannedCount}/${totalLineItems}`, Icon: ScanLine, accent: "var(--color-accent)" },
    { label: "Units Tracked", value: unitsTracked, Icon: Package, accent: "var(--color-yellow)" },
    { label: "Validated in Tatmeen", value: `${tatmeenValidatedCount}/${pharmaCount}`, Icon: ShieldCheck, accent: "var(--color-green)" },
  ];

  return (
    <>
      {/* Heading lives here (not in the parent page) so it can share one
          row with the action button/link, per user request - they were
          previously stacked in separate rows well below the heading. */}
      <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide mb-0.5" style={{ color: "var(--color-muted)" }}>
            Invoice Number
          </div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{invoice.invoice_number}</h1>
            <span className="mono text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--color-accent-tint, #e2efef)", color: "var(--color-accent-ink, #0a5e6d)" }}>
              {invoice.source === "preloaded" ? "Pre-uploaded invoice - live extraction" : "Real upload - live extraction"}
            </span>
          </div>
          <p className="text-sm text-[var(--color-muted)] mt-1">{invoice.sold_to}</p>
        </div>
        {stage === "scan" && (invoiceFileUrl || lastScannedImageUrl || scannedCount > 0) && (
          <div className="flex flex-col items-end gap-2 shrink-0">
            {scannedCount > 0 && (
              <button
                onClick={() => setStage("summary")}
                className="rounded-lg px-4 py-2 text-sm font-semibold text-white flex items-center gap-2 whitespace-nowrap"
                style={{ background: "linear-gradient(135deg, var(--color-accent), #0a5e6d)" }}
              >
                View Summary <ArrowRight size={14} strokeWidth={2.5} />
              </button>
            )}
            <div className="flex items-center gap-2">
              {lastScannedImageUrl && (
                <button
                  onClick={() => setPreview({ url: lastScannedImageUrl, title: "Scanned Photo" })}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1.5 rounded-full transition-colors whitespace-nowrap"
                  style={{ background: "var(--color-accent-tint, #e2efef)", color: "var(--color-accent-ink, #0a5e6d)" }}
                >
                  <ImageIcon size={12} strokeWidth={2.5} />
                  View Image
                </button>
              )}
              {invoiceFileUrl && (
                <button
                  onClick={() => setPreview({ url: invoiceFileUrl, title: "Invoice Document" })}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1.5 rounded-full transition-colors whitespace-nowrap"
                  style={{ background: "var(--color-accent-tint, #e2efef)", color: "var(--color-accent-ink, #0a5e6d)" }}
                >
                  <FileText size={12} strokeWidth={2.5} />
                  View Invoice
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
        className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6"
      >
        {statCards.map((s) => (
          <div
            key={s.label}
            className="rounded-xl border bg-white px-4 py-3.5 flex items-center gap-3 transition-shadow hover:shadow-md"
            style={{ borderColor: "var(--color-line)" }}
          >
            <div className="h-9 w-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: "var(--color-paper)" }}>
              <s.Icon size={16} style={{ color: s.accent }} strokeWidth={2.25} />
            </div>
            <div className="min-w-0">
              <div className="text-lg font-bold leading-tight mono">{s.value}</div>
              <div className="text-[11px] text-[var(--color-muted)] truncate">{s.label}</div>
            </div>
          </div>
        ))}
      </motion.div>

      <AnimatePresence mode="wait">
      {stage === "scan" && (
        <motion.div key="scan" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}>
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
              {allQuantitiesMatched ? "Re-scan box / item - one or multiple photos" : "Scan box / item - one or multiple photos"}
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
                  : allQuantitiesMatched
                  ? "Ready to Re-scan - add one photo, or several, then Re-Scan Photos"
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
                  {busy
                    ? "Decoding…"
                    : allQuantitiesMatched
                    ? (files.length > 1 ? `Re-Scan ${files.length} Photos` : "Re-Scan Photo")
                    : (files.length > 1 ? `Scan ${files.length} Photos` : "Scan Photo")}
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

      <RecaptureModal
        open={rejection != null}
        message={rejection?.message ?? ""}
        imagePreview={previews[0] ?? null}
        onRecapture={handleRecapture}
      />
      <AnalyzingModal active={busy} />
      <Modal open={preview != null} onClose={() => setPreview(null)} title={preview?.title ?? ""} half>
        {preview && (
          preview.url.toLowerCase().endsWith(".pdf") ? (
            <iframe src={preview.url} title={preview.title} className="w-full h-full border-0" />
          ) : (
            <img src={preview.url} alt={preview.title} className="max-w-full max-h-full object-contain" />
          )
        )}
      </Modal>
    </>
  );
}
