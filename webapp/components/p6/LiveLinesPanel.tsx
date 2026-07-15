"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, isUnavailable, SPORTS, type BestBetsEnvelope, type GameEdge } from "@/lib/p5api";
import { Panel, Unavailable, Badge, ModeDot, timeAgoIso } from "./Primitives";
import { Num, Delta } from "@/components/ui/terminal";
import { useLiveData } from "@/lib/useLiveData";

// LiveLinesPanel -- captured odds/lines per game across all sports.
// Reads GET /api/v1/bestbets/{sport} for each sport, shows best_book (venue),
// line, odds, and freshness badge from generated_at. UNITS ONLY; no $ column.
// Auto-polls every 15s (useLiveData: pause-on-hidden, last-good retention,
// honest stale badge, never crashes on a failed poll).

// STALE_MS -- a feed older than this (by its OWN generated_at) reads stale->RED.
// live-lines.md section 5: strict 15-minute threshold; no amber middle state for age.
const STALE_MS = 15 * 60_000;

// freshnessStatus -- derive freshness SOLELY from the FEED's own data age
// (generated_at), NEVER from when the client last polled (loadedAt / fetch time).
// A dead/stale upstream whose generated_at is hours old must read 'stale' even if
// the browser just fetched it (stale-never-green rail). Missing/unparseable
// generated_at -> 'unknown' (also non-green), never 'fresh'.
export function freshnessStatus(
  generatedAt: string | null | undefined,
): "fresh" | "stale" | "unknown" {
  if (!generatedAt) return "unknown";
  const t = Date.parse(generatedAt);
  if (Number.isNaN(t)) return "unknown";
  const ageMs = Date.now() - t;
  return ageMs < STALE_MS ? "fresh" : "stale";
}

// FreshnessPill -- freshness chip for the live-lines board. STALE renders RED
// (stale-never-green rail), fresh renders green, unknown renders SLATE (missing
// provenance is a neutral missing-data state, not a failure -- never red on
// missing data, never green on stale). Age string is always derived from
// generated_at via timeAgoIso, never from browser fetch time.
export function FreshnessPill({
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

// LoadingShimmer -- pre-resolve aria-busy placeholder that matches the resolved
// odds table layout. Renders 3 skeleton rows (shimmer bars) so there is no
// jarring text flash while the per-sport fetch is in flight.
function LoadingShimmer() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="loading lines"
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

type Freshness = { generatedAt: string | null; stale: boolean };

// SportFeed -- per-sport block that owns its own useLiveData poller.
// Isolating per-sport polling means a single sport failure never kills the rest.
// onFreshness reports this sport's own generated_at + stale-ness up to the
// panel head so the top-level "as of" stamp reflects real feed data, never a
// fabricated timestamp.
function SportFeed({
  sport,
  onFreshness,
}: {
  sport: string;
  onFreshness: (sport: string, f: Freshness) => void;
}) {
  const fetcher = useCallback(
    (signal: AbortSignal) => api.bestbets(sport, signal),
    [sport],
  );

  const { data, isLoading, isStale, error } = useLiveData<BestBetsEnvelope>(
    fetcher,
    { intervalMs: 15_000, staleAfterSec: 30 },
  );

  const generatedAt = data?.generated_at ?? null;
  const bodyStale = isStale || freshnessStatus(generatedAt) === "stale";
  useEffect(() => {
    onFreshness(sport, { generatedAt, stale: bodyStale });
  }, [sport, generatedAt, bodyStale, onFreshness]);

  // Before first load: show neutral 'checking' shimmer (never red for loading).
  if (isLoading && !data) {
    return (
      <div>
        <div className="mb-2 flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-foreground">
            {sport}
          </span>
          <Badge tone="slate">checking</Badge>
        </div>
        <LoadingShimmer />
      </div>
    );
  }

  // The data freshness pill is derived from the FEED's own generated_at (honest);
  // isStale from useLiveData reflects poll-level staleness (last-good retention).
  const freshnessPillOverride =
    isStale && data != null ? (
      <Badge tone="amber">stale</Badge>
    ) : (
      <FreshnessPill generatedAt={data?.generated_at} />
    );

  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-foreground">
          {sport}
        </span>
        {freshnessPillOverride}
      </div>

      {error && !data ? (
        <Unavailable reason={error} />
      ) : !data ? (
        <LoadingShimmer />
      ) : !data.games || data.games.length === 0 ? (
        <p className="text-xs text-faint">
          {data.reason || "no games on slate"}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="microlabel py-1.5 px-3">Game</th>
                <th className="microlabel py-1.5 px-3">Market</th>
                <th className="microlabel py-1.5 px-3">Venue</th>
                <th className="microlabel py-1.5 px-3 text-right">Odds</th>
                <th className="microlabel py-1.5 px-3 text-right">Div</th>
                <th className="microlabel py-1.5 px-3 text-right">Tier</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.games.slice(0, 8).map((g) => (
                <GameRows key={g.game_id} game={g} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function LiveLinesPanel() {
  const [freshness, setFreshness] = useState<Record<string, Freshness>>({});
  const onFreshness = useCallback((sport: string, f: Freshness) => {
    setFreshness((prev) =>
      prev[sport]?.generatedAt === f.generatedAt && prev[sport]?.stale === f.stale
        ? prev
        : { ...prev, [sport]: f },
    );
  }, []);

  // Panel-level asOf: the freshest per-sport generated_at we have, formatted
  // HH:MM:SS. Panel-level stale: true if ANY sport's own feed is stale --
  // never silently green while one sport is dead.
  const { asOfStamp, anyStale } = useMemo(() => {
    const entries = Object.values(freshness);
    const stamps = entries
      .map((f) => f.generatedAt)
      .filter((d): d is string => Boolean(d))
      .sort();
    const newest = stamps.at(-1) ?? null;
    const t = newest ? Date.parse(newest) : NaN;
    return {
      asOfStamp: Number.isNaN(t) ? null : new Date(t).toLocaleTimeString("en-US", { hour12: false }),
      anyStale: entries.length > 0 && entries.some((f) => f.stale),
    };
  }, [freshness]);

  return (
    <Panel
      title="Live lines"
      asOf={asOfStamp}
      stale={anyStale}
      right={
        <span className="flex items-center gap-2">
          <ModeDot mode="poll" />
        </span>
      }
    >
      <div className="space-y-5">
        {SPORTS.map((sport) => (
          <SportFeed key={sport} sport={sport} onFreshness={onFreshness} />
        ))}
      </div>
      <p className="mt-3 text-[11px] text-faint">
        Lines captured from public keyless feeds. Venue = best book at capture
        time. Div = model prob minus devigged market prob (calibrated divergence,
        not an edge claim). Units only; no $ column.
      </p>
    </Panel>
  );
}

function GameRows({ game }: { game: GameEdge }) {
  const bets = game.best_bets || game.candidates || [];
  const label =
    game.home && game.away
      ? `${game.away} @ ${game.home}`
      : game.game_id;

  if (bets.length === 0) {
    return (
      <tr className="text-muted-foreground">
        <td className="py-1.5 font-mono text-[10px]">{label}</td>
        <td colSpan={5} className="py-1.5 text-[10px] text-faint">
          no candidates
        </td>
      </tr>
    );
  }

  return (
    <>
      {bets.slice(0, 3).map((b, i) => (
        <tr key={`${b.market_type}-${b.side}-${i}`} className="text-foreground hover:bg-surface-2">
          {i === 0 ? (
            <td
              className="py-1.5 px-3 font-mono text-[10px] text-faint"
              rowSpan={Math.min(bets.length, 3)}
            >
              {label}
            </td>
          ) : null}
          <td className="py-1.5 px-3">
            {b.market_type}{" "}
            <span className="text-muted-foreground">{b.side}</span>
            {b.line != null ? (
              <Num className="ml-1 text-faint">{b.line}</Num>
            ) : null}
          </td>
          <td className="py-1.5 px-3 font-mono text-[10px] text-faint">
            {b.best_book || "--"}
          </td>
          <td className="py-1.5 px-3 text-right">
            <Num>{b.best_odds != null ? b.best_odds.toFixed(2) : "--"}</Num>
          </td>
          <td className="py-1.5 px-3 text-right">
            {b.model_prob != null && b.market_prob != null ? (
              <Delta value={b.model_prob - b.market_prob} digits={3} />
            ) : (
              <Num className="text-faint">n/a</Num>
            )}
          </td>
          <td className="py-1.5 px-3 text-right">
            {b.tier ? (
              <Badge tone={tierTone(b.tier)}>{b.tier}</Badge>
            ) : (
              <span className="text-faint">--</span>
            )}
          </td>
        </tr>
      ))}
    </>
  );
}

function tierTone(tier: string): "gold" | "green" | "slate" {
  if (tier === "S") return "gold";
  if (tier === "A") return "green";
  return "slate";
}
