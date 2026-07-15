"use client";

// EquitySparkline.tsx -- a compact inline SVG sparkline of the cumulative-units
// equity curve ("how much you WOULD have made" in UNITS) for the Home/today
// digest. Deliberately dependency-free (no recharts) so it stays tiny and renders
// inside a headline row. The full chart lives in PaperEquityChart.tsx.
//
// HONESTY RAILS: UNITS only (no $); never fabricates a curve when there are < 2
// points (shows an honest "no curve yet" note instead). ASCII only.

import { useMemo } from "react";

export interface EquitySparklineProps {
  // cumulative-units series (balance over time). null/short -> honest empty.
  values: number[] | null;
  // starting bankroll -> reference baseline + up/down color.
  startUnits?: number | null;
  width?: number;
  height?: number;
}

export function EquitySparkline({
  values,
  startUnits,
  width = 120,
  height = 34,
}: EquitySparklineProps) {
  const path = useMemo(() => {
    if (!values || values.length < 2) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const stepX = width / (values.length - 1);
    return values
      .map((v, i) => {
        const x = i * stepX;
        const y = height - ((v - min) / span) * height;
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [values, width, height]);

  if (!path || !values) {
    return (
      <span
        data-testid="today-sparkline-empty"
        className="font-data text-[10px] text-faint"
      >
        no equity curve yet -- units only, no $
      </span>
    );
  }

  const last = values[values.length - 1];
  const up = startUnits == null ? true : last >= startUnits;
  const color = up ? "hsl(var(--success))" : "hsl(var(--danger))";

  // Baseline y for the start-units reference line (only when in range).
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const baselineY =
    startUnits != null && startUnits >= min && startUnits <= max
      ? height - ((startUnits - min) / span) * height
      : null;

  return (
    <svg
      data-testid="today-sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="paper equity curve in units (compact)"
      className="overflow-visible"
    >
      {baselineY != null && (
        <line
          x1={0}
          y1={baselineY}
          x2={width}
          y2={baselineY}
          stroke="hsl(var(--border))"
          strokeWidth={1}
          strokeDasharray="2 2"
        />
      )}
      <path d={path} fill="none" stroke={color} strokeWidth={2} />
    </svg>
  );
}
