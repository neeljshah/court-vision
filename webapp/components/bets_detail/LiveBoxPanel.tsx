"use client";

// LiveBoxPanel.tsx -- live boxscore + in-game win-prob when a game is live.
// Shows score/period/clock, calibrated P(home win), and per-player stats table.
// HONESTY RAILS: stale-never-green, INSUFFICIENT_DATA honest, no $, no edge claim.
// FRESHNESS GATE: generated_at > LIVE_STALE_MS -> Stale (never shown as live).
// ingame=null -> skeleton shimmer (neutral checking, never green/red/stale).

import * as React from "react";
import { Badge } from "@/components/p6/Primitives";
import { Unavailable, Empty, Stale } from "@/components/honest/HonestState";
import { UncertaintyBar } from "@/components/depth/UncertaintyBar";
import { Panel as TerminalPanel, PanelHead, Num } from "@/components/ui/terminal";
import { isExtUnavailable } from "@/lib/p5api_ext";
import type { InGameFull, BoxscorePlayer } from "@/lib/p5api_ext";
import {
  LIVE_STALE_MS,
  ageMs,
  fmtAge,
  fmtClockIso,
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

// Local Panel shim: p6/Primitives.Panel currently lacks asOf/stale wiring, so
// this component composes directly from the terminal.tsx primitives instead
// (same title/right/asOf/stale/children/className call shape used below).
function Panel({
  title,
  asOf,
  stale = false,
  right,
  children,
  className,
}: {
  title: string;
  asOf?: string | null;
  stale?: boolean;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <TerminalPanel className={className}>
      <PanelHead title={title} asOf={asOf} stale={stale} right={right} />
      <div className="p-4">{children}</div>
    </TerminalPanel>
  );
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
      asOf={fmtClockIso(ingame.generated_at)}
      stale={isStale}
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
              <span className="text-sm font-semibold text-foreground">{away}</span>
              <Num className="text-xl font-bold text-foreground">
                {ingame.away_score ?? "--"}
              </Num>
              <span className="text-faint">@</span>
              <Num className="text-xl font-bold text-foreground">
                {ingame.home_score ?? "--"}
              </Num>
              <span className="text-sm font-semibold text-foreground">{home}</span>
            </div>
            <Num className="text-right text-xs text-muted-foreground">
              {ingame.period ? `Q${ingame.period}` : ""}
              {ingame.clock ? ` ${ingame.clock}` : ""}
              {ingame.frac_elapsed != null && (
                <span className="ml-1 text-faint">
                  ({(ingame.frac_elapsed * 100).toFixed(0)}% elapsed)
                </span>
              )}
            </Num>
          </div>

          {/* Calibrated win-prob (CALIBRATION only, not a $ edge). */}
          <div className="mb-3">
            <UncertaintyBar
              prob={ingame.p_win ?? null}
              label={`P(${home} win)`}
            />
            <p className="mt-1 font-data text-[10px] text-faint">
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
        <div className="mt-3 border border-warning/40 bg-warning/10 px-2 py-1.5">
          <span className="font-data text-[10px] text-stale">
            IN-GAME CLV: INSUFFICIENT_DATA -- liquid in-play prices unavailable
            (NBA offseason). No CLV is fabricated.
          </span>
        </div>
      )}
    </Panel>
  );
}
