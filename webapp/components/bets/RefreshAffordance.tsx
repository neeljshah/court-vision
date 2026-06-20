"use client";
// RefreshAffordance.tsx -- Presentational refresh-status components extracted
// from BestBetsBoard.tsx to keep that file under the 300-LOC rail.
// Exports: AgeBadge, LivePulse, NextRefreshCountdown, RefreshAffordance.
//
// intervalMs is passed in by the parent (BestBetsBoard) so the countdown and
// copy always reflect the REAL poll cadence -- no duplicated constant here.

import { useState, useEffect } from "react";
import { Badge, timeAgoIso } from "@/components/p6/Primitives";
import { freshnessStatus } from "@/components/p6/LiveLinesPanel";
import { cn } from "@/lib/utils";

// AgeBadge -- data age from envelope.generated_at. NEVER green (stale-never-green).
// Amber when stale (>15m); slate otherwise. title exposes raw ISO asOf.
export function AgeBadge({ asOf }: { asOf: string | null }) {
  if (!asOf) return <Badge tone="slate"><span className="font-mono text-[10px]">data age: checking</span></Badge>;
  const stale = freshnessStatus(asOf) === "stale";
  const age = timeAgoIso(asOf);
  return (
    <span title={`data as-of: ${asOf}`} data-testid="age-badge">
      <Badge tone={stale ? "amber" : "slate"}>
        <span className="font-mono text-[10px]">{stale ? `data ${age} -- aging` : `data ${age}`}</span>
      </Badge>
    </span>
  );
}

// LivePulse -- pulsing dot + "updated Ns ago" from hook ageSec. Slate always.
export function LivePulse({ ageSec, isStale }: { ageSec: number | null; isStale: boolean }) {
  const label =
    ageSec === null ? "checking..."
    : ageSec < 60 ? `updated ${ageSec}s ago`
    : `updated ${Math.floor(ageSec / 60)}m ${String(ageSec % 60).padStart(2, "0")}s ago`;
  return (
    <span className="inline-flex items-center gap-1.5" data-testid="live-pulse">
      <span
        className={cn("inline-block h-1.5 w-1.5 rounded-full",
          isStale ? "bg-amber-500" : "bg-slate-500 animate-pulse")}
        aria-hidden="true"
      />
      <span className="font-mono text-[10px] text-slate-500">{label}</span>
    </span>
  );
}

// NextRefreshCountdown -- live countdown to next auto-refresh (ticks every 1s).
// intervalMs: the real poll interval from the parent board (no duplicated constant).
export function NextRefreshCountdown({
  loading,
  lastFetchedAt,
  intervalMs,
}: {
  loading: boolean;
  lastFetchedAt: number | null;
  intervalMs: number;
}) {
  const [secsLeft, setSecsLeft] = useState<number | null>(null);
  useEffect(() => {
    if (lastFetchedAt === null) { setSecsLeft(null); return; }
    const calc = () => Math.max(0, Math.round((intervalMs - (Date.now() - lastFetchedAt)) / 1000));
    setSecsLeft(calc());
    const id = window.setInterval(() => setSecsLeft(calc()), 1000);
    return () => window.clearInterval(id);
  }, [lastFetchedAt, intervalMs]);

  const intervalSec = Math.round(intervalMs / 1000);
  const intervalLabel = intervalSec >= 60
    ? `${Math.floor(intervalSec / 60)}m`
    : `~${intervalSec}s`;

  const text = loading ? "refreshing..."
    : secsLeft === null ? "auto-refresh scheduled"
    : secsLeft >= 60 ? `next refresh in ${Math.floor(secsLeft / 60)}m ${String(secsLeft % 60).padStart(2, "0")}s`
    : `next refresh in ${secsLeft}s`;

  return (
    <span
      className={cn("font-mono text-[10px]", loading ? "text-slate-400" : "text-slate-500")}
      data-testid="next-refresh-countdown"
      aria-live={loading ? "polite" : "off"}
      title={`auto-refreshes every ${intervalLabel}`}
    >
      {text}
    </span>
  );
}

// RefreshAffordance -- age badge + live pulse + countdown + manual refresh btn.
// intervalMs: passed from parent board; drives countdown + copy (no hardcoded constant).
export function RefreshAffordance({
  onRefresh,
  loading,
  lastFetchedAt,
  asOf,
  ageSec,
  isStale,
  intervalMs,
}: {
  onRefresh: () => void;
  loading: boolean;
  lastFetchedAt: number | null;
  asOf: string | null;
  ageSec: number | null;
  isStale: boolean;
  intervalMs: number;
}) {
  const intervalSec = Math.round(intervalMs / 1000);
  const intervalLabel = intervalSec >= 60
    ? `${Math.floor(intervalSec / 60)}m`
    : `~${intervalSec}s`;

  return (
    <div className="flex flex-wrap items-center gap-2.5" aria-label="refresh controls" data-testid="refresh-affordance">
      <AgeBadge asOf={asOf} />
      <LivePulse ageSec={ageSec} isStale={isStale} />
      <span className="font-mono text-[10px] text-slate-600" data-testid="auto-refresh-label">
        auto-refreshing every {intervalLabel}
      </span>
      <NextRefreshCountdown loading={loading} lastFetchedAt={lastFetchedAt} intervalMs={intervalMs} />
      <button type="button" aria-label="Refresh best bets now" disabled={loading} onClick={onRefresh}
        className={cn("inline-flex items-center gap-1 rounded border px-2 py-0.5",
          "font-mono text-[10px] uppercase tracking-wide transition-colors",
          "border-slate-700 bg-slate-900 text-slate-400",
          "hover:border-slate-500 hover:text-slate-200 focus-visible:outline-none",
          "focus-visible:ring-1 focus-visible:ring-slate-500 disabled:opacity-40")}>
        {loading ? "refreshing..." : "refresh now"}
      </button>
    </div>
  );
}
