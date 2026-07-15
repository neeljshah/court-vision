"use client";

// RecordsClvSeries.tsx -- W1-records-clv-analytics: CLV-over-time sparkline.
//
// Reads /api/paper/clv/series (ClvSeries shape). Renders:
//   - Honest empty state when count=0 (offseason, no closes graded yet).
//   - A Recharts line sparkline of cumulative_mean_clv_pct when series>=1.
//   - Each point labeled with its matchup + beat_close indicator.
//
// Honesty rails:
//   - count=0 -> NEVER fabricates a curve; shows exact honest_note from API.
//   - No $ token anywhere. CLV = probability-space only.
//   - Proxy points labeled (clv_is_proxy=true).
//   - ASCII only. Under 300 LOC.

import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { ClvSeries, ClvSeriesPoint } from "@/lib/types";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";

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
      className="border border-border bg-card px-3 py-2 text-[11px] font-data text-foreground"
    >
      <div className="text-faint text-[10px] mb-1">{pt.matchup ?? "unknown"}</div>
      <div>cum. CLV: <span className={pct >= 0 ? "text-up" : "text-down"}>{sign}{(pct * 100).toFixed(2)}%</span></div>
      <div>this bet: <span className={pt.beat_close ? "text-up" : "text-faint"}>{beatLabel}{pt.clv_is_proxy ? " (proxy)" : ""}</span></div>
      {pt.sport && <div className="text-faint text-[9px] mt-0.5">{pt.sport}</div>}
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
      <span className="font-data text-[13px] font-semibold text-faint">
        INSUFFICIENT_DATA
      </span>
      <span className="font-data text-[11px] text-faint max-w-sm">
        no closes graded yet -- offseason, no liquid in-play prices
      </span>
      {nNoClose != null && nNoClose > 0 && (
        <span className="font-data text-[9px] text-faint mt-1">
          {nNoClose} bets logged, awaiting closing prices
        </span>
      )}
      <span className="font-data text-[9px] text-faint mt-1">
        {reason.length > 80 ? reason.slice(0, 80) + "..." : reason}
      </span>
      <span className="font-data text-[9px] text-faint">
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
      <div className="h-[100px] w-full animate-pulse bg-surface-2" role="presentation" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sparkline chart
// ---------------------------------------------------------------------------

function EndpointDot(lastIndex: number) {
  return function Dot(props: { cx?: number; cy?: number; index?: number }) {
    const { cx, cy, index } = props;
    if (cx == null || cy == null || index !== lastIndex) return <g />;
    return <circle cx={cx} cy={cy} r={3.5} fill="hsl(var(--s-model))" stroke="none" />;
  };
}

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

  return (
    <div data-testid="clv-series-chart" className="w-full">
      <div className="mb-1 flex items-center justify-between">
        <span className="microlabel">
          cumulative mean CLV (%)
        </span>
        <span
          data-testid="clv-series-last-val"
          className={`text-[12px] font-semibold ${lastVal >= 0 ? "text-up" : "text-down"}`}
        >
          <Num>{lastVal >= 0 ? "+" : ""}{lastVal.toFixed(2)}%</Num>
        </span>
      </div>
      <ResponsiveContainer width="100%" height={100}>
        <LineChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <XAxis dataKey="index" hide />
          <YAxis hide domain={["auto", "auto"]} />
          <ReferenceLine y={0} stroke="hsl(var(--border))" strokeDasharray="3 3" strokeWidth={1} />
          <Tooltip content={<SeriesChartTooltip />} />
          <Line
            type="monotone"
            dataKey="cumPct"
            stroke="hsl(var(--s-model))"
            strokeWidth={2}
            dot={EndpointDot(chartData.length - 1)}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-1 flex items-center gap-2">
        <span className="font-data text-[9px] text-faint">
          {series.length} graded bets -- CLV = beat-the-close; calibration only -- not a market edge
        </span>
        {series.some((p) => p.clv_is_proxy) && (
          <span className="font-data text-[9px] text-stale">(some proxy closes)</span>
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
  /** Fetch time for the CLV series feed (no upstream timestamp on this shape). */
  asOf?:     string | null;
}

export function RecordsClvSeries({
  clvSeries,
  loading = false,
  nNoClose,
  asOf = null,
}: RecordsClvSeriesProps) {
  if (loading && clvSeries === null) {
    return (
      <div data-testid="records-clv-series" role="region" aria-label="CLV series sparkline">
        <Panel>
          <PanelHead title="CLV Over Time" asOf={asOf} />
          <div className="px-4 py-3">
            <LoadingSkeleton />
          </div>
        </Panel>
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
    <div data-testid="records-clv-series" role="region" aria-label="CLV series sparkline">
      <Panel>
        <PanelHead title="CLV Over Time" asOf={asOf} />
        <div className="px-4 py-3">
          {hasData ? (
            <SparklineChart series={series!} />
          ) : (
            <HonestEmpty honestNote={honestNote} nNoClose={nNoClose} />
          )}
        </div>
      </Panel>
    </div>
  );
}
