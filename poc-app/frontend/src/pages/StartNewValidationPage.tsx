import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, ExternalLink, FileSearch, FileText, Loader2, PackageSearch, ScanLine, Sparkles } from "lucide-react";
import { api, fileUrl } from "../api";
import ScannerFrame from "../components/ScannerFrame";
import RecaptureModal from "../components/RecaptureModal";
import type { Invoice, SapInvoiceRow } from "../types";

/**
 * "Start New Validation" — a second, streamlined entry point into the same
 * real (non-mock) scan pipeline RealScanFlow already uses, per the client's
 * spec: pick a pre-uploaded invoice from a dropdown, scan/capture an item
 * photo, hit one button, land straight on the existing details page
 * (ValidationWizardPage -> RealScanFlow) with the analysis already run.
 * Deliberately does NOT reimplement extraction, matching, or the results
 * table — it only collects the two inputs and calls the same
 * api.uploadRealScan the existing flow uses, then navigates away.
 */
export default function StartNewValidationPage() {
  const navigate = useNavigate();
  const [invoices, setInvoices] = useState<SapInvoiceRow[] | null>(null);
  const [selected, setSelected] = useState("");
  const [invoiceDetail, setInvoiceDetail] = useState<Invoice | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A rejected scan (nothing recorded server-side) - shown as a blocking
  // popup with the actual offending photo, per user directive, rather
  // than a passive inline banner. Cleared only by the Re-capture action.
  const [rejection, setRejection] = useState<{ message: string } | null>(null);

  useEffect(() => {
    api.listPreloadedInvoices().then(setInvoices).catch(() => setInvoices([]));
  }, []);

  // Preview the selected invoice in the space next to the scanner, instead
  // of leaving it blank — a user picking from the dropdown should be able
  // to see what they're about to scan against at a glance.
  useEffect(() => {
    if (!selected) { setInvoiceDetail(null); return; }
    let cancelled = false;
    setDetailLoading(true);
    api.getInvoice(selected).then((inv) => {
      if (!cancelled) setInvoiceDetail(inv);
    }).catch(() => {
      if (!cancelled) setInvoiceDetail(null);
    }).finally(() => {
      if (!cancelled) setDetailLoading(false);
    });
    return () => { cancelled = true; };
  }, [selected]);

  function addFiles(newFiles: File[]) {
    setError(null);
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

  async function startAnalysis() {
    if (!selected || files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      // Artificial minimum wait so the button feels like it's actually
      // scanning the photo rather than resolving instantly - real scan time
      // still wins if it happens to take longer than this floor.
      const [res] = await Promise.all([
        api.uploadRealScan(selected, files),
        new Promise((resolve) => setTimeout(resolve, 3000)),
      ]);
      // Block navigation whenever the scan wasn't clean - not just when
      // the backend rejected it outright (results.length === 0), but also
      // whenever it found stock that doesn't belong to this invoice
      // (res.unmatched, e.g. unrelated products mixed into the same
      // photo). Checking `unmatched` directly here is deliberate: it's
      // real data already present in the response regardless of how any
      // backend rejection heuristic classified the photo, so it can't
      // silently miss a case the way a threshold-tuned gate can.
      const unmatchedCount = res.unmatched.reduce((s, u) => s + u.count, 0);
      if (res.results.length === 0 || unmatchedCount > 0) {
        setRejection({
          message:
            res.message ||
            (unmatchedCount > 0
              ? `This photo includes ${unmatchedCount} item(s) that don't match any line on ${selected} ` +
                "(other stock mixed in with what you're validating). Please make sure only this " +
                "invoice's item(s) are in frame, then rescan."
              : "Couldn't read a barcode from this photo - try a straight-on, well-lit, uncropped photo of the item label."),
        });
        setBusy(false);
        return;
      }
      navigate(`/validate/${selected}`);
    } catch (e) {
      setError(String(e));
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

  const ready = Boolean(selected) && files.length > 0 && !busy;
  const invoiceFileUrl = fileUrl(invoiceDetail?.source_file_name);
  // Rendered flat image of the PDF's first page - see the matching
  // save_name.replace(...) convention in seed_data.py's _seed_preloaded_pdf.
  const previewImageUrl = fileUrl(invoiceDetail?.source_file_name?.replace(".pdf", "_preview.png"));

  return (
    <div className="px-8 py-8 max-w-6xl">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
        <div className="flex items-center gap-3 mb-1">
          <div
            className="h-9 w-9 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: "linear-gradient(135deg, var(--color-accent), #0a5e6d)" }}
          >
            <ScanLine size={17} className="text-white" strokeWidth={2.25} />
          </div>
          <h1 className="text-2xl font-bold">Start Validation</h1>
        </div>
        <p className="text-sm text-[var(--color-muted)] mb-7 max-w-2xl">
          Pick a pre-uploaded invoice, scan the shipment with your camera or upload a photo, then run the
          analysis - you'll land straight on the full invoice ↔ scan ↔ Tatmeen result.
        </p>
      </motion.div>

      <div className="grid lg:grid-cols-5 gap-8 items-stretch">
        {/* --- Left: invoice picker + scanner + start --- */}
        <div className="lg:col-span-3 flex flex-col">
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06, duration: 0.3 }} className="mb-7">
            <label className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-2 block">
              Select Invoice
            </label>
            <div className="relative">
              <PackageSearch size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--color-muted)] pointer-events-none" strokeWidth={2.25} />
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                disabled={!invoices || invoices.length === 0}
                className="w-full appearance-none rounded-xl border bg-white pl-10 pr-4 py-3 text-sm font-medium disabled:opacity-50"
                style={{ borderColor: "var(--color-line)" }}
              >
                {!invoices && <option value="">Loading invoices…</option>}
                {invoices && invoices.length === 0 && <option value="">No pre-uploaded invoices available</option>}
                {invoices && invoices.length > 0 && <option value="">Please select invoice</option>}
                {invoices?.map((inv) => (
                  <option key={inv.invoice_number} value={inv.invoice_number}>
                    {inv.invoice_number} - {inv.supplier}
                  </option>
                ))}
              </select>
            </div>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12, duration: 0.3 }} className="mb-6">
            <label className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-2 block">
              Scan the shipment
            </label>
            <ScannerFrame
              files={files}
              previews={previews}
              onAddFiles={addFiles}
              onRemoveFile={removeFile}
              status={
                error ? "Scan failed"
                  : files.length > 0 ? "Photo(s) captured - ready to start analysis"
                  : "Ready - capture a photo, or upload one from your device"
              }
              statusVariant={error ? "error" : files.length > 0 ? "success" : "idle"}
            />
            {error && (
              <p className="text-sm rounded-lg p-3 mt-2" style={{ background: "var(--color-red-tint)", color: "var(--color-red)" }}>
                {error}
              </p>
            )}
            {/* Guaranteed fallback: the same rejection message also shown
                inline, in case the popup can't render for some reason -
                so it's never possible to see nothing at all. */}
            {rejection && (
              <div className="text-sm rounded-lg p-3 mt-2" style={{ background: "var(--color-red-tint)", color: "var(--color-red)" }}>
                <p className="font-semibold mb-1">Please rearrange and retake the photo</p>
                <p>{rejection.message}</p>
              </div>
            )}
          </motion.div>

          <motion.button
            whileHover={ready ? { scale: 1.01 } : {}}
            whileTap={ready ? { scale: 0.99 } : {}}
            onClick={startAnalysis}
            disabled={!ready}
            className="w-full rounded-xl px-5 py-3.5 text-sm font-semibold text-white disabled:opacity-50 flex items-center justify-center gap-2"
            style={{ background: "linear-gradient(135deg, var(--color-accent), #0a5e6d)" }}
          >
            <AnimatePresence mode="wait" initial={false}>
              {busy ? (
                <motion.span key="busy" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2">
                  <Loader2 size={15} className="animate-spin" />
                  Analyzing - extracting, matching, checking Tatmeen…
                </motion.span>
              ) : (
                <motion.span key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2">
                  <Sparkles size={15} strokeWidth={2.25} />
                  Start Analysis
                </motion.span>
              )}
            </AnimatePresence>
          </motion.button>
        </div>

        {/* --- Right: preview of the selected invoice --- */}
        <div className="lg:col-span-2 flex flex-col">
          <label className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-2 block">
            Invoice preview
          </label>
          {/* flex-1 + items-stretch on the row above make this card match
              the left column's height exactly - no more fixed pixel guess
              that either clips the image or leaves a blank gap below it. */}
          <div className="rounded-xl border bg-white overflow-hidden flex-1 flex flex-col" style={{ borderColor: "var(--color-line)" }}>
            {!selected && (
              <motion.div
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}
                className="flex-1 flex flex-col items-center justify-center gap-4 px-8 text-center"
              >
                <motion.div
                  animate={{ y: [0, -7, 0] }}
                  transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
                  className="h-14 w-14 rounded-2xl flex items-center justify-center"
                  style={{ background: "var(--color-paper)", border: "1.5px dashed var(--color-line)" }}
                >
                  <FileSearch size={22} style={{ color: "var(--color-accent)" }} strokeWidth={1.75} />
                </motion.div>
                <div>
                  <p className="text-sm font-semibold">No invoice selected yet</p>
                  <p className="text-xs text-[var(--color-muted)] mt-1 max-w-[240px]">
                    Pick one from the dropdown on the left and it'll show up here.
                  </p>
                </div>
                <motion.div
                  animate={{ x: [0, -6, 0] }}
                  transition={{ duration: 1.3, repeat: Infinity, ease: "easeInOut" }}
                  className="flex items-center gap-1.5 text-xs font-semibold"
                  style={{ color: "var(--color-accent)" }}
                >
                  <ArrowLeft size={13} strokeWidth={2.5} /> Select Invoice
                </motion.div>
              </motion.div>
            )}

            {selected && detailLoading && (
              <div className="flex-1 flex items-center justify-center text-sm text-[var(--color-muted)]">Loading invoice…</div>
            )}

            {selected && !detailLoading && invoiceDetail && (
              <AnimatePresence mode="wait">
                <motion.div
                  key={invoiceDetail.invoice_number}
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}
                  className="flex-1 flex flex-col min-h-0"
                >
                  {/* Thin identity bar - the PDF itself shows every other detail */}
                  <div className="px-4 py-2.5 flex items-center justify-between gap-3 shrink-0" style={{ background: "linear-gradient(135deg, #0b7285, #0d2523)" }}>
                    <div className="flex items-center gap-2 text-white min-w-0">
                      <FileText size={14} strokeWidth={2.25} className="shrink-0" />
                      <span className="mono font-semibold text-xs truncate">TAX INVOICE: {invoiceDetail.invoice_number}</span>
                    </div>
                    {invoiceFileUrl && (
                      <a
                        href={invoiceFileUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full text-white/90 shrink-0 transition-colors hover:bg-white/25"
                        style={{ background: "rgba(255,255,255,0.15)" }}
                      >
                        Open full PDF <ExternalLink size={10} strokeWidth={2.5} />
                      </a>
                    )}
                  </div>

                  {previewImageUrl ? (
                    // A flat rendered image, not an embedded PDF - Chrome's
                    // built-in PDF viewer carries its own floating toolbar
                    // (download/print/more) that current versions no longer
                    // let a page suppress via URL fragment params. An <img>
                    // has none of that chrome at all, just the document.
                    // flex-1 + overflow-y-auto: fills exactly the space
                    // available (matching the left column), scrolling only
                    // if the page image is genuinely taller than that.
                    <div className="flex-1 overflow-y-auto" style={{ background: "var(--color-paper)" }}>
                      <img src={previewImageUrl} alt={`Invoice ${invoiceDetail.invoice_number}`} className="w-full block" />
                    </div>
                  ) : (
                    <div className="flex-1 flex items-center justify-center text-sm text-[var(--color-muted)]">
                      No preview is available for this invoice.
                    </div>
                  )}
                </motion.div>
              </AnimatePresence>
            )}
          </div>
        </div>
      </div>

      <RecaptureModal
        open={rejection != null}
        message={rejection?.message ?? ""}
        imagePreview={previews[0] ?? null}
        onRecapture={handleRecapture}
      />
    </div>
  );
}
