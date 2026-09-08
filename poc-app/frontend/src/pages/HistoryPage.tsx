import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Plus } from "lucide-react";
import { api } from "../api";
import { formatDate } from "../format";
import StatusBadge from "../components/StatusBadge";
import { useAuth } from "../context/AuthContext";
import type { AllShipmentsSummary, ShipmentSummaryRow, Status } from "../types";

// Same 3-tier wording FinalSummary.tsx uses for its own verdict banner
// ("Validation Successful" / "Validation Completed with Exceptions" /
// "Human Intervention Required") - shown here in its shorter form since
// this is a compact table badge, not a banner headline. Shipment-level
// wording, distinct from StatusBadge's default per-line-item labels
// ("Warning", "Manual Intervention") which stay as-is elsewhere.
const SHIPMENT_STATUS_LABEL: Partial<Record<Status, string>> = {
  yellow: "Partially Validated",
  red: "Human Intervention Required",
};

const FILTERS: { key: Status | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "green", label: "Validated" },
  { key: "yellow", label: "Partially Validated" },
  { key: "red", label: "Human Intervention Required" },
  { key: "pending", label: "Not scanned" },
];

export default function HistoryPage() {
  const { user } = useAuth();
  // If "Upload Invoice" isn't a tab this account can see, send the quick
  // action to "Start Validation" instead - the equivalent action they do
  // have access to - rather than a link that just bounces them back.
  const uploadLinkTo = !user?.allowedNav || user.allowedNav.includes("/validate") ? "/validate" : "/validate-new";
  const [summary, setSummary] = useState<AllShipmentsSummary | null>(null);
  const [filter, setFilter] = useState<Status | "all">("all");
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.getAllShipmentsSummary().then(setSummary).catch(() => setSummary(null));
  }, []);

  // Sara's account (allowedNav set) only ever works the 7 pre-loaded
  // invoices meant for real processing (source="preloaded") - not the
  // INV001-INV007 SAP demo-flow showcase invoices. Any unrestricted
  // account (e.g. the Manager login) sees every invoice, same as before.
  const restrictedToPreloaded = Boolean(user?.allowedNav);

  // "Invoice 1" at the top, ascending from there - same ordinal the Start
  // Validation dropdown sorts by. Preloaded invoices carry it as "Invoice N
  // - ..." in their supplier label; the SAP demo-flow invoices (INV001-007)
  // carry the same ordinal directly as demo_flow. Anything with neither
  // (e.g. INV008) sorts to the end rather than disturbing the rest.
  function invoiceOrdinal(s: ShipmentSummaryRow): number {
    const fromSupplier = Number(s.supplier.match(/^Invoice (\d+)/)?.[1]);
    if (!Number.isNaN(fromSupplier)) return fromSupplier;
    return s.demo_flow ?? Infinity;
  }

  const rows = useMemo(() => {
    if (!summary) return [];
    return summary.shipments
      .filter((s) => {
        if (restrictedToPreloaded && s.source !== "preloaded") return false;
        if (filter !== "all" && s.overall_status !== filter) return false;
        if (query && !s.invoice_number.toLowerCase().includes(query.toLowerCase())) return false;
        return true;
      })
      .sort((a, b) => invoiceOrdinal(a) - invoiceOrdinal(b));
  }, [summary, filter, query, restrictedToPreloaded]);

  return (
    <div className="px-8 py-8">
      <h1 className="text-2xl font-bold mb-1">Shipment History</h1>
      <p className="text-sm text-[var(--color-muted)] mb-6">
        Every invoice validated so far, with its latest reconciliation status.
      </p>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search invoice number…"
          className="rounded-lg border px-3 py-2 text-sm bg-white"
          style={{ borderColor: "var(--color-line)" }}
        />
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className="text-xs font-medium px-3 py-1.5 rounded-full transition-colors"
              style={
                filter === f.key
                  ? { background: "var(--color-accent)", color: "white" }
                  : { background: "white", color: "var(--color-muted)", border: "1px solid var(--color-line)" }
              }
            >
              {f.label}
            </button>
          ))}
        </div>
        <Link
          to={uploadLinkTo}
          className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold text-white shrink-0 hover:opacity-90 transition-opacity ml-auto"
          style={{ background: "var(--color-accent)" }}
        >
          <Plus size={15} strokeWidth={2.5} />
          {uploadLinkTo === "/validate" ? "Upload Invoice" : "Start Validation"}
        </Link>
      </div>

      <div className="rounded-xl border bg-white overflow-hidden" style={{ borderColor: "var(--color-line)" }}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-[var(--color-muted)] border-b" style={{ borderColor: "var(--color-line)" }}>
              <th className="py-3 px-4">Invoice</th>
              <th className="py-3 px-4">Flow</th>
              <th className="py-3 px-4">Date</th>
              <th className="py-3 px-4">Items</th>
              <th className="py-3 px-4">Progress</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s, i) => (
              <motion.tr
                key={s.invoice_number}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.03 }}
                className="border-b last:border-0 hover:bg-[var(--color-paper)] transition-colors"
                style={{ borderColor: "var(--color-line)" }}
              >
                <td className="py-3 px-4 mono font-medium">{s.invoice_number}</td>
                <td className="py-3 px-4 text-[var(--color-muted)]">{s.demo_flow ? `Flow ${s.demo_flow}` : "-"}</td>
                <td className="py-3 px-4 text-[var(--color-muted)]">{formatDate(s.invoice_date)}</td>
                <td className="py-3 px-4">{s.item_count}</td>
                <td className="py-3 px-4 text-[var(--color-muted)]">{s.scanned_count}/{s.item_count} scanned</td>
                <td className="py-3 px-4"><StatusBadge status={s.overall_status} label={SHIPMENT_STATUS_LABEL[s.overall_status]} /></td>
                <td className="py-3 px-4 text-right">
                  <Link to={`/validate/${s.invoice_number}`} className="text-[var(--color-accent)] text-xs font-medium hover:underline">
                    Open →
                  </Link>
                </td>
              </motion.tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="py-8 text-center text-[var(--color-muted)]">
                  No shipments match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
