"use client";

/**
 * GameStatusChip.tsx -- shared presentational primitive for LIVE / PREGAME / DONE.
 *
 * Addresses review finding FD-07: a settled game must never show a LIVE pulse or
 * a bet chip.  This chip is the single canonical renderer for game status across
 * slate cards and the WS5 live view; no surface should duplicate this logic.
 *
 * RAILS:
 *   - ASCII only (no Unicode arrows, em-dashes, ellipses, etc.)
 *   - Pure + presentational: no fetching, no store access.
 *   - DONE tone is neutral (border/muted) -- no pulse on a finished game.
 *   - LIVE tone is amber (in-progress) -- deliberate, never success/green.
 *   - PREGAME tone is neutral (upcoming).
 *   - Token-driven per Direction A "Amber Console": flat borders, no rounded pill.
 *   - a11y: role="status" + aria-label conveying both status and optional period/clock.
 *   - <=300 LOC.
 */

import * as React from "react";
import { cn } from "@/lib/utils";
import { type GameStatus, statusLabel } from "./gameStatus";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface GameStatusChipProps {
  /** The derived status. Use deriveGameStatus() from gameStatus.ts. */
  status: GameStatus;
  /**
   * Optional live period/quarter label (e.g. "Q3 8:42"). Rendered next to the
   * status pill for LIVE games only. ASCII only.
   */
  period?: string | null;
  /** Extra CSS classes for the wrapper span. */
  className?: string;
  /**
   * Size variant.
   *   sm  -- compact (default) -- used in slate cards.
   *   md  -- slightly larger  -- used in game headers.
   */
  size?: "sm" | "md";
}

// ---------------------------------------------------------------------------
// Token maps
// ---------------------------------------------------------------------------

/**
 * Tone per status -- token-driven, flat borders (no rounded surfaces, no glow).
 *
 * DONE:    neutral border/muted ink  -- no pulse; the game is over.
 * LIVE:    amber (--warning)         -- visually distinct and urgent, never success/green.
 * PREGAME: neutral border/muted ink  -- not yet started.
 */
const STATUS_TONE: Record<GameStatus, string> = {
  DONE:    "border-border text-muted-foreground",
  LIVE:    "border-warning/60 text-stale",
  PREGAME: "border-border text-muted-foreground",
};

const SIZE_CLASSES: Record<"sm" | "md", string> = {
  sm: "px-1.5 py-0.5 text-[10px]",
  md: "px-2 py-0.5 text-xs",
};

// ---------------------------------------------------------------------------
// LivePulse -- small animated dot shown ONLY for LIVE status
// ---------------------------------------------------------------------------

/**
 * A pulsing amber dot conveying "game is in progress".
 * NOT rendered for DONE or PREGAME -- a settled game must never show a pulse.
 * CSS animation relies on Tailwind's built-in `animate-ping` (opacity + scale).
 */
function LivePulse() {
  return (
    <span
      aria-hidden="true"
      className="relative inline-flex h-1.5 w-1.5 shrink-0"
    >
      {/* Outer ping ring */}
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-warning opacity-60" />
      {/* Inner solid dot */}
      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-warning" />
    </span>
  );
}

// ---------------------------------------------------------------------------
// GameStatusChip
// ---------------------------------------------------------------------------

/**
 * GameStatusChip -- renders the canonical status pill for a game.
 *
 * Usage:
 *   const status = deriveGameStatus(game.live?.state, game.tipoffMs);
 *   <GameStatusChip status={status} period={game.live?.period} />
 *
 * The chip is purely presentational.  All status derivation must happen upstream
 * via deriveGameStatus() so the logic is testable without React.
 */
export function GameStatusChip({
  status,
  period,
  className,
  size = "sm",
}: GameStatusChipProps) {
  const label = statusLabel(status);
  const isLive = status === "LIVE";

  // Build the accessible label: e.g. "LIVE Q3 8:42" or "DONE" or "PREGAME"
  const ariaLabel = isLive && period ? `${label} ${period}` : label;

  return (
    <span
      role="status"
      aria-label={ariaLabel}
      data-game-status={status}
      className={cn(
        "inline-flex items-center gap-1 border font-data font-semibold uppercase tracking-wide",
        STATUS_TONE[status],
        SIZE_CLASSES[size],
        className,
      )}
    >
      {isLive && <LivePulse />}
      <span>{label}</span>
      {isLive && period ? (
        <span
          aria-hidden="true"
          className="ml-0.5 font-data text-stale normal-case tracking-normal"
        >
          {period}
        </span>
      ) : null}
    </span>
  );
}

export default GameStatusChip;
