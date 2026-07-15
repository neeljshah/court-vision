"use client";

import { useCallback } from "react";
import Link from "next/link";
import {
  api,
  streamUrl,
  type Report,
  type GameEdge,
  type ClvScoreboard as Clv,
} from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import { useStream } from "@/lib/useStream";
import { GameReport } from "./GameReport";
import { BestBets } from "./BestBets";
import { ClvScoreboard } from "./ClvScoreboard";
import { ModeDot } from "./Primitives";

// GameDetail -- the per-game live view. The report STREAMS over the
// /api/stream/game SSE endpoint (poll fallback). Best bets + the per-game CLV
// scoreboard come from /api/v1/bestbets/{sport}/{game_id}.
//
// Live polling: edge uses useLiveData (pause-on-hidden, last-good, stale badge).
// No bespoke setInterval.

// GameEdgeWithClv: the API returns GameEdge & { clv?: Clv }.
type GameEdgeWithClv = GameEdge & { clv?: Clv };

export function GameDetail({
  sport,
  gameId,
}: {
  sport: string;
  gameId: string;
}) {
  // Streamed report (SSE -> poll fallback).
  const { data: report, mode } = useStream<Report>({
    sseUrl: streamUrl(sport, gameId),
    pollFn: async (s) => {
      const d = await api.report(sport, gameId, s);
      return d as Report;
    },
    pollMs: 5000,
  });

  // Best bets -- polled via useLiveData (pause-on-hidden, last-good, stale badge).
  const edgeFetcher = useCallback(
    (s: AbortSignal) =>
      api.bestbetsGame(sport, gameId, s) as Promise<GameEdgeWithClv>,
    [sport, gameId],
  );
  const { data: edgeData } = useLiveData<GameEdgeWithClv>(edgeFetcher, {
    intervalMs: 8000,
    staleAfterSec: 30,
  });

  // Unwrap edge and clv from the combined response.
  const edge: GameEdge | null = edgeData ?? null;
  const clv: Clv | null = edgeData?.clv ?? null;

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-4 p-6">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/p6"
            className="font-mono text-xs text-muted-foreground hover:text-foreground"
          >
            &larr; slate
          </Link>
          <h1 className="text-lg font-semibold tracking-tight">
            <span className="uppercase text-muted-foreground">{sport}</span>{" "}
            <span className="font-mono text-muted-foreground">{gameId}</span>
          </h1>
        </div>
        <ModeDot mode={mode} />
      </header>

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-7">
          <GameReport report={report} />
        </div>
        <div className="col-span-12 flex flex-col gap-4 lg:col-span-5">
          <BestBets game={edge} sport={sport} />
          <ClvScoreboard clv={clv} />
        </div>
      </div>

      <footer className="mt-2 text-center text-[11px] text-faint">
        Live report streams over SSE (falls back to polling). Stakes are units;
        no dollar column. Paper only; no $ edge is claimed.
      </footer>
    </main>
  );
}
