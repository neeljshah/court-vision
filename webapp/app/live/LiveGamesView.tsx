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
import { cn } from "@/lib/utils";
import { useLiveData } from "@/lib/useLiveData";
import { LiveBadge } from "@/components/live/LiveBadge";
import {
  buildEntry, buildDoneEntryFromResult, partitionEntries,
  type LiveGameEntry,
} from "./liveSections";
import type { LiveState } from "./liveSections";

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

function LiveChip() {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-tier-a/40 bg-tier-a/20 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide text-tier-a"
      data-testid="live-chip"
      aria-label="live"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-tier-a animate-pulse" aria-hidden />
      LIVE
    </span>
  );
}

function gameStateLabel(liveState: LiveState | null): string {
  if (!liveState) return "";
  if (liveState.detail) return liveState.detail;
  if (liveState.status && liveState.status !== "live") return liveState.status;
  const parts: string[] = [];
  if (liveState.period != null) parts.push(`Q${liveState.period}`);
  if (liveState.clock) parts.push(liveState.clock);
  return parts.join(" ");
}

export function LiveGameRow({ entry }: { entry: LiveGameEntry }) {
  const isLive = entry.section === "LIVE";
  const isDone = entry.section === "DONE";
  const stateLabel = gameStateLabel(entry.liveState);
  const ls = entry.liveState;
  const fs = entry.finalScore;
  const mc = entry.modelCall;
  return (
    <li
      className={cn(
        "flex flex-col gap-1 rounded-lg border px-4 py-3 transition-colors",
        isLive ? "border-tier-a/30 bg-tier-a/5" : "border-slate-800 bg-bg-panel",
      )}
      data-testid="live-game-row"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-slate-100">
          {entry.away}<span className="mx-1.5 font-normal text-slate-500">@</span>{entry.home}
        </span>
        <span className="flex items-center gap-2">
          {isLive && <LiveChip />}
          {isDone && fs ? (
            <span className="font-mono text-xs font-semibold text-slate-300" data-testid="final-score">
              {entry.away} {fs.away_score} - {fs.home_score} {entry.home}
              <span className="ml-1.5 text-[10px] font-normal text-slate-500">{fs.label}</span>
            </span>
          ) : null}
          {!isLive && !isDone && entry.tipoff ? (
            <span className="font-mono text-[10px] text-slate-500">{entry.tipoff}</span>
          ) : null}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-[11px] text-slate-400">
          {entry.sport.toUpperCase()}<span className="mx-1.5 text-slate-700">&middot;</span>{entry.game_id}
        </span>
        {entry.homeWinProb != null ? (
          <span className="font-mono text-[11px] text-slate-300">
            {entry.home} win prob: {(entry.homeWinProb * 100).toFixed(1)}%
          </span>
        ) : null}
        {isDone && mc ? (
          <span
            className={cn(
              "font-mono text-[11px]",
              mc.correct === true
                ? "text-green-400"
                : mc.correct === false
                  ? "text-red-400"
                  : "text-slate-400",
            )}
            data-testid="model-call"
          >
            model: {mc.favoured} {mc.prob != null ? `(${(mc.prob * 100).toFixed(0)}%)` : ""}
            {mc.correct === true ? " -- correct" : mc.correct === false ? " -- wrong" : ""}
          </span>
        ) : null}
        {isLive && stateLabel ? <span className="font-mono text-[11px] text-slate-400">{stateLabel}</span> : null}
        {isLive && ls?.home_score != null && ls?.away_score != null ? (
          <span className="font-mono text-[11px] font-semibold text-slate-200">
            {ls.away_score} - {ls.home_score}
          </span>
        ) : null}
      </div>
    </li>
  );
}

function SectionPanel({ title, entries, accent }: {
  title: string; entries: LiveGameEntry[]; accent?: boolean;
}) {
  return (
    <section aria-label={`${title} games`} data-testid={`section-${title.toLowerCase()}`}>
      <h2 className={cn("mb-2 text-xs font-semibold uppercase tracking-widest", accent ? "text-tier-a" : "text-slate-400")}>
        {title}
      </h2>
      <ul className="flex flex-col gap-2">
        {entries.map((e) => <LiveGameRow key={`${e.sport}:${e.game_id}`} entry={e} />)}
      </ul>
    </section>
  );
}

function OffseasonState({ badge }: { badge: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-slate-800 bg-bg-panel px-8 py-14 text-center" data-testid="offseason-empty-state">
      <p className="text-sm font-medium text-slate-300" data-testid="offseason-message">
        No live games right now (offseason / none in progress)
      </p>
      <p className="text-[11px] text-slate-500">
        Auto-refresh is active -- this page will update when games are scheduled or start.
      </p>
      <div className="mt-1">{badge}</div>
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
    { intervalMs: POLL_MS, staleAfterSec: STALE_SEC },
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

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            Live Games
            <span className="ml-2 font-mono text-sm text-muted-foreground">
              live / pregame / done
            </span>
          </h1>
          <p className="mt-0.5 font-mono text-[11px] text-slate-500">
            probability only -- no $ -- calibration, not edge
          </p>
        </div>
        {badge}
      </div>

      {/* Skeleton shimmer only while first poll is pending (no data + no error yet). */}
      {isLoading && data === null && error === null ? (
        <div className="flex flex-col gap-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton-shimmer h-16 rounded-lg" />
          ))}
        </div>
      ) : !hasAny ? (
        <OffseasonState badge={badge} />
      ) : (
        <div className="flex flex-col gap-6">
          {live.length > 0 && <SectionPanel title="LIVE" entries={live} accent />}
          {pregame.length > 0 && <SectionPanel title="PREGAME" entries={pregame} />}
          {done.length > 0 && <SectionPanel title="DONE" entries={done} />}
        </div>
      )}
    </div>
  );
}
