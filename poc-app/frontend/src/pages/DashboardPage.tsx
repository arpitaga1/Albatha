import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { api } from "../api";
import { useAuth } from "../context/AuthContext";
import StatusBadge from "../components/StatusBadge";
import DonutChart from "../components/DonutChart";
import type { AllShipmentsSummary } from "../types";

const TILES = [
  { key: "total", label: "Total shipments", color: "var(--color-accent)" },
  { key: "green", label: "Validated", color: "var(--color-green)" },
  { key: "yellow", label: "Pending / review", color: "var(--color-yellow)" },
  { key: "red", label: "Exceptions", color: "var(--color-red)" },
];

export default function DashboardPage() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<AllShipmentsSummary | null>(null);

  useEffect(() => {
    api.getAllShipmentsSummary().then(setSummary).catch(() => setSummary(null));
  }, []);

  const counts = summary?.counts ?? {};
  const values: Record<string, number> = {
    total: summary?.total ?? 0,
    green: counts.green ?? 0,
    yellow: counts.yellow ?? 0,
    red: counts.red ?? 0,
  };
  const tatmeenCounts = summary?.tatmeen_counts ?? {};
  const categoryCounts = summary?.category_counts ?? {};
  const tatmeenTotal = (tatmeenCounts.green ?? 0) + (tatmeenCounts.yellow ?? 0) + (tatmeenCounts.red ?? 0);

  return (
    <div className="px-8 py-8">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        <p className="text-sm text-[var(--color-muted)]">Welcome back, {user?.name?.split(" ")[0]}</p>
        <h1 className="text-2xl font-bold mt-0.5 mb-6">Shipment Validation Dashboard</h1>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-4">
        <div className="lg:col-span-2 grid grid-cols-2 gap-4">
          {TILES.map((t, i) => (
            <motion.div
              key={t.key}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: i * 0.06 }}
              className="rounded-xl border bg-white p-5 flex flex-col justify-center"
              style={{ borderColor: "var(--color-line)" }}
            >
              <div className="mono text-3xl font-bold" style={{ color: t.color }}>
                {values[t.key]}
              </div>
              <div className="text-xs text-[var(--color-muted)] mt-1">{t.label}</div>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.24 }}
          className="rounded-xl border bg-white p-5" style={{ borderColor: "var(--color-line)" }}
        >
          <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
            Tatmeen reporting
          </h2>
          <DonutChart
            compact
            size={110}
            centerLabel="pharma scanned"
            data={[
              { label: "Reported", value: tatmeenCounts.green ?? 0, color: "var(--color-green)" },
              { label: "Pending", value: tatmeenCounts.yellow ?? 0, color: "var(--color-yellow)" },
              { label: "Not reported", value: tatmeenCounts.red ?? 0, color: "var(--color-red)" },
            ]}
          />
          {tatmeenTotal === 0 && (
            <p className="text-[11px] text-[var(--color-muted)] mt-3 text-center">
              Fills in once shipments are validated against Tatmeen.
            </p>
          )}
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.3 }}
          className="rounded-xl border bg-white p-5" style={{ borderColor: "var(--color-line)" }}
        >
          <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
            Item categories
          </h2>
          <DonutChart
            compact
            size={110}
            centerLabel="total items"
            data={[
              { label: "Pharma", value: categoryCounts.pharma ?? 0, color: "var(--color-accent)" },
              { label: "Non-pharma", value: categoryCounts.non_pharma ?? 0, color: "#5a827e" },
            ]}
          />
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.36 }}
        className="rounded-xl border bg-white p-5 mb-4" style={{ borderColor: "var(--color-line)" }}
      >
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Recent activity
          </h2>
          <Link to="/history" className="text-xs text-[var(--color-accent)] hover:underline">
            View all →
          </Link>
        </div>
        <div className="grid sm:grid-cols-2 gap-x-6">
          {(summary?.shipments ?? []).slice(0, 6).map((s) => (
            <Link
              key={s.invoice_number}
              to={`/validate/${s.invoice_number}`}
              className="flex items-center justify-between px-2 py-2 rounded-lg hover:bg-[var(--color-paper)] transition-colors"
            >
              <div>
                <span className="mono text-sm font-medium">{s.invoice_number}</span>
                {s.demo_flow && (
                  <span className="mono text-xs text-[var(--color-muted)] ml-2">Flow {s.demo_flow}</span>
                )}
                <span className="text-xs text-[var(--color-muted)] ml-2">
                  {s.scanned_count}/{s.item_count} scanned
                </span>
              </div>
              <StatusBadge status={s.overall_status} compact />
            </Link>
          ))}
          {summary && summary.shipments.length === 0 && (
            <p className="text-sm text-[var(--color-muted)] px-2 py-3">No shipments yet.</p>
          )}
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.42 }}
        className="rounded-xl p-5 text-white flex items-center justify-between gap-4 flex-wrap"
        style={{ background: "linear-gradient(135deg, #0b7285, #0d2523)" }}
      >
        <div>
          <div className="text-sm opacity-80 mb-0.5">Get started</div>
          <div className="text-base font-semibold leading-snug">Run a new invoice ↔ scan ↔ Tatmeen validation</div>
        </div>
        <Link
          to="/validate"
          className="inline-flex items-center justify-center rounded-lg bg-white/95 text-[#0a5e6d] text-sm font-semibold px-4 py-2.5 hover:bg-white transition-colors shrink-0"
        >
          Start New Validation →
        </Link>
      </motion.div>
    </div>
  );
}
