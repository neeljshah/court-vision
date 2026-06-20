"use client";

// LiveBoxPanel.tsx -- live boxscore + in-game win-prob when a game is live.
// Shows score/period/clock, calibrated P(home win), and per-player stats table.
// HONESTY RAILS: stale-never-green, INSUFFICIENT_DATA honest, no $, no edge claim.
// FRESHNESS GATE: generated_at > LIVE_STALE_MS -> Stale (never shown as live).
// ingame=null -> skeleton shimmer (neutral checking, never green/red/stale).

import * as React from "react";
import { Panel, Badge } from "@/components/p6/Primitives";
import { Unavailable, Empty, Stale } from "@/components/honest/HonestState";
import { UncertaintyBar } from "@/components/depth/UncertaintyBar";
import { isExtUnavailable } from "@/lib/p5api_ext";
import type { InGameFull, BoxscorePlayer } from "@/lib/p5api_ext";
import {
  LIVE_STALE_MS,
  ageMs,
  fmtAge,
  fmtStat,
  fmtMin,
  LiveBoxSkeleton,
  AgeChip,
  StaleAgeNote,
  ClvStatusChip,
  BoxTable,
} from "./LiveBoxHelpers";

export interface LiveBoxPanelProps {
  ingame: InGameFull | null;
  className?: string;
}

/** Live boxscore + calibrated win-prob (CLV may be INSUFFICIENT_DATA). */
export function LiveBoxPanel({ ingame, className }: LiveBoxPanelProps) {
  // ingame=null: initial fetch in flight. Show a skeleton shimmer that visually
  // matches the live content shape. This is a neutral "checking" state -- never
  // green, never red, never a stale score. All honest branches below are intact.
  if (!ingame) {
    return (
      <Panel title="Live / in-game" className={className}>
        <LiveBoxSkeleton />
      </Panel>
    );
  }

  if (isExtUnavailable(ingame) || ingame.status === "unavailable") {
    return (
      <Panel title="Live / in-game" className={className}>
        <Unavailable
          reason={
            (ingame as { reason?: string }).reason ??
            "No live game data (offseason or game not started)"
          }
        />
      </Panel>
    );
  }

  // FRESHNESS GATE: compute payload age from generated_at.
  // A stale-but-200 payload (dead daemon or completed game) must NEVER be
  // shown as live -- this directly implements the stale-never-green rail.
  const age = ageMs(ingame.generated_at);
  const isStale = age > LIVE_STALE_MS;

  // Live when period/clock/scores present (including 0). Old !score check
  // wrongly swallowed a real 0-0 tipoff (0 is falsy).
  const hasScore = ingame.home_score != null && ingame.away_score != null;
  const notLive = !ingame.period && !ingame.clock && !hasScore;
  const home = ingame.home ?? "HOME";
  const away = ingame.away ?? "AWAY";
  const players: BoxscorePlayer[] = ingame.players ?? [];

  // Age chip: shown in header only when data is fresh (finite age, below threshold).
  // When stale, no age chip in header -- stale branch renders it inline instead.
  const ageLabel = !isStale && age < Infinity ? fmtAge(age) : null;

  return (
    <Panel
      title="Live / in-game"
      right={
        <div className="flex items-center gap-2">
          {ageLabel && (
            <AgeChip ageLabel={ageLabel} generatedAt={ingame.generated_at} />
          )}
          <ClvStatusChip status={ingame.clv_status} />
          {ingame.clv_is_proxy && (
            <Badge tone="amber">CLV proxy</Badge>
          )}
        </div>
      }
      className={className}
    >
      {/* STALE GATE: payload age exceeds threshold -- show Stale, never
          present score/win-prob as current. Covers dead-daemon and
          completed-game-still-serving-last-snapshot cases.
          The explicit age is surfaced inline so the viewer knows exactly
          how old the snapshot is (stale-never-green rail). */}
      {isStale ? (
        <div>
          <Stale
            asOf={ingame.generated_at ?? undefined}
            reason="Feed not updated -- game may be final or the live daemon is down. Score and win-prob not shown to avoid presenting stale data as live."
          />
          <StaleAgeNote age={age} generatedAt={ingame.generated_at} />
        </div>
      ) : notLive ? (
        <Empty
          label="Game not live"
          hint="Live score and win-prob appear when the game is in progress."
        />
      ) : (
        <>
          {/* Score + clock */}
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-baseline gap-2">
              <span className="text-sm font-semibold text-slate-100">{away}</span>
              <span className="text-xl font-bold tabular-nums text-slate-100">
                {ingame.away_score ?? "--"}
              </span>
              <span className="text-slate-600">@</span>
              <span className="text-xl font-bold tabular-nums text-slate-100">
                {ingame.home_score ?? "--"}
              </span>
              <span className="text-sm font-semibold text-slate-100">{home}</span>
            </div>
            <div className="text-right font-mono text-xs text-slate-400">
              {ingame.period ? `Q${ingame.period}` : ""}
              {ingame.clock ? ` ${ingame.clock}` : ""}
              {ingame.frac_elapsed != null && (
                <span className="ml-1 text-slate-600">
                  ({(ingame.frac_elapsed * 100).toFixed(0)}% elapsed)
                </span>
              )}
            </div>
          </div>

          {/* Calibrated win-prob (CALIBRATION only, not a $ edge). */}
          <div className="mb-3">
            <UncertaintyBar
              prob={ingame.p_win ?? null}
              label={`P(${home} win)`}
            />
            <p className="mt-1 font-mono text-[10px] text-slate-600">
              Calibrated in-game -- static-to-conditional Brier improvement.
              CALIBRATION, not a market edge. vs-close UNPROVEN.
            </p>
          </div>

          {/* Live boxscore */}
          {players.length > 0 ? (
            <BoxTable players={players} />
          ) : (
            <Empty
              label="No player stats yet"
              hint="Live player stats appear as the game progresses."
            />
          )}
        </>
      )}

      {/* Honest CLV note */}
      {ingame.clv_status === "INSUFFICIENT_DATA" && (
        <div className="mt-3 rounded border border-amber-900/30 bg-amber-950/10 px-2 py-1.5">
          <span className="font-mono text-[10px] text-amber-400">
            IN-GAME CLV: INSUFFICIENT_DATA -- liquid in-play prices unavailable
            (NBA offseason). No CLV is fabricated.
          </span>
        </div>
      )}
    </Panel>
  );
}
