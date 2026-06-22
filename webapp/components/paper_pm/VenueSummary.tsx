"use client";

// VenueSummary -- per-venue paper-trading summary tile grid.
// One tile per venue: trade count, open/settled, win/loss/push, total UNITS staked,
// mean model_prob, mean CLV (INSUFFICIENT_DATA honestly when no settled rows carry clv_pct).
// UNITS / probability only -- there is NO dollar column or $ symbol here.
// Pure presentational: receives rows prop; parent owns polling / data fetching.

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { fmtPct } from "@/lib/utils";
import { EMPTY_CELL } from "@/lib/tokens";
import { Badge } from "@/components/p6/Primitives";
import { aggregateByVenue } from "./venueAggregate";
import type { VenueStats } from "./venueAggregate";
import type { PaperTrailRow } from "@/lib/p5api";

// -- formatting helpers (units only, no $) --

function fmtProb(p: number | null): string {
  return p != null ? `${(p * 100).toFixed(1)}%` : EMPTY_CELL;
}

function fmtUnits(u: number | null): string {
  return u != null ? `${u.toFixed(2)}u` : EMPTY_CELL;
}

// CLV: null means INSUFFICIENT_DATA (zero settling rows with a real close).
// Never render 0 in place of null.
function fmtClv(clv: number | null): string {
  if (clv === null) return "INSUFFICIENT_DATA";
  return fmtPct(clv, true);
}

function clvTextClass(clv: number | null): string {
  if (clv === null) return "text-amber-600";
  if (clv > 0) return "text-success";
  if (clv < 0) return "text-danger";
  return "text-muted-foreground";
}

// -- sub-components --

type StatCellProps = { label: string; children: React.ReactNode };
function StatCell({ label, children }: StatCellProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[9px] font-mono uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <span className="font-mono text-[12px] text-slate-200">{children}</span>
    </div>
  );
}

type VenueTileProps = { stats: VenueStats };
function VenueTile({ stats }: VenueTileProps) {
  const {
    venue,
    total,
    open,
    settled,
    win,
    loss,
    push,
    stake_units_total,
    model_prob_mean,
    clv_mean,
    clv_sample_n,
  } = stats;

  return (
    <article
      aria-label={`Venue summary for ${venue}`}
      className={cn(
        "rounded-xl border border-slate-800 bg-bg-panel p-4",
        "flex flex-col gap-4",
      )}
      data-testid="venue-tile"
    >
      {/* Header */}
      <header className="flex items-center justify-between">
        <h3 className="font-mono text-[13px] font-semibold uppercase tracking-wide text-slate-200">
          {venue}
        </h3>
        <Badge tone="slate">{total} trade{total !== 1 ? "s" : ""}</Badge>
      </header>

      {/* Open / settled row */}
      <div className="flex gap-4">
        <StatCell label="Open">{open}</StatCell>
        <StatCell label="Settled">{settled}</StatCell>
      </div>

      {/* Win / loss / push */}
      <div className="flex gap-4">
        <StatCell label="Win">
          <span className={win > 0 ? "text-success" : "text-slate-400"}>
            {win}
          </span>
        </StatCell>
        <StatCell label="Loss">
          <span className={loss > 0 ? "text-danger" : "text-slate-400"}>
            {loss}
          </span>
        </StatCell>
        <StatCell label="Push">{push}</StatCell>
      </div>

      {/* Divider */}
      <div className="border-t border-slate-800/60" />

      {/* Metrics */}
      <div className="flex flex-wrap gap-4">
        <StatCell label="Staked (units, no $)">
          {fmtUnits(stake_units_total)}
        </StatCell>
        <StatCell label="Avg model prob">{fmtProb(model_prob_mean)}</StatCell>
        <StatCell label={`CLV (n=${clv_sample_n})`}>
          <span className={clvTextClass(clv_mean)}>{fmtClv(clv_mean)}</span>
        </StatCell>
      </div>

      {/* Honesty footnote when CLV is unavailable */}
      {clv_mean === null ? (
        <p className="text-[10px] leading-relaxed text-slate-600">
          CLV shown as INSUFFICIENT_DATA -- no settled trades with a captured
          closing line at this venue yet.
        </p>
      ) : null}
    </article>
  );
}

// -- main export --

type Props = {
  rows: PaperTrailRow[];
  loading?: boolean;
  error?: string | null;
};

export function VenueSummary({ rows, loading, error }: Props) {
  const venues = useMemo(() => aggregateByVenue(rows), [rows]);

  if (loading) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading venue summaries"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        {[1, 2].map((k) => (
          <div
            key={k}
            className="h-52 animate-pulse rounded-xl border border-slate-800 bg-bg-panel"
            data-testid="venue-skeleton"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div
        role="status"
        aria-label={`Venue summary unavailable: ${error}`}
        className="rounded-lg border border-amber-900/40 bg-amber-950/20 px-3 py-3 text-sm"
      >
        <span className="font-mono text-amber-400">unavailable</span>
        <span className="ml-2 text-xs text-slate-500">{error}</span>
      </div>
    );
  }

  if (venues.length === 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-bg-subtle/40 px-4 py-10 text-center text-sm text-slate-500">
        No venue data yet -- no paper trades in the trail.
      </div>
    );
  }

  return (
    <section aria-label="Per-venue paper trading summary">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {venues.map((stats) => (
          <VenueTile key={stats.venue} stats={stats} />
        ))}
      </div>
      <p className="mt-3 text-[11px] text-slate-600">
        One tile per venue the system executed on -- best available price per market.
        Paper mode -- stakes are units (no $). CLV (better-number-than-close) is
        the only honest calibration yardstick; shown as INSUFFICIENT_DATA when no
        settled closing line is captured. No edge is claimed.
      </p>
    </section>
  );
}
