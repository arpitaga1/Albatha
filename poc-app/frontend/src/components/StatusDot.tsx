import { CheckCircle2, AlertTriangle, XCircle, Circle } from "lucide-react";
import type { RowStatus } from "../format";

const META: Record<RowStatus, { Icon: typeof CheckCircle2; color: string; label: string }> = {
  pending: { Icon: Circle, color: "var(--color-muted)", label: "Not scanned" },
  green: { Icon: CheckCircle2, color: "var(--color-green)", label: "Matched" },
  // Reuses the existing --color-yellow token, which is an amber/orange
  // tone in this app's palette already (used elsewhere for "Pending") -
  // no new color needed for the client's "orange" state.
  orange: { Icon: AlertTriangle, color: "var(--color-yellow)", label: "Attention" },
  red: { Icon: XCircle, color: "var(--color-red)", label: "Mismatch" },
};

/** Compact icon + label status indicator for a dense table row (up to ~150
 * rows) - deliberately smaller/plainer than StatusBadge's pill, which reads
 * fine at a handful of items but gets visually heavy repeated 150 times. */
export default function StatusDot({ status, label }: { status: RowStatus; label?: string }) {
  const m = META[status];
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold" style={{ color: m.color }} title={label ?? m.label}>
      <m.Icon size={14} strokeWidth={2.5} />
      {label ?? m.label}
    </span>
  );
}
