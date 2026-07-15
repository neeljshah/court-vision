"use client";

// CardDetailView.tsx -- full click-through card detail for /bets/[sport]/[gameId].
// Panels: DistributionPanel, BookMatrixTable, ExecutionTrail, RationalePanel,
// LiveBoxPanel, SettleGradePanel. All degrade to honest unavailable states.
// HONESTY RAILS: UNITS / probability only. No $ anywhere. CLV = beat-the-close.
// Live polling via useLiveData (pause-on-hidden, last-good, stale badge).
// No bespoke setInterval.

import { useCallback } from "react";
import Link from "next/link";
import {
  api,
  isUnavailable,
  streamUrl,
  type Report,
  type GameEdge,
  type Results,
} from "@/lib/api";
import { apiExt, isExtUnavailable } from "@/lib/p5api_ext";
import type {
  LinesMatrix,
  PropsBoardEnvelope,
  InGameFull,
} from "@/lib/p5api_ext";
import type { ResultRow } from "@/lib/types";
import { useStream } from "@/lib/useStream";
import { useLiveData } from "@/lib/useLiveData";
import { ModeDot } from "@/components/p6/Primitives";
import { Degraded, Unavailable } from "@/components/honest/HonestState";
import { DistributionPanel } from "./DistributionPanel";
import { BookMatrixTable } from "./BookMatrixTable";
import { RationalePanel } from "./RationalePanel";
import { LiveBoxPanel } from "./LiveBoxPanel";
import { SettleGradePanel } from "./SettleGradePanel";
import { PlacedBetsForGamePanel } from "./PlacedBetsForGamePanel";
import { ExecutionTrail } from "@/components/execution/ExecutionTrail";
import { linesMatrixToExecutionTrail } from "./executionTrailAdapter";

// Derive a human-readable matchup label.
function matchupLabel(
  edge: GameEdge | null,
  report: Report | null,
): string {
  const g = edge ?? null;
  if (g?.home && g?.away) return `${g.away} @ ${g.home}`;
  const pg = report?.pregame;
  if (pg?.home && pg?.away) return `${pg.away} @ ${pg.home}`;
  return "";
}

// Sport label for display.
function sportLabel(sport: string): string {
  if (sport === "soccer_intl") return "SOCCER (INTL)";
  return sport.toUpperCase();
}

/**
 * Derives the authoritative sport to display.
 *
 * Priority:
 *   1. If the API-returned report has a `sport` field that is non-empty and
 *      DISAGREES with the URL slug, the API wins (return report.sport).
 *   2. If the API sport matches the URL slug, or the report is null / has no
 *      sport field, trust the URL slug (return urlSport).
 *
 * Returns:
 *   { resolved, mismatch }
 *   resolved  -- the sport string to use for display
 *   mismatch  -- true only when API sport is known AND differs from the URL slug
 */
function resolveSport(
  urlSport: string,
  report: Report | null,
): { resolved: string; mismatch: boolean } {
  const apiSport =
    report && typeof (report as Report).sport === "string" && (report as Report).sport
      ? (report as Report).sport
      : null;
  if (apiSport && apiSport !== urlSport) {
    return { resolved: apiSport, mismatch: true };
  }
  return { resolved: urlSport, mismatch: false };
}

// Formats age in seconds as a short human-readable string for the last-updated badge.
function fmtAge(ageSec: number | null): string {
  if (ageSec === null) return "checking";
  if (ageSec < 60) return `${ageSec}s ago`;
  return `${Math.round(ageSec / 60)}m ago`;
}

// Formats a fetch/feed timestamp (ms epoch) as HH:MM:SS for PanelHead as-of stamps.
function fmtClock(ms: number | null): string | null {
  if (ms == null) return null;
  return new Date(ms).toLocaleTimeString("en-US", { hour12: false });
}

export interface CardDetailViewProps {
  sport: string;
  gameId: string;
}

/** Full card detail view -- distribution, book matrix, rationale, live box, grade. */
export function CardDetailView({ sport, gameId }: CardDetailViewProps) {
  // Report: streaming via SSE / poll fallback (same pattern as GameView).
  const { data: report, mode, updatedAt: reportUpdatedAt } = useStream<Report>({
    sseUrl: streamUrl(sport, gameId),
    pollFn: async (s) => (await api.report(sport, gameId, s)) as Report,
    pollMs: 6000,
  });

  // Edge / best-bets -- polled via useLiveData (pause-on-hidden, last-good, stale).
  const edgeFetcher = useCallback(
    (s: AbortSignal) => api.bestbetsGame(sport, gameId, s) as Promise<GameEdge>,
    [sport, gameId],
  );
  const {
    data: edge,
    ageSec: edgeAge,
    isStale: edgeStale,
    error: edgeError,
    lastUpdatedAt: edgeUpdatedAt,
  } = useLiveData<GameEdge>(edgeFetcher, {
    intervalMs: 8000,
    staleAfterSec: 30,
  });

  // W4 in-game full -- polled via useLiveData.
  const ingameFetcher = useCallback(
    (s: AbortSignal) => apiExt.getInGameFull(sport, gameId, s) as Promise<InGameFull>,
    [sport, gameId],
  );
  const {
    data: ingame,
    ageSec: ingameAge,
    isStale: ingameStale,
  } = useLiveData<InGameFull>(ingameFetcher, {
    intervalMs: 10000,
    staleAfterSec: 45,
  });

  // W1 lines matrix -- one-shot (low-cadence; no real-time refresh needed).
  const linesFetcher = useCallback(
    (s: AbortSignal) => apiExt.getLinesMatrix(sport, gameId, s) as Promise<LinesMatrix>,
    [sport, gameId],
  );
  const {
    data: linesMatrix,
    lastUpdatedAt: linesUpdatedAt,
    isStale: linesStale,
  } = useLiveData<LinesMatrix>(linesFetcher, {
    intervalMs: 60000,
    staleAfterSec: 300,
  });

  // W2 props board -- one-shot.
  const propsFetcher = useCallback(
    (s: AbortSignal) =>
      apiExt.getPropsBoard(sport, gameId, s) as Promise<PropsBoardEnvelope>,
    [sport, gameId],
  );
  const { data: propsData } = useLiveData<PropsBoardEnvelope>(propsFetcher, {
    intervalMs: 60000,
    staleAfterSec: 300,
  });

  // Results for settle/grade -- one-shot.
  const resultsFetcher = useCallback(
    async (s: AbortSignal) => {
      const d = await api.getResults(sport, gameId, s);
      if (isUnavailable(d)) return { status: "unavailable" as const };
      const row = (d as Results).results?.find((r) => r.game_id === gameId) ?? null;
      // Wrap as an object so useLiveData can distinguish null-row from unavailable.
      return { row } as unknown as ResultRow;
    },
    [sport, gameId],
  );
  const {
    data: resultWrapper,
    lastUpdatedAt: resultUpdatedAt,
    isStale: resultStale,
  } = useLiveData<ResultRow>(resultsFetcher, {
    intervalMs: 120000,
    staleAfterSec: 600,
  });
  // The actual row may be null (game not yet settled); unwrap from the wrapper.
  const result = (resultWrapper as unknown as { row?: ResultRow | null })?.row ?? null;

  const matchup = matchupLabel(edge, report);

  // Cross-check the URL sport slug against the API-returned sport.
  const { resolved: resolvedSport, mismatch: sportMismatch } = resolveSport(
    sport,
    report,
  );

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-4 p-6">
      {/* Header */}
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/bets"
            className="rounded-sm font-data text-xs text-faint hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
          >
            &larr; bets
          </Link>
          <h1 className="text-lg font-semibold tracking-tight">
            <span className="uppercase text-muted-foreground">
              {sportLabel(resolvedSport)}
            </span>
            {matchup && (
              <span className="ml-2 text-foreground">{matchup}</span>
            )}
            {!matchup && (
              <span className="ml-2 font-data text-faint">{gameId}</span>
            )}
          </h1>
        </div>
        <ModeDot mode={mode} />
      </header>

      {/* Last-updated age strip for live data (stale-never-green rail). */}
      <div className="flex items-center gap-4 text-[10px] font-data">
        <span
          className={edgeStale ? "text-stale" : "text-faint"}
          aria-label="edge-age"
        >
          edge: {edgeError ? "unavailable" : fmtAge(edgeAge)}
          {edgeStale ? " (stale)" : ""}
        </span>
        <span
          className={ingameStale ? "text-stale" : "text-faint"}
          aria-label="ingame-age"
        >
          live: {fmtAge(ingameAge)}
          {ingameStale ? " (stale)" : ""}
        </span>
      </div>

      {/* Sport mismatch notice -- URL slug disagrees with the API sport field. */}
      {sportMismatch && (
        <div
          role="alert"
          aria-label="sport-mismatch-notice"
          className="flex items-start gap-2 border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm"
        >
          <span className="mt-0.5 font-data text-xs uppercase tracking-wide text-stale">
            sport mismatch
          </span>
          <span className="text-foreground">
            This link says{" "}
            <span className="font-semibold text-stale">
              {sportLabel(sport)}
            </span>{" "}
            but this game is{" "}
            <span className="font-semibold text-up">
              {sportLabel(resolvedSport)}
            </span>
            . Showing correct sport.
          </span>
        </div>
      )}

      {/* Honest degradation notice */}
      {mode === "disconnected" ? (
        report ? (
          <Degraded reason="Live feed unavailable -- showing the last snapshot." />
        ) : (
          <Unavailable reason="Live feed unavailable and no snapshot received." />
        )
      ) : null}

      {/* Main layout: left column (prediction + lines + rationale), right (live + grade). */}
      <div className="grid grid-cols-12 gap-4">
        {/* Left column */}
        <div className="col-span-12 flex flex-col gap-4 lg:col-span-7">
          {/* Full prediction / interval (game + props). */}
          <DistributionPanel
            report={report}
            propsData={propsData}
            sport={sport}
            asOf={fmtClock(reportUpdatedAt)}
            stale={mode === "disconnected"}
          />
          {/* Per-book odds matrix (W1). */}
          <BookMatrixTable
            matrix={linesMatrix}
            asOf={fmtClock(linesUpdatedAt)}
            stale={linesStale}
          />
          {/* Execution trail (WS5): best line + devig + decision. */}
          <ExecutionTrail
            {...linesMatrixToExecutionTrail(
              linesMatrix ?? null,
              edge ?? null,
            )}
          />
          {/* Rationale (validated signals + model notes). */}
          <RationalePanel
            report={report}
            sport={sport}
            asOf={fmtClock(reportUpdatedAt)}
            stale={mode === "disconnected"}
          />
        </div>

        {/* Right column */}
        <div className="col-span-12 flex flex-col gap-4 lg:col-span-5">
          {/* Execution hand-in-hand: what the system ACTUALLY staked for this
              game in the paper ledger (units / tier / outcome / CLV) -- the
              money-makers, each linking to its full per-bet execution detail.
              Sits above the would-do trail so "what we did" reads first. */}
          <PlacedBetsForGamePanel sport={resolvedSport} gameId={gameId} />
          {/* Live boxscore + win-prob (W4). */}
          <LiveBoxPanel ingame={ingame} />
          {/* Settlement grade + CLV. */}
          <SettleGradePanel
            edge={edge}
            result={result}
            asOf={fmtClock(resultUpdatedAt ?? edgeUpdatedAt)}
            stale={resultStale || edgeStale}
          />
        </div>
      </div>

      <footer className="mt-2 text-center text-[11px] text-faint">
        One coherent prediction spines every market. Stakes are units; no $ column.
        CLV = beat-the-close yardstick only. vs-close UNPROVEN. Paper mode only.
      </footer>
    </main>
  );
}
