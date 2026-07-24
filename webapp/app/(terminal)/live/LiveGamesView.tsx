"use client";
// LiveGamesView.tsx -- /live polling body. Uses the canonical useLiveData hook
// (pause-on-hidden, last-good retention, ageSec ticking, isStale, clean abort).
// Three sections: LIVE / PREGAME / DONE. Honest offseason empty state with the
// refresh mechanism still visibly running (stale-never-green).
// HONESTY RAILS: probability / UNITS only -- NO $ anywhere.

import { useCallback } from "react";
import {
  api, isUnavailable, SPORTS,
  type PredictEnvelope, type PredictRecord,
  type BestBetsEnvelope, type GameEdge,
  type Results, type ResultRow,
} from "@/lib/api";
import type { Unavailable } from "@/lib/api";
import { useLiveData } from "@/lib/useLiveData";
import { LiveBadge } from "@/components/live/LiveBadge";
import { LiveGameRow } from "@/components/live/LiveGameRow";
import { Panel, PanelHead } from "@/components/ui/terminal";
import {
  buildEntry, buildDoneEntryFromResult, partitionEntries,
  type LiveGameEntry,
} from "./liveSections";

const POLL_MS = 20_000;
const STALE_SEC = 5 * 60;

// Fetch + merge predict + bestbets + results envelopes for all sports.
// Returns Unavailable sentinel when ALL sports fail (network-level error), so
// useLiveData can retain the last-good entries (stale, not cleared).
// Returns [] when sports respond but have no games (valid offseason state).
async function fetchLiveGames(
  signal: AbortSignal,
): Promise<LiveGameEntry[] | Unavailable> {
  type SportResult = { ok: true; entries: LiveGameEntry[] } | { ok: false };

  const sportResults = await Promise.allSettled(
    SPORTS.map(async (sport): Promise<SportResult> => {
      const [pred, bets, res] = await Promise.all([
        api.getPredict(sport, signal),
        api.bestbets(sport, signal),
        api.getResults(sport, undefined, signal),
      ]);
      // If predict is unavailable for this sport, this sport failed.
      if (isUnavailable(pred)) return { ok: false };
      const env = pred as PredictEnvelope;
      // Non-ok status (e.g. "offseason") is a valid empty response, not a failure.
      if (env.status !== "ok") {
        // Still surface completed results even when predict is offseason.
        const doneFromResults: LiveGameEntry[] = [];
        if (!isUnavailable(res)) {
          const rEnv = res as Results;
          for (const row of rEnv.results ?? []) {
            const e = buildDoneEntryFromResult(row, sport, null);
            if (e) doneFromResults.push(e);
          }
        }
        return { ok: true, entries: doneFromResults };
      }
      const preds: PredictRecord[] = env.predictions ?? [];
      // Build a map from game_id -> PredictRecord for model-call lookup on results.
      const predMap: Record<string, PredictRecord> = {};
      for (const p of preds) predMap[p.game_id] = p;
      // Build a map from game_id -> GameEdge (live state).
      const edgeMap: Record<string, GameEdge> = {};
      if (!isUnavailable(bets)) {
        const bEnv = bets as BestBetsEnvelope;
        for (const g of bEnv.games ?? []) {
          if (g.game_id) edgeMap[g.game_id] = g;
        }
      }
      // Build a results lookup from game_id -> ResultRow.
      const resultRowMap: Record<string, ResultRow> = {};
      if (!isUnavailable(res)) {
        const rEnv = res as Results;
        for (const row of rEnv.results ?? []) {
          if (row.game_id) resultRowMap[row.game_id] = row;
        }
      }
      // Merge predict+bestbets entries; upgrade to DONE when results says completed.
      // Keeps LIVE entries as-is (trust live state over results).
      const baseEntries = preds.map((rec) => {
        const entry = buildEntry(rec, edgeMap[rec.game_id] ?? null);
        if (entry.section === "LIVE") return entry;
        const rRow = resultRowMap[rec.game_id];
        if (!rRow || !rRow.completed) return entry;
        const enriched = buildDoneEntryFromResult(rRow, sport, rec);
        return enriched ? { ...enriched, liveState: entry.liveState } : entry;
      });
      // Surface completed games dropped by predict (suppressed/game_complete).
      const seenIds = new Set(baseEntries.map((e) => e.game_id));
      const doneFromResults: LiveGameEntry[] = [];
      for (const [gid, rRow] of Object.entries(resultRowMap)) {
        if (seenIds.has(gid)) continue;
        const e = buildDoneEntryFromResult(rRow, sport, predMap[gid]);
        if (e) doneFromResults.push(e);
      }
      return { ok: true, entries: [...baseEntries, ...doneFromResults] };
    }),
  );

  const settled = sportResults.map(
    (r) => (r.status === "fulfilled" ? r.value : { ok: false as const }),
  );
  const anyOk = settled.some((r) => r.ok);

  // All sports failed at the transport layer -> propagate Unavailable so
  // useLiveData retains the last-good entries instead of clearing to [].
  if (!anyOk) return { status: "unavailable", reason: "all sport endpoints unreachable" };

  return settled.flatMap((r) => (r.ok ? r.entries : []));
}

function SectionPanel({ title, entries, accent, asOf, stale }: {
  title: string; entries: LiveGameEntry[]; accent?: boolean;
  asOf: string; stale: boolean;
}) {
  return (
    <div data-testid={`section-${title.toLowerCase()}`} aria-label={`${title} games`}>
      <Panel>
        <PanelHead
          title={title}
          asOf={asOf}
          stale={stale}
          right={accent ? <span className="text-[10px] font-bold uppercase tracking-wider text-stale">in progress</span> : undefined}
        />
        <ul className="flex flex-col">
          {entries.map((e) => <LiveGameRow key={`${e.sport}:${e.game_id}`} entry={e} />)}
        </ul>
      </Panel>
    </div>
  );
}

function OffseasonState({ badge }: { badge: React.ReactNode }) {
  return (
    <div data-testid="offseason-empty-state">
      <Panel className="flex flex-col items-center gap-4 px-8 py-14 text-center">
        <p className="text-sm font-medium text-muted-foreground" data-testid="offseason-message">
          No live games right now (offseason / none in progress)
        </p>
        <p className="text-[11px] text-faint">
          Auto-refresh is active -- this page will update when games are scheduled or start.
        </p>
        <div className="mt-1">{badge}</div>
      </Panel>
    </div>
  );
}

export function LiveGamesView() {
  // useLiveData wraps fetchLiveGames: pause-on-hidden, last-good retention,
  // ageSec ticking, isStale, clean abort. No bespoke setInterval here.
  const liveDataFetcher = useCallback(
    (signal: AbortSignal) => fetchLiveGames(signal),
    [],
  );

  const { data, ageSec, isStale, error, isLoading } = useLiveData<LiveGameEntry[]>(
    liveDataFetcher,
    { intervalMs: POLL_MS, staleAfterSec: STALE_SEC, cacheKey: "live:games" },
  );

  const entries = data ?? [];
  const { live, pregame, done } = partitionEntries(entries);
  const hasAny = live.length + pregame.length + done.length > 0;

  // Shared LiveBadge driven by the canonical hook contract.
  const badge = (
    <LiveBadge
      ageSec={ageSec}
      isStale={isStale}
      error={error}
      isLoading={isLoading}
      data-testid="live-badge"
    />
  );

  // Real as-of stamp for section PanelHeads, derived from the last poll age.
  const sectionAsOf =
    ageSec != null ? new Date(Date.now() - ageSec * 1000).toLocaleTimeString() : "--:--:--";
  const sectionStale = isStale || Boolean(error);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground">
            Live Games
            <span className="ml-2 font-data text-sm text-muted-foreground">
              live / pregame / done
            </span>
          </h1>
          <p className="mt-0.5 font-data text-[11px] text-faint">
            probability only -- no $ -- calibration, not edge
          </p>
        </div>
        {badge}
      </div>

      {/* Skeleton shimmer only while first poll is pending (no data + no error yet). */}
      {isLoading && data === null && error === null ? (
        <div className="flex flex-col gap-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton-shimmer h-16" />
          ))}
        </div>
      ) : !hasAny ? (
        <OffseasonState badge={badge} />
      ) : (
        <div className="flex flex-col gap-6">
          {live.length > 0 && (
            <SectionPanel title="LIVE" entries={live} accent asOf={sectionAsOf} stale={sectionStale} />
          )}
          {pregame.length > 0 && (
            <SectionPanel title="PREGAME" entries={pregame} asOf={sectionAsOf} stale={sectionStale} />
          )}
          {done.length > 0 && (
            <SectionPanel title="DONE" entries={done} asOf={sectionAsOf} stale={sectionStale} />
          )}
        </div>
      )}
    </div>
  );
}
