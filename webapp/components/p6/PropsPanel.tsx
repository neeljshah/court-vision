"use client";

import { useCallback, useMemo } from "react";
import { api, type PropsBoard, type PlayerPropRow } from "@/lib/p5api";
import { Panel, Unavailable, Badge, ModeDot, timeAgoIso } from "./Primitives";
import { useLiveData } from "@/lib/useLiveData";
import { fmtPct } from "@/lib/utils";

// PropsPanel -- calibrated player-prop predictions per sport.
// Reads GET /api/predict/props/{sport} for each sport, shows player/stat/line/
// book/P(over)/tier. Mirrors LiveLinesPanel's pattern: per-sport SportFeed
// isolation, useLiveData polling (pause-on-hidden, stale-never-green, last-good
// retention), a loading shimmer, and an honest empty state.
//
// Scoped to sports with a REAL live bridge behind /api/predict/props/{sport}:
// mlb + soccer_intl only. NBA/soccer/tennis do not have real prop data behind
// this bridge yet -- do not claim otherwise by including them here.
const PROP_SPORTS = ["mlb", "soccer_intl"] as const;

// Rows come back capped at ~1600-1700+ for MLB / ~500 for soccer_intl -- never
// render the full corpus unpaginated. Take the top N by |p_over - 0.5|
// divergence (most decisive calibrated views), note the true total separately.
const MAX_ROWS = 12;

// STALE_MS mirrors LiveLinesPanel's strict 15-minute threshold; freshness is
// derived from the feed's OWN generated_at, never from browser fetch time.
const STALE_MS = 15 * 60_000;

function freshnessStatus(
  generatedAt: string | null | undefined,
): "fresh" | "stale" | "unknown" {
  if (!generatedAt) return "unknown";
  const t = Date.parse(generatedAt);
  if (Number.isNaN(t)) return "unknown";
  const ageMs = Date.now() - t;
  return ageMs < STALE_MS ? "fresh" : "stale";
}

function FreshnessPill({
  generatedAt,
}: {
  generatedAt: string | null | undefined;
}) {
  const status = freshnessStatus(generatedAt);
  if (status === "fresh") {
    return <Badge tone="green">{`fresh ${timeAgoIso(generatedAt as string)}`}</Badge>;
  }
  if (status === "stale") {
    return <Badge tone="red">{`STALE ${timeAgoIso(generatedAt as string)}`}</Badge>;
  }
  return <Badge tone="slate">no feed timestamp</Badge>;
}

// LoadingShimmer -- pre-resolve aria-busy placeholder matching the resolved
// props table layout. No jarring text flash while the per-sport fetch is in flight.
function LoadingShimmer() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="loading props"
      className="space-y-1.5"
    >
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex gap-2 py-1">
          <div className="h-3 w-28 animate-pulse rounded bg-slate-800/70" />
          <div className="h-3 w-16 animate-pulse rounded bg-slate-800/50" />
          <div className="ml-auto h-3 w-10 animate-pulse rounded bg-slate-800/50" />
        </div>
      ))}
    </div>
  );
}

// isBodyUnavailable -- the real endpoint returns HTTP 200 with a body-level
// status of "UNAVAILABLE"/"unavailable" (offseason / genuine miss), not the
// transport-level Unavailable sentinel. Check both.
function isBodyUnavailable(d: PropsBoard): boolean {
  return d.status?.toUpperCase() === "UNAVAILABLE";
}

// topByDivergence -- sort by biggest |p_over - 0.5| divergence (most decisive
// calibrated views first) and cap at MAX_ROWS. Rows with a null p_over sort last.
function topByDivergence(rows: PlayerPropRow[]): PlayerPropRow[] {
  return [...rows]
    .sort((a, b) => {
      const da = a.p_over == null ? -1 : Math.abs(a.p_over - 0.5);
      const db = b.p_over == null ? -1 : Math.abs(b.p_over - 0.5);
      return db - da;
    })
    .slice(0, MAX_ROWS);
}

// SportFeed -- per-sport block that owns its own useLiveData poller. Isolating
// per-sport polling means one sport's failure never kills the other.
function SportFeed({ sport }: { sport: string }) {
  const fetcher = useCallback(
    (signal: AbortSignal) => api.propsBoard(sport, undefined, signal),
    [sport],
  );

  const { data, isLoading, isStale, error } = useLiveData<PropsBoard>(fetcher, {
    intervalMs: 30_000,
    staleAfterSec: 60,
  });

  const topRows = useMemo(
    () => (data?.rows?.length ? topByDivergence(data.rows) : []),
    [data],
  );

  if (isLoading && !data) {
    return (
      <div>
        <div className="mb-2 flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-300">
            {sport}
          </span>
          <Badge tone="slate">checking</Badge>
        </div>
        <LoadingShimmer />
      </div>
    );
  }

  const freshnessPillOverride =
    isStale && data != null ? (
      <Badge tone="amber">stale</Badge>
    ) : (
      <FreshnessPill generatedAt={data?.generated_at} />
    );

  const bodyUnavailable = data ? isBodyUnavailable(data) : false;

  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-300">
          {sport}
        </span>
        {freshnessPillOverride}
        {data && !bodyUnavailable ? (
          <span className="ml-auto font-mono text-[10px] text-slate-600">
            showing {topRows.length} of {data.count}
          </span>
        ) : null}
      </div>

      {error && !data ? (
        <Unavailable reason={error} />
      ) : !data ? (
        <LoadingShimmer />
      ) : bodyUnavailable || !data.rows || data.rows.length === 0 ? (
        <p className="text-xs text-slate-600">
          {data.reason || data.honest_note || "no props on slate"}
        </p>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wide text-slate-500">
              <th className="pb-1.5 font-medium">Player</th>
              <th className="pb-1.5 font-medium">Stat</th>
              <th className="pb-1.5 font-medium text-right">Line</th>
              <th className="pb-1.5 font-medium">Book</th>
              <th className="pb-1.5 font-medium text-right">P(over)</th>
              <th className="pb-1.5 font-medium text-right">Tier</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {topRows.map((r, i) => (
              <PropRowView key={`${r.player}-${r.stat}-${r.book}-${i}`} row={r} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function PropRowView({ row }: { row: PlayerPropRow }) {
  return (
    <tr className="text-slate-300">
      <td className="py-1.5">
        <div className="text-slate-200">{row.player}</div>
        {row.match ? (
          <div className="font-mono text-[10px] text-slate-600">{row.match}</div>
        ) : null}
      </td>
      <td className="py-1.5 text-slate-400">{row.stat}</td>
      <td className="py-1.5 text-right font-mono tabular-nums">
        {row.line != null ? row.line : "--"}
      </td>
      <td className="py-1.5 font-mono text-[10px] text-slate-400">
        {row.book || "--"}
      </td>
      <td className="py-1.5 text-right font-mono tabular-nums">
        {row.p_over != null ? fmtPct(row.p_over, false) : "n/a"}
      </td>
      <td className="py-1.5 text-right">
        {row.tier ? (
          <Badge tone={tierTone(row.tier)}>{row.tier}</Badge>
        ) : (
          <span className="text-slate-600">--</span>
        )}
      </td>
    </tr>
  );
}

function tierTone(tier: string): "gold" | "green" | "slate" {
  if (tier === "S") return "gold";
  if (tier === "A") return "green";
  return "slate";
}

export function PropsPanel() {
  return (
    <Panel
      title="Player props"
      right={
        <span className="flex items-center gap-2">
          <ModeDot mode="poll" />
        </span>
      }
    >
      <div className="space-y-5">
        {PROP_SPORTS.map((sport) => (
          <SportFeed key={sport} sport={sport} />
        ))}
      </div>
      <p className="mt-3 text-[11px] text-slate-600">
        Calibrated P(over) from each sport&apos;s Poisson/NegBin prop model,
        priced against real scraped sportsbook/DFS lines (DraftKings/Underdog/
        PrizePicks/FanDuel). Probabilities only -- no $ edge is claimed. Rows are
        capped and ranked by largest divergence from a coinflip; see the count
        badge for the full slate size. clv_is_proxy: no true prop closing-line
        capture yet for these sports.
      </p>
    </Panel>
  );
}
