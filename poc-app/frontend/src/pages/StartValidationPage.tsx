import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight, Building2, CalendarDays, FileText, Layers, ListChecks, Loader2,
  Package, PackageSearch, Pill, PlugZap, ScanBarcode, Search, Sparkles, UploadCloud,
} from "lucide-react";
import { api } from "../api";
import { formatDate } from "../format";
import UploadDropzone from "../components/UploadDropzone";
import StatusBadge from "../components/StatusBadge";
import type { SapInvoiceRow } from "../types";

/**
 * Unified "Start Validation" entry point — per the spec's Step 1 + Step 2,
 * which describes ONE screen with two sections side by side: a list of
 * dummy invoices presented as fetched from SAP, and a manual upload
 * option. Previously these lived on two separate nav pages ("New
 * Validation" vs "Demo Scenarios") — merged here to match the spec's
 * actual described flow: "Select Invoice from SAP OR Upload Invoice" is
 * one branching step, not two destinations.
 */

// Client's 7 demo flows + bonus (Claude.md) each have a fixed meaning —
// used here purely to give each SAP row a descriptive chip/icon instead of
// a bare invoice number, no backend change needed.
const FLOW_META: Record<string, { label: string; Icon: typeof Pill; accent: string; tint: string }> = {
  "1": { label: "All Pharma", Icon: Pill, accent: "#0b7285", tint: "#e2efef" },
  "2": { label: "Pharma - Not Reported", Icon: Pill, accent: "#a9722e", tint: "#f3e9d9" },
  "3": { label: "OCR Fallback", Icon: ScanBarcode, accent: "#6b4fa0", tint: "#ece5f6" },
  "4": { label: "SSCC Reported", Icon: Layers, accent: "#0b7285", tint: "#e2efef" },
  "5": { label: "SSCC Not Reported", Icon: Layers, accent: "#a9722e", tint: "#f3e9d9" },
  "6": { label: "Mixed Pharma + Non-Pharma", Icon: PackageSearch, accent: "#0b7285", tint: "#e2efef" },
  "7": { label: "Non-Pharma Only", Icon: Package, accent: "#2f6b4f", tint: "#e4efe8" },
  bonus: { label: "Tatmeen Pending", Icon: Sparkles, accent: "#a9722e", tint: "#f3e9d9" },
  // Neutral fallback for anything that isn't one of the 7 fixed flows or
  // the INV008 bonus - specifically, an invoice pulled in via the search
  // box below. "Tatmeen Pending" used to double as this fallback too,
  // which was wrong for a freshly-fetched invoice that hasn't been
  // scanned at all yet, let alone reached a Tatmeen-pending state.
  default: { label: "From SAP", Icon: FileText, accent: "#57635f", tint: "#eef1f0" },
};

function flowMeta(demoFlow: number | null, invoiceNumber: string) {
  if (invoiceNumber === "INV008") return FLOW_META.bonus;
  if (demoFlow != null && FLOW_META[String(demoFlow)]) return FLOW_META[String(demoFlow)];
  return FLOW_META.default;
}

export default function StartValidationPage() {
  const navigate = useNavigate();
  const [sapInvoices, setSapInvoices] = useState<SapInvoiceRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listSapInvoices().then(setSapInvoices).catch(() => setSapInvoices([]));
  }, []);

  const stats = useMemo(() => {
    const rows = sapInvoices ?? [];
    const totalUnits = rows.reduce((s, r) => s + r.total_quantity, 0);
    const scanned = rows.filter((r) => r.status !== "pending").length;
    return { count: rows.length, totalUnits, scanned, ready: rows.length - scanned };
  }, [sapInvoices]);

  const visibleInvoices = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sapInvoices ?? [];
    return (sapInvoices ?? []).filter((inv) => inv.invoice_number.toLowerCase().includes(q));
  }, [sapInvoices, query]);

  // Searching an invoice number that isn't already in the list pulls it
  // "from SAP" directly - per user request, the fixed 8 demo invoices
  // used to be the only thing searchable. A number nobody's seen before
  // gets a genuinely generated (server-side, not fabricated in the
  // browser) SAP invoice, persisted like any other, so clicking into it
  // runs through the exact same validation flow as any sample invoice.
  async function searchSap() {
    const q = query.trim();
    if (!q) return;
    const alreadyListed = (sapInvoices ?? []).some((inv) => inv.invoice_number.toLowerCase() === q.toLowerCase());
    if (alreadyListed) return; // already visible via the live filter above
    setSearching(true);
    setSearchError(null);
    try {
      const inv = await api.searchSapInvoice(q);
      setSapInvoices((prev) => [inv, ...(prev ?? []).filter((x) => x.invoice_number !== inv.invoice_number)]);
    } catch (e) {
      setSearchError(String(e));
    } finally {
      setSearching(false);
    }
  }

  function handleFile(f: File) {
    setFile(f);
    setError(null);
    if (f.type.startsWith("image/")) setPreview(URL.createObjectURL(f));
    else setPreview(null);
  }

  async function submitUpload() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const invoice = await api.uploadInvoice(file);
      navigate(`/validate/${invoice.invoice_number}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="px-8 py-8 max-w-6xl">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
        <div className="flex items-center gap-3 mb-1">
          <div
            className="h-9 w-9 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: "linear-gradient(135deg, var(--color-accent), #0a5e6d)" }}
          >
            <PlugZap size={17} className="text-white" strokeWidth={2.25} />
          </div>
          <h1 className="text-2xl font-bold">Upload Invoice</h1>
        </div>
        <p className="text-sm text-[var(--color-muted)] mb-6 max-w-2xl">
          Pick an invoice already in the system, or upload a new one - either path runs the same
          real matching, discrepancy, and Tatmeen validation engine.
        </p>
      </motion.div>

      {/* --- Stat strip --- */}
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08, duration: 0.35 }}
        className="grid grid-cols-3 gap-4 mb-7"
      >
        {[
          { label: "Invoices in system", value: stats.count, Icon: FileText, accent: "var(--color-accent)" },
          { label: "Ready to validate", value: stats.ready, Icon: ListChecks, accent: "var(--color-green)" },
          { label: "Total units tracked", value: stats.totalUnits, Icon: Layers, accent: "var(--color-yellow)" },
        ].map((s) => (
          <div
            key={s.label}
            className="rounded-xl border bg-white px-4 py-3.5 flex items-center gap-3 transition-shadow hover:shadow-md"
            style={{ borderColor: "var(--color-line)" }}
          >
            <div className="h-9 w-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: "var(--color-paper)" }}>
              <s.Icon size={16} style={{ color: s.accent }} strokeWidth={2.25} />
            </div>
            <div className="min-w-0">
              <div className="text-lg font-bold leading-tight mono">{sapInvoices ? s.value : "-"}</div>
              <div className="text-[11px] text-[var(--color-muted)] truncate">{s.label}</div>
            </div>
          </div>
        ))}
      </motion.div>

      <div className="grid lg:grid-cols-5 gap-6">
        {/* --- Section 1: Invoices from SAP --- */}
        <div className="lg:col-span-3">
          <div className="flex items-center gap-2 mb-3">
            <h2 className="font-semibold">Invoices from SAP</h2>
            <span className="mono text-[10px] px-2 py-0.5 rounded-full" style={{ background: "var(--color-accent-tint, #e2efef)", color: "var(--color-accent-ink, #0a5e6d)" }}>
              Fetched from SAP
            </span>
          </div>

          <div className="flex items-center gap-2 mb-4">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-muted)]" strokeWidth={2.25} />
              <input
                value={query}
                onChange={(e) => { setQuery(e.target.value); setSearchError(null); }}
                onKeyDown={(e) => { if (e.key === "Enter") searchSap(); }}
                placeholder="Search invoice number…"
                className="w-full rounded-lg border pl-9 pr-3 py-2 text-sm bg-white"
                style={{ borderColor: "var(--color-line)" }}
              />
            </div>
            <button
              onClick={searchSap}
              disabled={!query.trim() || searching}
              className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-50 shrink-0"
              style={{ background: "var(--color-accent)" }}
            >
              {searching ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} strokeWidth={2.5} />}
              {searching ? "Fetching from SAP…" : "Search SAP"}
            </button>
          </div>
          {searchError && (
            <p className="text-xs mb-3" style={{ color: "var(--color-red)" }}>{searchError}</p>
          )}

          <div className="space-y-2">
            <AnimatePresence>
              {visibleInvoices.map((inv, i) => {
                const meta = flowMeta(inv.demo_flow, inv.invoice_number);
                return (
                  <motion.div
                    key={inv.invoice_number}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.035, duration: 0.25 }}
                    whileHover={{ y: -2 }}
                    onClick={() => navigate(`/validate/${inv.invoice_number}`)}
                    className="group rounded-xl border bg-white px-4 py-3 flex items-center gap-4 cursor-pointer transition-shadow hover:shadow-lg"
                    style={{ borderColor: "var(--color-line)" }}
                  >
                    <div
                      className="h-10 w-10 rounded-lg flex items-center justify-center shrink-0 transition-transform group-hover:scale-105"
                      style={{ background: meta.tint }}
                    >
                      <meta.Icon size={17} style={{ color: meta.accent }} strokeWidth={2.25} />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="mono font-semibold text-sm">{inv.invoice_number}</span>
                        <span
                          className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                          style={{ background: meta.tint, color: meta.accent }}
                        >
                          {meta.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-[var(--color-muted)]">
                        <span className="flex items-center gap-1"><Building2 size={12} />{inv.supplier}</span>
                        <span className="flex items-center gap-1"><CalendarDays size={12} />{formatDate(inv.invoice_date)}</span>
                      </div>
                    </div>

                    <div className="text-right shrink-0 hidden sm:block">
                      <div className="text-sm font-semibold mono">{inv.total_quantity} <span className="font-normal text-[var(--color-muted)]">units</span></div>
                      <div className="text-[11px] text-[var(--color-muted)]">{inv.item_count} line item{inv.item_count === 1 ? "" : "s"}</div>
                    </div>

                    <StatusBadge status={inv.status} compact />

                    <ArrowRight
                      size={16}
                      className="shrink-0 text-[var(--color-muted)] transition-all -translate-x-1 opacity-0 group-hover:translate-x-0 group-hover:opacity-100"
                    />
                  </motion.div>
                );
              })}
            </AnimatePresence>

            {sapInvoices && query.trim() && visibleInvoices.length === 0 && !searching && (
              <div className="rounded-xl border bg-white py-8 text-center text-sm text-[var(--color-muted)]" style={{ borderColor: "var(--color-line)" }}>
                No match yet for "{query.trim()}" - press Enter or "Search SAP" to fetch it.
              </div>
            )}
            {sapInvoices && !query.trim() && sapInvoices.length === 0 && (
              <div className="rounded-xl border bg-white py-10 text-center text-sm text-[var(--color-muted)]" style={{ borderColor: "var(--color-line)" }}>
                No SAP invoices available.
              </div>
            )}
            {!sapInvoices && (
              <div className="rounded-xl border bg-white py-10 text-center text-sm text-[var(--color-muted)]" style={{ borderColor: "var(--color-line)" }}>
                Loading invoices…
              </div>
            )}
          </div>
        </div>

        {/* --- Section 2: Upload Invoice --- */}
        <div className="lg:col-span-2">
          <div className="flex items-center gap-2 mb-5">
            <h2 className="font-semibold">Get started</h2>
            <span className="mono text-[10px] px-2 py-0.5 rounded-full" style={{ background: "var(--color-accent-tint, #e2efef)", color: "var(--color-accent-ink, #0a5e6d)" }}>
              Live Extraction
            </span>
          </div>
          <motion.div
            initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }}
            whileHover={{ y: -3, boxShadow: "0 12px 28px -12px rgba(11,114,133,0.45)" }}
            transition={{ duration: 0.3, delay: 0.12 }}
            className="rounded-xl overflow-hidden mb-4"
            style={{ boxShadow: "0 4px 14px -8px rgba(11,114,133,0.35)" }}
          >
            <div className="p-5 text-white" style={{ background: "linear-gradient(135deg, #0b7285, #0d2523)" }}>
              <div className="text-xs opacity-80 mb-1">Upload &amp; extract</div>
              <div className="text-base font-semibold leading-snug">
                Run a new invoice ↔ scan ↔ Tatmeen validation
              </div>
            </div>
            <UploadDropzone
              embedded
              label="Upload the invoice"
              hint="PDF or image."
              onFile={handleFile}
              preview={preview}
              fileName={file?.name ?? null}
            />
          </motion.div>

          <AnimatePresence>
            {busy && (
              <motion.div
                initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                className="mt-3 rounded-lg border px-3 py-2.5 text-xs flex items-center gap-2 overflow-hidden"
                style={{ borderColor: "var(--color-line)", background: "var(--color-paper)" }}
              >
                <motion.div
                  animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
                  className="h-3.5 w-3.5 rounded-full border-2 border-t-transparent shrink-0"
                  style={{ borderColor: "var(--color-accent)", borderTopColor: "transparent" }}
                />
                Reading document with OCR - extracting GTIN, batch, quantity…
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                className="mt-3 text-sm rounded-lg p-3" style={{ background: "var(--color-red-tint)", color: "var(--color-red)" }}
              >
                <p className="mb-1">{error}</p>
                <p className="text-xs opacity-80">
                  Couldn't extract this document automatically - you can browse the Invoices from SAP
                  list on the left instead, or try a different file.
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          <motion.button
            whileHover={file && !busy ? { scale: 1.015 } : {}}
            whileTap={file && !busy ? { scale: 0.985 } : {}}
            onClick={submitUpload}
            disabled={!file || busy}
            className="mt-3 w-full rounded-lg px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50 flex items-center justify-center gap-2"
            style={{ background: "linear-gradient(135deg, var(--color-accent), #0a5e6d)" }}
          >
            <UploadCloud size={15} strokeWidth={2.25} />
            {busy ? "Reading document (OCR)…" : "Upload & Extract"}
          </motion.button>
        </div>
      </div>
    </div>
  );
}
