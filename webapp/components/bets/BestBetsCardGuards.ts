// BestBetsCardGuards.ts -- pure UI-side guard helpers for the Best Bets board.
//
// These guards are UI-ONLY safety nets.  They run AFTER the backend has already
// filtered post/final cards, providing a second layer of defence against backend
// leaks.  They are pure functions with zero React dependencies.
//
// HONESTY RAILS:
//   - No $ / no profit / no edge claim language.
//   - degenerate_model=true -> decision=no_bet must be rendered EXPLICITLY, not silently
//     suppressed and not silently rendered as a bet.
//   - live.state in {post,final} -> settled / no bet (game is over).
//
// OWN FILE RULE: <= 300 LOC.  Per-file tests in __tests__/bestbets-guards.test.tsx.

import type { BestBetsCard } from "@/lib/types_w12";

// Statuses carried in BestBetsCard.live.state that indicate the game has ended
// or is fully settled.  Backend should filter these before sending to the UI,
// but we add an explicit UI-side guard as a second line of defence.
const SETTLED_LIVE_STATES = new Set(["post", "final"]);

// Statuses in BestBetsCard.status that indicate the game has ended.
const SETTLED_STATUSES = new Set(["post", "final"]);

// ---------------------------------------------------------------------------
// SuppressReason -- structured reason for suppression so callers can render
// an honest label rather than silently hiding a card.
// ---------------------------------------------------------------------------

export type SuppressReason =
  | "live_state_settled"      // card.live.state in {post, final}
  | "status_settled"          // card.status in {post, final} (second-layer guard)
  | "degenerate_model"        // card.degenerate_model === true
  | null;                     // card is OK to render as a bet

// ---------------------------------------------------------------------------
// shouldSuppressBet -- primary guard function.
//
// Returns a SuppressReason string when the card must NOT be rendered as an
// actionable bet, or null when the card is eligible.
//
// Priority order (highest to lowest):
//   1. live.state settled   -- game over by live-state signal
//   2. status settled       -- game over by top-level status field
//   3. degenerate_model     -- model output is unreliable; render no_bet explicitly
// ---------------------------------------------------------------------------

export function shouldSuppressBet(card: BestBetsCard): SuppressReason {
  // Guard 1: live.state in {post, final}
  const liveState = card.live?.state;
  if (liveState != null && SETTLED_LIVE_STATES.has(liveState)) {
    return "live_state_settled";
  }

  // Guard 2: top-level status in {post, final}
  if (SETTLED_STATUSES.has(card.status)) {
    return "status_settled";
  }

  // Guard 3: degenerate model output
  if (card.degenerate_model === true) {
    return "degenerate_model";
  }

  return null;
}

// ---------------------------------------------------------------------------
// suppressReasonLabel -- human-readable label for the SuppressReason.
// Rendered in the card instead of a bet decision.  Never claims an edge or $.
// ---------------------------------------------------------------------------

export function suppressReasonLabel(reason: SuppressReason): string {
  switch (reason) {
    case "live_state_settled":
      return "settled / no bet (game over -- live state)";
    case "status_settled":
      return "settled / no bet (game over)";
    case "degenerate_model":
      return "decision=no_bet (degenerate model output -- calibration context only)";
    default:
      return "";
  }
}

// ---------------------------------------------------------------------------
// isDecisionNoBet -- narrower check: is this card explicitly decision=no_bet
// (degenerate model)?  Used by the board to render the explicit no_bet label
// rather than silently hiding the card.
// ---------------------------------------------------------------------------

export function isDecisionNoBet(card: BestBetsCard): boolean {
  return card.degenerate_model === true;
}

// ---------------------------------------------------------------------------
// isSettledCard -- check for completed-game guard only (not degenerate_model).
// Used by tests that want to verify the completed-game path independently.
// ---------------------------------------------------------------------------

export function isSettledCard(card: BestBetsCard): boolean {
  const liveState = card.live?.state;
  if (liveState != null && SETTLED_LIVE_STATES.has(liveState)) return true;
  if (SETTLED_STATUSES.has(card.status)) return true;
  return false;
}
