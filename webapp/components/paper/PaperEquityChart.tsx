"use client";

// PaperEquityChart.tsx -- cumulative-units equity curve for the paper book.
//
// Recharts AreaChart of balance_units over points[] (the "how much I would have
// made" curve). Reuses the RecordsClvSeries chart approach (gradient area, hidden
// axes, zero/start reference line, honest empty state).
//
// HONESTY RAILS: UNITS only (no $); never fabricates a curve when points is
// null/empty; ASCII only.

import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { PnlSeriesPoint } from "@/lib/types";

// ---------------------------------------------------------------------------
// Formatters (exported -- shared with PaperEquityPanel).
// ---------------------------------------------------------------------------

export function fmtUnits(v: number): string {
  return v.toFixed(2);
}

export function fmtSignedUnits(v: number): string {
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}`;
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

interface ChartRow extends PnlSeriesPoint {
  index: number;
}

interface TooltipPayload {
  value?: number;
  payload?: ChartRow;
}

function EquityTooltip({
  active,
  payload,
  startUnits,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  startUnits: number | null;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const pt = payload[0]?.payload;
  if (!pt) return null;
  const net = startUnits != null ? pt.balance_units - startUnits : pt.cumulative_units;
  return (
    <div
      data-testid="paper-equity-tooltip"
      className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-[11px] font-mono text-slate-300"
    >
      <div className="mb-1 text-[10px] text-muted-foreground">{pt.day ?? pt.ts ?? "unknown"}</div>
      <div>
        balance:{" "}
        <span className="text-foreground">{fmtUnits(pt.balance_units)}u</span>
      </div>
      <div>
        net:{" "}
        <span className={net >= 0 ? "text-emerald-400" : "text-rose-400"}>
          {fmtSignedUnits(net)}u
        </span>
      </div>
      <div className="text-[9px] text-faint">
        {pt.n_bets} bets / {pt.n_win}W-{pt.n_loss}L
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyCurve({ honestNote }: { honestNote?: string }) {
  return (
    <div
      data-testid="paper-equity-empty"
      className="flex flex-col items-center justify-center gap-1 py-8 text-center"
    >
      <span className="font-mono text-[13px] font-semibold text-faint">
        no equity curve yet
      </span>
      <span className="font-mono text-[11px] text-faint max-w-sm">
        the curve appears once paper bets are placed and graded
      </span>
      {honestNote ? (
        <span className="font-mono text-[9px] text-faint mt-1 max-w-md">
          {honestNote.length > 100 ? honestNote.slice(0, 100) + "..." : honestNote}
        </span>
      ) : null}
      <span className="font-mono text-[9px] text-faint mt-1">
        UNITS only -- no dollars; no edge claimed
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PaperEquityChart -- main export.
// ---------------------------------------------------------------------------

export interface PaperEquityChartProps {
  points: PnlSeriesPoint[] | null;
  startUnits: number | null;
  honestNote?: string;
  loading?: boolean;
}

export function PaperEquityChart({
  points,
  startUnits,
  honestNote,
  loading,
}: PaperEquityChartProps) {
  const chartData = useMemo<ChartRow[]>(
    () => (points ?? []).map((pt, i) => ({ ...pt, index: i + 1 })),
    [points],
  );

  if (loading && (!points || points.length === 0)) {
    return (
      <div
        data-testid="paper-equity-loading"
        className="flex items-center justify-center py-8"
        aria-busy="true"
        aria-label="equity curve loading"
      >
        <div className="h-[140px] w-full animate-pulse rounded bg-slate-800/40" role="presentation" />
      </div>
    );
  }

  if (!points || points.length === 0) {
    return <EmptyCurve honestNote={honestNote} />;
  }

  const lastBalance = chartData[chartData.length - 1]?.balance_units ?? startUnits ?? 0;
  const up = startUnits == null ? true : lastBalance >= startUnits;
  const lineColor = up ? "#34d399" : "#f87171"; // emerald-400 / rose-400

  return (
    <div data-testid="paper-equity-chart" className="w-full">
      <div className="mb-1 flex items-center justify-between">
        <span className="font-mono text-[9px] uppercase tracking-widest text-faint">
          cumulative bankroll (units)
        </span>
        <span
          data-testid="paper-equity-last"
          className="font-mono text-[12px] font-semibold text-foreground"
        >
          {fmtUnits(lastBalance)}u
        </span>
      </div>
      <ResponsiveContainer width="100%" height={140}>
        <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="paperEquityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={lineColor} stopOpacity={0.2} />
              <stop offset="95%" stopColor={lineColor} stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <XAxis dataKey="index" hide />
          <YAxis hide domain={["auto", "auto"]} />
          {startUnits != null && (
            <ReferenceLine
              y={startUnits}
              stroke="#475569"
              strokeDasharray="3 3"
              strokeWidth={1}
            />
          )}
          <Tooltip content={<EquityTooltip startUnits={startUnits} />} />
          <Area
            type="monotone"
            dataKey="balance_units"
            stroke={lineColor}
            strokeWidth={1.5}
            fill="url(#paperEquityGrad)"
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      <div className="mt-1">
        <span className="font-mono text-[9px] text-faint">
          {points.length} points -- dashed line = starting bankroll. UNITS only; no $.
        </span>
      </div>
    </div>
  );
}
