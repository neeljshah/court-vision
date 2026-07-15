"use client";

// GameView -- the full per-game view for /games/[sport]/[gameId]. Reuses the
// existing p6 building blocks (GameReport = pregame prediction + provenance +
// FULL market surface; BestBets = units/tier/decision + paper-bet action;
// ClvScoreboard = beat-the-close yardstick) and adds the per-game in-game
// calibration number. The report STREAMS over SSE (poll fallback).
//
// HONESTY RAILS: UNITS / probability only -- NO $ anywhere. no_bet below floor
// is shown honestly; vs_close is UNPROVEN; paper mode only; local only.

import { useCallback } from "react";
import Link from "next/link";
import {
  api,
  isUnavailable,
  streamUrl,
  type Report,
  type GameEdge,
  type ClvScoreboard as Clv,
} from "@/lib/api";
import { useLiveData } from "@/lib/useLiveData";
import { useStream } from "@/lib/useStream";
import { GameReport } from "@/components/p6/GameReport";
import { BestBets } from "@/components/p6/BestBets";
import { ClvScoreboard } from "@/components/p6/ClvScoreboard";
import { ModeDot } from "@/components/p6/Primitives";
import { sportLabel } from "../../card-utils";
import { InGameNumber } from "./InGameNumber";
import {
  CoherentPrediction,
  GameMarketSurface,
  ValidatedSignalsStrip,
} from "@/components/games_depth";
import { Degraded, Unavailable } from "@/components/honest/HonestState";
import { PanelErrorBoundary } from "@/components/honest/PanelErrorBoundary";
import { LiveInGamePanel } from "@/components/live/LiveInGamePanel";
import type { Unavailable as UnavailableT } from "@/lib/types";

export function GameView({
  sport,
  gameId,
}: {
  sport: string;
  gameId: string;
}) {
  const { data: report, mode } = useStream<Report>({
    sseUrl: streamUrl(sport, gameId),
    pollFn: async (s) => (await api.report(sport, gameId, s)) as Report,
    pollMs: 5000,
  });

  // Migrate bestbetsGame from bespoke setInterval to the canonical useLiveData hook.
  // On a failed poll the hook retains the last-good GameEdge and marks isStale --
  // the panel never goes blank/red, and fetching pauses when the tab is hidden.
  const bestbetsFetcher = useCallback(
    (signal: AbortSignal) =>
      api.bestbetsGame(sport, gameId, signal) as Promise<
        (GameEdge & { clv?: Clv }) | UnavailableT
      >,
    [sport, gameId],
  );

  const { data: edgeData } = useLiveData<GameEdge & { clv?: Clv }>(
    bestbetsFetcher,
    { intervalMs: 15_000, staleAfterSec: 60 },
  );

  // Derive the edge/clv props from the live-data result, identical to before.
  let edge: GameEdge | null = null;
  let clv: Clv | null = null;
  if (edgeData !== null) {
    if (isUnavailable(edgeData)) {
      edge = { game_id: gameId, status: "unavailable", reason: (edgeData as unknown as UnavailableT).reason };
    } else {
      const g = edgeData as GameEdge & { clv?: Clv };
      edge = g;
      if (g.clv) clv = g.clv;
    }
  }

  // Derive live panel props from the streamed report (pregame model probability
  // and matchup label). Both are display-only; null is an honest "not yet known".
  const pregameProb: number | null =
    report?.pregame?.model_probs?.["home_ml"] ?? null;
  const matchupLabel: string | null =
    report?.pregame?.away && report?.pregame?.home
      ? `${report.pregame.away} @ ${report.pregame.home}`
      : null;

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-4 p-6">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/games"
            className="rounded-sm font-data text-xs text-faint transition-colors hover:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
          >
            &larr; games
          </Link>
          <h1 className="text-lg font-semibold tracking-tight">
            <span className="uppercase text-muted-foreground">{sportLabel(sport)}</span>{" "}
            <span className="font-data text-faint">{gameId}</span>
          </h1>
        </div>
        <ModeDot mode={mode} />
      </header>

      {/* Honest connection state: the live feed is down AND we have no last-good
          frame to show. Render an explicit degraded/unavailable note rather than
          a frozen panel presented as live. */}
      {mode === "disconnected" ? (
        report ? (
          <Degraded reason="Live feed unavailable -- showing the last received snapshot, not a live number." />
        ) : (
          <Unavailable reason="Live feed unavailable and no snapshot has been received yet. No number is fabricated." />
        )
      ) : null}

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 flex flex-col gap-4 lg:col-span-7">
          {/* The ONE coherent prediction: provenance + uncertainty (no $). */}
          <CoherentPrediction report={report} sport={sport} />
          <GameReport report={report} />
          {/* The FULL coherent market surface off one engine matrix (no $). */}
          <GameMarketSurface report={report} sport={sport} />
        </div>
        <div className="col-span-12 flex flex-col gap-4 lg:col-span-5">
          <BestBets game={edge} sport={sport} />
          <InGameNumber sport={sport} gameId={gameId} />
          {/* LiveInGamePanel: score/clock/win-prob bar depth block.
              Wrapped in PanelErrorBoundary so a render crash here cannot
              blank the rest of the route. Does NOT duplicate InGameNumber's
              probability number -- adds score/clock/bar depth. */}
          <PanelErrorBoundary label="live in-game panel">
            <LiveInGamePanel
              sport={sport}
              gameId={gameId}
              pregameProb={pregameProb}
              matchupLabel={matchupLabel}
            />
          </PanelErrorBoundary>
          <ClvScoreboard clv={clv} />
          {/* Which gate-tested signals feed this sport (verdict chips). */}
          <ValidatedSignalsStrip sport={sport} />
        </div>
      </div>

      <footer className="mt-2 text-center font-data text-[11px] text-faint">
        One coherent prediction spines every market. Stakes are units; there is
        no dollar column. vs-close UNPROVEN. Paper only; no $ edge is claimed.
      </footer>
    </main>
  );
}
