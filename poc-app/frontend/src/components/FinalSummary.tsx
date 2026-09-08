import { motion } from "framer-motion";
import {
  CheckCircle2, AlertTriangle, XCircle, Pill, Package, FileText,
  ExternalLink, ClipboardList, ScanLine, Layers,
} from "lucide-react";
import { fileUrl } from "../api";
import StatusBadge from "./StatusBadge";
import type { Invoice, UnmatchedBarcode, ValidationResult } from "../types";

/**
 * Final Validation Summary — spec Step 11. Four aggregate sub-sections
 * (Invoice, Physical Scan, Matching, Tatmeen) computed dynamically from
 * real results, a 3-tier final verdict, PLUS a per-item breakdown showing
 * each line item's real status and the actual discrepancy/validation
 * messages behind it — the aggregate counts alone answer "how many are
 * wrong," this answers "which ones, and why," which is what a reviewer
 * actually needs to act on before signing off a shipment.
 */
export default function FinalSummary({
  invoice, results, unmatched = [],
}: {
  invoice: Invoice;
  results: Record<number, ValidationResult>;
  unmatched?: UnmatchedBarcode[];
}) {
  const items = invoice.line_items;
  const scanned = items.filter((li) => results[li.id]);
  const notScanned = items.filter((li) => !results[li.id]);
  const extraCount = unmatched.length;

  const totalQtyInvoice = items.reduce((s, li) => s + li.qty, 0);
  const totalQtyDetected = scanned.reduce((s, li) => s + (results[li.id].cumulative.total_scanned || 0), 0);

  const matched = scanned.filter((li) => {
    const r = results[li.id];
    return r.invoice_match_status === "green" && r.quantity_status === "green" && r.resolution_action !== "rejected";
  });
  const mismatched = scanned.filter((li) => {
    const r = results[li.id];
    return (r.invoice_match_status === "red" || r.quantity_status === "red") && r.resolution_action !== "accepted";
  });

  const pharmaScanned = scanned.filter((li) => li.category === "pharma");
  const tatmeenReported = pharmaScanned.filter((li) => results[li.id].tatmeen_status === "green");
  const tatmeenNotReported = pharmaScanned.filter((li) =>
    results[li.id].tatmeen_status === "red" && !results[li.id].findings.some((f) => f.message.startsWith("Tatmeen Validation Failed"))
  );
  const tatmeenFailed = pharmaScanned.filter((li) =>
    results[li.id].findings.some((f) => f.message.startsWith("Tatmeen Validation Failed"))
  );
  const tatmeenPending = pharmaScanned.filter((li) => results[li.id].tatmeen_status === "yellow");

  // SSCC (rule 17) is deliberately reported as a non-critical "yellow"
  // finding at the item level (so its Status dot still reads "Matched" -
  // see ItemsTable's rowStatus mapping), but that doesn't mean it should be
  // invisible up here: an item whose SSCC genuinely isn't reported is a
  // real exception the shipment summary needs to say so about, not silently
  // fold into "Validation Successful" just because GTIN/qty/Tatmeen all
  // passed.
  const ssccApplicable = scanned.filter((li) => li.sscc);
  const ssccNotReported = ssccApplicable.filter((li) => results[li.id].sscc_status === "red");
  const ssccPending = ssccApplicable.filter((li) => results[li.id].sscc_status === "yellow");

  const anyUnresolvedRed = scanned.some((li) => results[li.id].overall_status === "red" && results[li.id].resolution_action !== "accepted");
  const anyException = mismatched.length > 0 || tatmeenNotReported.length > 0 || tatmeenFailed.length > 0 ||
    notScanned.length > 0 || extraCount > 0 || ssccNotReported.length > 0;

  let finalResult: { label: string; color: string; bg: string; Icon: typeof CheckCircle2 };
  if (anyUnresolvedRed) {
    finalResult = { label: "Human Intervention Required", color: "var(--color-red)", bg: "var(--color-red-tint)", Icon: XCircle };
  } else if (anyException) {
    finalResult = { label: "Validation Completed with Exceptions", color: "var(--color-yellow)", bg: "var(--color-yellow-tint)", Icon: AlertTriangle };
  } else {
    finalResult = { label: "Validation Successful", color: "var(--color-green)", bg: "var(--color-green-tint)", Icon: CheckCircle2 };
  }

  // A generic label alone ("Human Intervention Required") doesn't say WHAT
  // needs attention — this builds a real one-line breakdown from the actual
  // computed counts below it (matched/mismatched/missing/extra, and for
  // pharma items specifically, reported/not-reported/pending/failed against
  // Tatmeen), so the banner itself answers "which items, what's wrong"
  // instead of just "something's wrong."
  const breakdownParts: string[] = [];
  if (matched.length > 0) breakdownParts.push(`${matched.length} matched`);
  if (mismatched.length > 0) breakdownParts.push(`${mismatched.length} mismatched`);
  if (notScanned.length > 0) breakdownParts.push(`${notScanned.length} not scanned`);
  if (extraCount > 0) breakdownParts.push(`${extraCount} unidentified`);
  if (tatmeenReported.length > 0) breakdownParts.push(`${tatmeenReported.length} reported to Tatmeen`);
  if (tatmeenNotReported.length > 0) breakdownParts.push(`${tatmeenNotReported.length} not reported to Tatmeen`);
  if (tatmeenPending.length > 0) breakdownParts.push(`${tatmeenPending.length} pending Tatmeen confirmation`);
  if (tatmeenFailed.length > 0) breakdownParts.push(`${tatmeenFailed.length} Tatmeen check failed`);
  if (ssccNotReported.length > 0) breakdownParts.push(`${ssccNotReported.length} SSCC not reported`);
  if (ssccPending.length > 0) breakdownParts.push(`${ssccPending.length} SSCC pending confirmation`);
  const breakdown = breakdownParts.join(" · ");

  const invoiceFileUrl = fileUrl(invoice.source_file_name);

  return (
    <div className="rounded-xl border bg-white p-6" style={{ borderColor: "var(--color-line)" }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.3 }}
        className="rounded-lg p-5 mb-6 text-center" style={{ background: finalResult.bg }}
      >
        <finalResult.Icon size={28} strokeWidth={2} className="mx-auto mb-1.5" style={{ color: finalResult.color }} />
        <div className="text-lg font-bold" style={{ color: finalResult.color }}>{finalResult.label}</div>
        {breakdown && <div className="text-xs font-medium mt-1 opacity-80" style={{ color: finalResult.color }}>{breakdown}</div>}
      </motion.div>

      {/* Per-item breakdown - the actual "which item, what's wrong" view */}
      <div className="mb-6">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-2.5">
          <ClipboardList size={13} strokeWidth={2.5} />
          Item-by-Item Status
        </div>
        <div className="space-y-2">
          {items.map((li, i) => {
            const r = results[li.id];
            const Icon = li.category === "pharma" ? Pill : Package;
            const failFindings = r?.findings.filter((f) => f.severity === "fail") ?? [];
            return (
              <motion.div
                key={li.id}
                initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}
                className="rounded-lg border p-3" style={{ borderColor: "var(--color-line)" }}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <Icon size={14} className="shrink-0" style={{ color: "var(--color-muted)" }} strokeWidth={2.25} />
                    <span className="text-sm font-medium truncate">{li.item_name}</span>
                  </div>
                  <StatusBadge status={r?.overall_status ?? "pending"} compact />
                </div>
                {r && failFindings.length > 0 && (
                  <ul className="mt-2 pl-5 space-y-0.5" style={{ listStyleType: "disc" }}>
                    {failFindings.map((f, fi) => (
                      <li key={fi} className="text-xs" style={{ color: "var(--color-red)" }}>{f.message}</li>
                    ))}
                  </ul>
                )}
                {r?.resolution_action && (
                  <div className="mt-2 text-xs rounded-md px-2 py-1 inline-block" style={{ background: "var(--color-paper)", color: "var(--color-muted)" }}>
                    Reviewer: <b>{r.resolution_action}</b>{r.resolution_note ? ` - "${r.resolution_note}"` : ""}
                  </div>
                )}
                {!r && <div className="mt-1 text-xs" style={{ color: "var(--color-muted)" }}>Not scanned yet.</div>}
              </motion.div>
            );
          })}

          {unmatched.map((u, i) => (
            <motion.div
              key={`unmatched-${i}`}
              initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: (items.length + i) * 0.04 }}
              className="rounded-lg border p-3" style={{ borderColor: "var(--color-red)", background: "var(--color-red-tint)" }}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <AlertTriangle size={14} className="shrink-0" style={{ color: "var(--color-red)" }} strokeWidth={2.25} />
                  <span className="text-sm font-medium" style={{ color: "var(--color-red)" }}>Unidentified item ({u.count} unit{u.count === 1 ? "" : "s"})</span>
                </div>
              </div>
              <div className="mt-1 text-xs" style={{ color: "var(--color-red)" }}>{u.message}</div>
            </motion.div>
          ))}
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-5">
        <SummaryBlock title="Invoice Summary" Icon={FileText}>
          <Line label="Invoice Number" value={invoice.invoice_number} />
          <Line label="Total Items" value={String(items.length)} />
          <Line label="Total Quantity" value={String(totalQtyInvoice)} />
          {invoiceFileUrl && (
            <a
              href={invoiceFileUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-semibold mt-1.5"
              style={{ color: "var(--color-accent-ink, #0a5e6d)" }}
            >
              <FileText size={12} strokeWidth={2.5} />
              View uploaded invoice
              <ExternalLink size={10} strokeWidth={2.5} />
            </a>
          )}
        </SummaryBlock>

        <SummaryBlock title="Physical Scan Summary" Icon={ScanLine}>
          <Line label="Items Detected" value={`${scanned.length} / ${items.length}`} />
          <Line label="Total Quantity Detected" value={String(totalQtyDetected)} />
        </SummaryBlock>

        <SummaryBlock title="Matching Summary" Icon={CheckCircle2}>
          <Line label="Matched Items" value={String(matched.length)} good />
          <Line label="Mismatched Items" value={String(mismatched.length)} bad={mismatched.length > 0} />
          <Line label="Missing Items" value={String(notScanned.length)} bad={notScanned.length > 0} />
          <Line label="Extra Items" value={String(extraCount)} bad={extraCount > 0} />
        </SummaryBlock>

        <SummaryBlock title="Tatmeen Summary" Icon={Layers}>
          <Line label="Reported Items" value={String(tatmeenReported.length)} good />
          <Line label="Not Reported Items" value={String(tatmeenNotReported.length)} bad={tatmeenNotReported.length > 0} />
          <Line label="Pending Items" value={String(tatmeenPending.length)} />
          <Line label="Failed Validations" value={String(tatmeenFailed.length)} bad={tatmeenFailed.length > 0} />
          {ssccApplicable.length > 0 && (
            <>
              <Line label="SSCC Reported" value={String(ssccApplicable.length - ssccNotReported.length - ssccPending.length)} good />
              <Line label="SSCC Not Reported" value={String(ssccNotReported.length)} bad={ssccNotReported.length > 0} />
              {ssccPending.length > 0 && <Line label="SSCC Pending" value={String(ssccPending.length)} />}
            </>
          )}
        </SummaryBlock>
      </div>
    </div>
  );
}

function SummaryBlock({ title, Icon, children }: { title: string; Icon: typeof CheckCircle2; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border p-4 transition-shadow hover:shadow-sm" style={{ borderColor: "var(--color-line)" }}>
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-2">
        <Icon size={12} strokeWidth={2.5} />
        {title}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Line({ label, value, good, bad }: { label: string; value: string; good?: boolean; bad?: boolean }) {
  const color = bad ? "var(--color-red)" : good ? "var(--color-green)" : "var(--color-ink)";
  return (
    <div className="flex justify-between text-sm">
      <span className="text-[var(--color-muted)]">{label}</span>
      <span className="mono font-medium" style={{ color }}>{value}</span>
    </div>
  );
}
