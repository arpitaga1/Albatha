import { motion } from "framer-motion";

export interface DonutSegment {
  label: string;
  value: number;
  color: string;
}

/**
 * Animated multi-segment donut chart. Built on plain, manually-computed
 * stroke-dasharray/stroke-dashoffset math (not framer-motion's special
 * pathLength/pathOffset SVG values) after an earlier version using those
 * rendered wrong: every segment silently started from offset 0 regardless
 * of its real position, so segments overlapped instead of sitting side by
 * side, leaving part of the ring showing the bare background track. That
 * happened because pathOffset was only ever combined correctly with
 * pathLength when BOTH are simple, ordinary numbers this component owns
 * outright - here strokeDashoffset is a static, per-segment prop (no
 * special value system involved, so there's nothing for it to be silently
 * dropped from), and only strokeDasharray - a single well-documented
 * animatable two-token string - is what animates.
 */
export default function DonutChart({
  data, size = 160, thickness = 18, centerLabel, centerValue, compact = false,
}: {
  data: DonutSegment[];
  size?: number;
  thickness?: number;
  centerLabel?: string;
  centerValue?: number | string;
  // Stacks the ring above the legend instead of beside it - for a narrow
  // grid column where a side-by-side layout would feel cramped.
  compact?: boolean;
}) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  const r = 50 - thickness / 2;
  const circumference = 2 * Math.PI * r;
  let cumulative = 0;

  return (
    <div className={compact ? "flex flex-col items-center gap-4" : "flex items-center gap-5"}>
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg viewBox="0 0 100 100" width={size} height={size}>
          <circle cx={50} cy={50} r={r} fill="none" stroke="var(--color-line)" strokeWidth={thickness} />
          {total > 0 && data.map((d, i) => {
            if (d.value === 0) return null;
            const frac = d.value / total;
            const segLen = frac * circumference;
            // Negative offset shifts the dash pattern's start point forward
            // along the circle by this segment's cumulative share so far -
            // this is what actually positions each segment next to the
            // last, rather than every segment starting at the same point.
            const dashOffset = -cumulative * circumference;
            cumulative += frac;
            return (
              <motion.circle
                key={d.label}
                cx={50} cy={50} r={r} fill="none"
                stroke={d.color} strokeWidth={thickness} strokeLinecap="butt"
                transform="rotate(-90 50 50)"
                strokeDashoffset={dashOffset}
                initial={{ strokeDasharray: `0 ${circumference}` }}
                animate={{ strokeDasharray: `${segLen} ${circumference - segLen}` }}
                transition={{ duration: 0.7, delay: 0.15 + i * 0.12, ease: "easeOut" }}
              />
            );
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="mono text-2xl font-bold leading-none">{centerValue ?? total}</div>
          {centerLabel && <div className="text-[10px] text-[var(--color-muted)] mt-1 text-center max-w-[70px] leading-tight">{centerLabel}</div>}
        </div>
      </div>
      <div className={compact ? "w-full space-y-1.5" : "space-y-2"}>
        {data.map((d) => (
          <div key={d.label} className="flex items-center gap-2 text-sm">
            <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ background: d.color }} />
            <span className="text-[var(--color-muted)] text-xs">{d.label}</span>
            <span className="mono font-semibold ml-auto pl-2 text-xs">{d.value}</span>
            {total > 0 && (
              <span className="text-xs text-[var(--color-muted)] w-8 text-right">
                {Math.round((d.value / total) * 100)}%
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
