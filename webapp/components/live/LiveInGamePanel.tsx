"use client";

/**
 * LiveInGamePanel.tsx -- WS4 self-refreshing in-game depth panel.
 *
 * Renders score + quarter/clock + calibrated win-prob bar for in_progress games.
 * Shows "Final" for post-game, pregame prior for future games. Honest freshness
 * via PanelHead/AsOf (stale-never-green). Never claims $/edge -- CALIBRATION only.
 * Polls via useLiveDataUrl (20s; pauses when tab hidden; never crashes on failure).
 *
 * HONESTY RAILS: probability/UNITS only -- no $ -- CALIBRATION not edge.
 * stale-never-green; CLV may be INSUFFICIENT_DATA (shown honestly). ASCII only.
 * <=300 LOC.
 */

import * as React from "react";
import { useLiveDataUrl } from "@/lib/useLiveData";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";
import { cn } from "@/lib/utils";
import type { InGameFull } from "@/lib/types";
import { P5_BASE } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Public interface
// ---------------------------------------------------------------------------

export interface LiveInGamePanelProps {
  sport: string;
  gameId: string;
  /** Pregame model P(home win) -- shown when no live state. null renders nothing. */
  pregameProb?: number | null;
  /** "Away @ Home" matchup label. Falls back to sport/gameId. */
  matchupLabel?: string | null;
  className?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type Phase = "in_progress" | "post" | "pre";

function derivePhase(data: InGameFull | null): Phase {
  if (!data || data.status === "unavailable") return "pre";
  const period = data.score?.period ?? 0;
  const clock = data.score?.clock ?? "";
  // Period > 0 and clock present -> game is in progress
  if (period > 0 && clock !== "") {
    // Final: period >= 4 and clock is "0:00"
    if (period >= 4 && (clock === "0:00" || clock === "00:00")) return "post";
    return "in_progress";
  }
  return "pre";
}

function fmtProb(p: number): string {
  return `${(p * 100).toFixed(1)}%`;
}

function parseMatchup(label: string | null): { home: string; away: string } {
  if (!label) return { home: "Home", away: "Away" };
  const parts = label.split("@");
  return parts.length === 2
    ? { away: parts[0].trim() || "Away", home: parts[1].trim() || "Home" }
    : { home: "Home", away: "Away" };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function CalibLabel({ text }: { text: string }) {
  return <span className="font-data text-[10px] text-stale">{text}</span>;
}

/**
 * Thin horizontal model-probability bar (amber, bg-s-model). Only the model
 * side is real data here (no in-game market price feed) so the remainder
 * renders as a neutral surface segment, never a fabricated market series.
 */
function WinProbBar({ pHome }: { pHome: number }) {
  const homePct = Math.round(Math.max(0, Math.min(1, pHome)) * 100);
  return (
    <div
      data-testid="win-prob-bar"
      role="meter"
      aria-label={`Home win probability ${homePct}% calibration only`}
      aria-valuenow={homePct}
      aria-valuemin={0}
      aria-valuemax={100}
      className="flex flex-col gap-1"
    >
      <div className="flex h-2 overflow-hidden bg-surface-2">
        <div className="h-full bg-s-model transition-all" style={{ width: `${homePct}%` }} />
        <div className="h-full bg-surface-3 transition-all" style={{ width: `${100 - homePct}%` }} />
      </div>
      <div className="flex justify-between font-data text-[10px] tabular text-muted-foreground">
        <span>{`Home ${homePct}%`}</span>
        <CalibLabel text="CALIBRATION -- not edge" />
        <span>{`${100 - homePct}% Away`}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase renderers
// ---------------------------------------------------------------------------

function InProgressContent({ data, home, away }: {
  data: InGameFull;
  home: string;
  away: string;
}) {
  const score = data.score;
  const period = score?.period;
  const clock = score?.clock;
  const periodClock =
    period && period > 0
      ? `Q${period}${clock ? ` ${clock}` : ""}`
      : "live";

  const pHome = data.win_prob?.p_home ?? null;
  const provenance = data.win_prob?.provenance ?? [];
  const clvStatus = data.clv_status ?? null;

  return (
    <div data-testid="in-progress-state" className="flex flex-col gap-3">
      {/* Score line */}
      <div data-testid="score-line" className="flex items-center justify-between">
        <span className="font-data text-base font-semibold tabular text-foreground">
          {away}{" "}
          <Num className="text-foreground">{score?.away ?? "--"}</Num>
          <span className="mx-2 text-xs font-normal text-faint">@</span>
          <Num className="text-foreground">{score?.home ?? "--"}</Num>
          {" "}{home}
        </span>
        <span
          data-testid="quarter-clock"
          className="font-data text-xs font-semibold text-stale"
        >
          {periodClock}
        </span>
      </div>

      {/* Win-prob bar (only when data available) */}
      {pHome != null ? (
        <>
          <WinProbBar pHome={pHome} />
          {provenance.length > 0 && (
            <span className="font-data text-[10px] text-faint">
              {provenance.join(" | ")}
            </span>
          )}
        </>
      ) : (
        <span className="text-xs text-muted-foreground">{"Win prob: checking..."}</span>
      )}

      {clvStatus != null && (
        <CalibLabel
          text={
            clvStatus === "INSUFFICIENT_DATA"
              ? "CLV: INSUFFICIENT_DATA (in-game CLV unproven)"
              : `CLV: ${clvStatus}`
          }
        />
      )}
    </div>
  );
}

function PostContent({ data, home, away }: {
  data: InGameFull | null;
  home: string;
  away: string;
}) {
  const score = data?.score;
  return (
    <div data-testid="final-state" className="flex flex-col gap-1">
      <span className="text-sm font-semibold text-muted-foreground">{"Final"}</span>
      {score?.home != null && score?.away != null && (
        <span className="font-data text-xs tabular text-faint">
          {`${away} ${score.away} -- ${home} ${score.home}`}
        </span>
      )}
    </div>
  );
}

function PreContent({ pregameProb }: { pregameProb: number | null }) {
  return (
    <div data-testid="pregame-state" className="flex flex-col gap-1">
      {pregameProb != null ? (
        <>
          <span className="text-xs text-muted-foreground">
            {"Pregame win prob (home): "}
            <Num className="font-semibold text-foreground">{fmtProb(pregameProb)}</Num>
          </span>
          <CalibLabel text="pregame calibration -- not edge" />
        </>
      ) : (
        <span className="text-sm text-faint" data-testid="pregame-no-prob">
          {"Pregame -- no live data yet"}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function LiveInGamePanel({
  sport,
  gameId,
  pregameProb = null,
  matchupLabel = null,
  className,
}: LiveInGamePanelProps) {
  const url = `${P5_BASE}/api/ingame/${sport}/${encodeURIComponent(gameId)}/full`;
  const { data, ageSec, isStale, error, isLoading } = useLiveDataUrl<InGameFull>(url, {
    intervalMs: 20_000,
    staleAfterSec: 90,
    timeoutMs: 8_000,
    cacheKey: `game:${sport}:${gameId}:ingame-full`,
  });

  const phase = derivePhase(data);
  const { home, away } = parseMatchup(matchupLabel);
  const isFirstLoad = isLoading && data === null;

  // Real as-of stamp from the last successful poll; "--:--:--" before any data.
  const asOf =
    ageSec != null ? new Date(Date.now() - ageSec * 1000).toLocaleTimeString() : "--:--:--";
  const stale = isStale || Boolean(error);

  return (
    <div data-testid="live-ingame-panel">
      <Panel className={cn("flex flex-col", className)}>
        <PanelHead
          title={matchupLabel ?? `${sport.toUpperCase()} / ${gameId}`}
          asOf={asOf}
          stale={stale}
        />
        <div className="flex flex-col gap-3 px-3 py-2">
          {/* Phase-driven body */}
          {isFirstLoad ? (
            <p className="text-sm text-faint" data-testid="loading-state">{"checking..."}</p>
          ) : phase === "in_progress" && data ? (
            <InProgressContent data={data} home={home} away={away} />
          ) : phase === "post" ? (
            <PostContent data={data} home={home} away={away} />
          ) : (
            <PreContent pregameProb={pregameProb} />
          )}
        </div>
      </Panel>
    </div>
  );
}
