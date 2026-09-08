import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "../api";
import MockScanFlow from "../components/MockScanFlow";
import RealScanFlow from "../components/RealScanFlow";
import StatusBadge from "../components/StatusBadge";
import FinalSummary from "../components/FinalSummary";
import type { Invoice, Status, ValidationResult } from "../types";

type Stage = "invoice" | "scan" | "summary";

const STEPS: { key: Stage; label: string }[] = [
  { key: "invoice", label: "1. Invoice" },
  { key: "scan", label: "2. Scan Items" },
  { key: "summary", label: "3. Summary" },
];

function overallStatus(results: Record<number, ValidationResult>): Status {
  const values = Object.values(results);
  if (values.length === 0) return "pending";
  if (values.some((r) => r.overall_status === "red" && r.resolution_action !== "accepted")) return "red";
  if (values.some((r) => r.overall_status === "yellow" || r.overall_status === "pending")) return "yellow";
  return "green";
}

export default function ValidationWizardPage() {
  const { invoiceNumber } = useParams<{ invoiceNumber: string }>();
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [results, setResults] = useState<Record<number, ValidationResult>>({});
  const [stage, setStage] = useState<Stage>("invoice");
  const [invoiceExtracted, setInvoiceExtracted] = useState(false);
  const [extracting, setExtracting] = useState(false);

  useEffect(() => {
    if (!invoiceNumber) return;
    api.getInvoice(invoiceNumber).then(async (inv) => {
      setInvoice(inv);

      // State persistence: if this invoice already has any scan results,
      // skip straight past loading and go right to the scan step instead
      // of always starting the wizard blank.
      const r = await api.getResultsForInvoice(invoiceNumber).catch(() => null);
      if (r && Object.keys(r).length > 0) {
        setResults(r);
        setInvoiceExtracted(true);
        setStage("scan");
        return;
      }

      // Otherwise, load the invoice data automatically as soon as the
      // page opens - per user feedback, requiring a manual "Load Invoice
      // Data" click before showing anything was an unnecessary extra
      // step; the SAP-pull animation still plays briefly for realism, it
      // just isn't gated behind a click anymore.
      if (inv.source === "sap") extractInvoice();
    });
  }, [invoiceNumber]);

  // Keep results fresh whenever the Summary step is opened — MockScanFlow
  // and RealScanFlow update their own item state independently, so this
  // page's copy would otherwise go stale as soon as a scan happens.
  useEffect(() => {
    if (stage === "summary" && invoiceNumber) {
      api.getResultsForInvoice(invoiceNumber).then(setResults).catch(() => {});
    }
  }, [stage, invoiceNumber]);

  function extractInvoice() {
    setExtracting(true);
    setTimeout(() => {
      setExtracting(false);
      setInvoiceExtracted(true);
    }, 1100);
  }

  if (!invoice) return <div className="p-8 text-[var(--color-muted)]">Loading…</div>;

  // --- Real, freshly-uploaded invoice (or a pre-uploaded fixture routed
  // through the same real pipeline via the Start New Validation screen):
  // genuinely different flow, no seeded steps, no fake stepper — extraction
  // already happened at upload/seed time. Branches on `source`, not
  // `demo_flow` — INV008 (the bonus pending-status demo) has demo_flow=null
  // but source="sap", so demo_flow alone would have misrouted it into this
  // real-upload branch. Caught while wiring the unified Start Validation
  // page together. ---
  if (invoice.source === "upload" || invoice.source === "preloaded") {
    return (
      <div className="px-8 py-8">
        {invoice.source === "preloaded" ? (
          <Link to="/validate-new" className="text-sm text-[var(--color-accent)] hover:underline">
            ← Start New Validation
          </Link>
        ) : (
          <Link to="/validate" className="text-sm text-[var(--color-accent)] hover:underline">
            ← Upload a different invoice
          </Link>
        )}
        <div className="mt-3">
          <RealScanFlow invoice={invoice} />
        </div>
      </div>
    );
  }

  // --- SAP-sourced invoice (one of the 7 client flows + bonus): existing
  // mock-seed-driven guided wizard, clearly labeled as SAP data. ---
  return (
    <div className="px-8 py-8">
      <Link to="/validate" className="text-sm text-[var(--color-accent)] hover:underline">
        ← Back to Upload Invoice
      </Link>

      <div className="flex items-center justify-between mt-3 mb-1">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">
            {invoice.invoice_number}
            {invoice.demo_flow && <span className="ml-1 mono text-sm font-normal text-[var(--color-accent-ink)]">Flow {invoice.demo_flow}</span>}
          </h1>
          <span className="mono text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--color-accent-tint, #e2efef)", color: "var(--color-accent-ink, #0a5e6d)" }}>
            Fetched from SAP
          </span>
        </div>
        <StatusBadge status={overallStatus(results)} />
      </div>

      {/* Stepper */}
      <div className="flex items-center gap-2 mb-8 mt-4">
        {STEPS.map((s, i) => (
          <div key={s.key} className="flex items-center gap-2">
            <button
              onClick={() => s.key !== "scan" || invoiceExtracted ? setStage(s.key) : null}
              disabled={s.key === "scan" && !invoiceExtracted}
              className="text-sm font-medium px-3 py-1.5 rounded-full transition-colors disabled:opacity-40"
              style={
                stage === s.key
                  ? { background: "var(--color-accent)", color: "white" }
                  : { background: "white", color: "var(--color-muted)", border: "1px solid var(--color-line)" }
              }
            >
              {s.label}
            </button>
            {i < STEPS.length - 1 && <div className="w-6 h-px" style={{ background: "var(--color-line)" }} />}
          </div>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {stage === "invoice" && (
          <motion.div key="invoice" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}>
            <div className="rounded-xl border bg-white p-5" style={{ borderColor: "var(--color-line)" }}>
              <div className="flex items-center justify-between mb-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
                  Invoice data (from SAP) - review before continuing
                </div>
                {extracting && (
                  <div className="flex items-center gap-2 text-sm font-medium text-[var(--color-muted)]">
                    <motion.span
                      className="h-3.5 w-3.5 rounded-full border-2 border-[var(--color-accent)] border-t-transparent"
                      animate={{ rotate: 360 }}
                      transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }}
                    />
                    Loading from SAP…
                  </div>
                )}
              </div>

              {invoiceExtracted && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <div className="flex flex-wrap gap-6 mb-4 text-sm">
                    <div><span className="text-[var(--color-muted)]">Supplier </span><span className="font-medium">{invoice.supplier || "-"}</span></div>
                    <div><span className="text-[var(--color-muted)]">Items </span><span className="font-medium">{invoice.line_items.length}</span></div>
                    <div><span className="text-[var(--color-muted)]">Total Qty </span><span className="font-medium">{invoice.line_items.reduce((s, li) => s + li.qty, 0)}</span></div>
                  </div>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-[var(--color-muted)] border-b" style={{ borderColor: "var(--color-line)" }}>
                        <th className="pb-1.5 pt-1">Item</th>
                        <th className="pb-1.5 pt-1">GTIN</th>
                        <th className="pb-1.5 pt-1">Batch</th>
                        <th className="pb-1.5 pt-1">Qty</th>
                        <th className="pb-1.5 pt-1">Category</th>
                      </tr>
                    </thead>
                    <tbody className="mono">
                      {invoice.line_items.map((li) => (
                        <tr key={li.id} className="border-t" style={{ borderColor: "var(--color-line)" }}>
                          <td className="py-1.5 pr-2">{li.item_name}</td>
                          <td className="py-1.5 pr-2">{li.gtin ?? "-"}</td>
                          <td className="py-1.5 pr-2">{li.batch}</td>
                          <td className="py-1.5 pr-2">{li.qty} {li.uom}</td>
                          <td className="py-1.5">{li.category}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </motion.div>
              )}
            </div>
            {invoiceExtracted && (
              <motion.button
                initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                onClick={() => setStage("scan")}
                className="mt-5 rounded-lg px-4 py-2 text-sm font-semibold text-white"
                style={{ background: "var(--color-accent)" }}
              >
                Continue to Scan →
              </motion.button>
            )}
          </motion.div>
        )}

        {stage === "scan" && (
          <motion.div key="scan" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}>
            <MockScanFlow invoice={invoice} />
            <button
              onClick={() => setStage("summary")}
              className="mt-6 rounded-lg px-4 py-2 text-sm font-semibold text-white"
              style={{ background: "var(--color-accent)" }}
            >
              View Summary →
            </button>
          </motion.div>
        )}

        {stage === "summary" && (
          <motion.div key="summary" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}>
            <div className="mb-4">
              <FinalSummary invoice={invoice} results={results} />
            </div>
            <div className="flex gap-3">
              <Link to="/validate" className="rounded-lg px-4 py-2 text-sm font-semibold text-white" style={{ background: "var(--color-accent)" }}>
                Start Another Validation
              </Link>
              <Link to="/history" className="rounded-lg px-4 py-2 text-sm font-semibold" style={{ border: "1px solid var(--color-line)", color: "var(--color-ink)" }}>
                View History
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
