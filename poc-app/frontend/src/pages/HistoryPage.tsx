import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Plus } from "lucide-react";
import { api } from "../api";
import { formatDate } from "../format";
import StatusBadge from "../components/StatusBadge";
import type { AllShipmentsSummary, Status } from "../types";

const FILTERS: { key: Status | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "green", label: "Validated" },
  { key: "yellow", label: "Pending" },
  { key: "red", label: "Exceptions" },
  { key: "pending", label: "Not scanned" },
];

export default function HistoryPage() {
  const [summary, setSummary] = useState<AllShipmentsSummary | null>(null);
  const [filter, setFilter] = useState<Status | "all">("all");
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.getAllShipmentsSummary().then(setSummary).catch(() => setSummary(null));
  }, []);

  const rows = useMemo(() => {
    if (!summary) return [];
    return summary.shipments.filter((s) => {
      if (filter !== "all" && s.overall_status !== filter) return false;
      if (query && !s.invoice_number.toLowerCase().includes(query.toLowerCase())) return false;
      return true;
    });
  }, [summary, filter, query]);

  return (
    <div className="px-8 py-8 max-w-6xl">
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
          to="/validate"
          className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold text-white shrink-0 hover:opacity-90 transition-opacity ml-auto"
          style={{ background: "var(--color-accent)" }}
        >
          <Plus size={15} strokeWidth={2.5} />
          Upload Invoice
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
                <td className="py-3 px-4"><StatusBadge status={s.overall_status} /></td>
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
