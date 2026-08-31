import { CheckCircle2, Clock, AlertTriangle, MinusCircle, Circle } from "lucide-react";
import type { Status } from "../types";

const STYLES: Record<Status, { bg: string; fg: string; ring: string; label: string; Icon: typeof CheckCircle2 }> = {
  green: { bg: "var(--color-green-tint)", fg: "var(--color-green)", ring: "#bfe0cd", label: "Validated", Icon: CheckCircle2 },
  yellow: { bg: "var(--color-yellow-tint)", fg: "var(--color-yellow)", ring: "#eecf9e", label: "Pending", Icon: Clock },
  red: { bg: "var(--color-red-tint)", fg: "var(--color-red)", ring: "#f0bcb7", label: "Manual Intervention", Icon: AlertTriangle },
  n_a: { bg: "#f1f3f2", fg: "var(--color-muted)", ring: "#dfe5e2", label: "N/A", Icon: MinusCircle },
  pending: { bg: "#f1f3f2", fg: "var(--color-muted)", ring: "#dfe5e2", label: "Not scanned", Icon: Circle },
};

export default function StatusBadge({ status, compact = false }: { status: Status; compact?: boolean }) {
  const s = STYLES[status] ?? STYLES.pending;
  const Icon = s.Icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold whitespace-nowrap border ${
        compact ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs"
      }`}
      style={{ background: s.bg, color: s.fg, borderColor: s.ring }}
      title={s.label}
    >
      <Icon size={compact ? 12 : 13} strokeWidth={2.5} />
      <span>{s.label}</span>
    </span>
  );
}
