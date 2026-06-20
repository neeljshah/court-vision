"use client";

// RecordsClvSeries.tsx -- W1-records-clv-analytics: CLV-over-time sparkline.
//
// Reads /api/paper/clv/series (ClvSeries shape). Renders:
//   - Honest empty state when count=0 (offseason, no closes graded yet).
//   - A Recharts AreaChart sparkline of cumulative_mean_clv_pct when series>=1.
//   - Each point labeled with its matchup + beat_close indicator.
//
// Honesty rails:
//   - count=0 -> NEVER fabricates a curve; shows exact honest_note from API.
//   - No $ token anywhere. CLV = probability-space only.
//   - Proxy points labeled (clv_is_proxy=true).
//   - ASCII only. Under 300 LOC.

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
import type { ClvSeries, ClvSeriesPoint } from "@/lib/types";

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

interface TooltipPayload {
  value?: number;
  payload?: ClvSeriesPoint;
}

function SeriesChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
}) {
  if (!active || !payload || payload.length === 0) return null;
  const pt = payload[0]?.payload;
  if (!pt) return null;
  const pct = pt.cumulative_mean_clv_pct;
  const sign = pct >= 0 ? "+" : "";
  const beatLabel = pt.beat_close === true ? "beat" : pt.beat_close === false ? "missed" : "n/a";
  return (
    <div
      data-testid="clv-series-tooltip"
      className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-[11px] font-mono text-slate-300"
    >
      <div className="text-slate-400 text-[10px] mb-1">{pt.matchup ?? "unknown"}</div>
      <div>cum. CLV: <span className={pct >= 0 ? "text-emerald-400" : "text-rose-400"}>{sign}{(pct * 100).toFixed(2)}%</span></div>
      <div>this bet: <span className={pt.beat_close ? "text-emerald-400" : "text-slate-400"}>{beatLabel}{pt.clv_is_proxy ? " (proxy)" : ""}</span></div>
      {pt.sport && <div className="text-slate-600 text-[9px] mt-0.5">{pt.sport}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty / offseason state
// ---------------------------------------------------------------------------

function HonestEmpty({ honestNote, nNoClose }: { honestNote?: string; nNoClose?: number }) {
  const reason = honestNote
    ? honestNote
    : "no closes graded yet -- offseason, no liquid in-play prices";
  return (
    <div
      data-testid="clv-series-empty"
      className="flex flex-col items-center justify-center gap-1 py-8 text-center"
    >
      <span className="font-mono text-[13px] font-semibold text-slate-600">
        INSUFFICIENT_DATA
      </span>
      <span className="font-mono text-[11px] text-slate-700 max-w-sm">
        no closes graded yet -- offseason, no liquid in-play prices
      </span>
      {nNoClose != null && nNoClose > 0 && (
        <span className="font-mono text-[9px] text-slate-800 mt-1">
          {nNoClose} bets logged, awaiting closing prices
        </span>
      )}
      <span className="font-mono text-[9px] text-slate-800 mt-1">
        {reason.length > 80 ? reason.slice(0, 80) + "..." : reason}
      </span>
      <span className="font-mono text-[9px] text-slate-800">
        CLV = beat-the-close; calibration only -- not a market edge
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function LoadingSkeleton() {
  return (
    <div
      data-testid="clv-series-loading"
      className="flex items-center justify-center py-8"
      aria-busy="true"
      aria-label="CLV series loading"
    >
      <div className="h-[100px] w-full animate-pulse rounded bg-slate-800/40" role="presentation" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sparkline chart
// ---------------------------------------------------------------------------

function SparklineChart({ series }: { series: ClvSeriesPoint[] }) {
  const chartData = useMemo(
    () =>
      series.map((pt, i) => ({
        ...pt,
        index: i + 1,
        // cumulative_mean_clv_pct is already a fraction; display as percent
        cumPct: pt.cumulative_mean_clv_pct * 100,
        label: pt.matchup ? pt.matchup.slice(0, 12) : `#${i + 1}`,
      })),
    [series],
  );

  const lastVal = chartData[chartData.length - 1]?.cumPct ?? 0;
  const lineColor = lastVal >= 0 ? "#34d399" : "#f87171"; // emerald-400 / rose-400

  return (
    <div data-testid="clv-series-chart" className="w-full">
      <div className="mb-1 flex items-center justify-between">
        <span className="font-mono text-[9px] uppercase tracking-widest text-slate-600">
          cumulative mean CLV (%)
        </span>
        <span
          data-testid="clv-series-last-val"
          className={`font-mono text-[12px] font-semibold ${lastVal >= 0 ? "text-emerald-400" : "text-rose-400"}`}
        >
          {lastVal >= 0 ? "+" : ""}{lastVal.toFixed(2)}%
        </span>
      </div>
      <ResponsiveContainer width="100%" height={100}>
        <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="clvGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={lineColor} stopOpacity={0.2} />
              <stop offset="95%" stopColor={lineColor} stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <XAxis dataKey="index" hide />
          <YAxis hide domain={["auto", "auto"]} />
          <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" strokeWidth={1} />
          <Tooltip content={<SeriesChartTooltip />} />
          <Area
            type="monotone"
            dataKey="cumPct"
            stroke={lineColor}
            strokeWidth={1.5}
            fill="url(#clvGrad)"
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      <div className="mt-1 flex items-center gap-2">
        <span className="font-mono text-[9px] text-slate-700">
          {series.length} graded bets -- CLV = beat-the-close; calibration only -- not a market edge
        </span>
        {series.some((p) => p.clv_is_proxy) && (
          <span className="font-mono text-[9px] text-amber-700">(some proxy closes)</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RecordsClvSeries -- main export
// ---------------------------------------------------------------------------

export interface RecordsClvSeriesProps {
  /** Already-fetched CLV series data (or null while loading). */
  clvSeries: ClvSeries | { status: "unavailable"; reason?: string } | null;
  loading?:  boolean;
  /** Optionally pass nNoClose from /api/paper/clv for the honest empty note. */
  nNoClose?: number;
}

export function RecordsClvSeries({
  clvSeries,
  loading = false,
  nNoClose,
}: RecordsClvSeriesProps) {
  if (loading && clvSeries === null) {
    return (
      <div
        data-testid="records-clv-series"
        role="region"
        aria-label="CLV series sparkline"
        className="rounded border border-slate-800 bg-slate-900/30 px-4 py-3"
      >
        <LoadingSkeleton />
      </div>
    );
  }

  const isUnavailable =
    clvSeries === null ||
    (clvSeries as { status?: string }).status === "unavailable";

  const series = isUnavailable
    ? null
    : (clvSeries as ClvSeries).series ?? [];

  const honestNote = isUnavailable
    ? undefined
    : (clvSeries as ClvSeries).honest_note;

  const hasData = !isUnavailable && Array.isArray(series) && series.length > 0;

  return (
    <div
      data-testid="records-clv-series"
      role="region"
      aria-label="CLV series sparkline"
      className="rounded border border-slate-800 bg-slate-900/30 px-4 py-3"
    >
      <div className="mb-2">
        <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
          CLV over time
        </span>
      </div>

      {hasData ? (
        <SparklineChart series={series!} />
      ) : (
        <HonestEmpty honestNote={honestNote} nNoClose={nNoClose} />
      )}
    </div>
  );
}
