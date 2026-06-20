/**
 * gameStatus.ts -- pure helpers for deriving LIVE / PREGAME / DONE status.
 *
 * No React, no fetching. Safe to import in tests and non-React contexts.
 *
 * RAILS:
 *   - ASCII only (no Unicode arrows, em-dashes, etc.)
 *   - DONE wins over LIVE whenever state signals completion -- a settled game
 *     must never show a live pulse or a bet chip downstream (iter-2 P0 fix).
 *   - isLikelyDone provides a stale-guard: a tipoff > typicalDurationMin in
 *     the past with absent/unknown state resolves DONE, not LIVE.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** The three canonical game statuses the UI renders. */
export type GameStatus = "LIVE" | "PREGAME" | "DONE";

/**
 * Subset of live.state strings the API may emit.
 * Modelled as a loose string so callers can pass raw API values; the
 * helpers normalise case and handle unknown values gracefully.
 */
export type LiveStateString =
  | "in"        // game is live / in-progress
  | "live"      // explicit live
  | "pre"       // pregame / scheduled
  | "upcoming"  // scheduled (synonym)
  | "post"      // final / post-game
  | "final"     // explicit final
  | "ft"        // full-time (soccer alias)
  | "f"         // final abbreviation
  | (string & {}); // allow any raw string without losing the named literals

// ---------------------------------------------------------------------------
// Sets of canonical values for each bucket
// ---------------------------------------------------------------------------

const LIVE_STATES = new Set(["in", "live", "inprogress", "in_progress"]);
const DONE_STATES = new Set(["post", "final", "ft", "f", "finished", "complete", "completed", "end"]);

// ---------------------------------------------------------------------------
// deriveGameStatus
// ---------------------------------------------------------------------------

/**
 * Derive the GameStatus from the raw live.state string and an optional tipoff.
 *
 * Priority order (DONE-first ensures settled games never revert to LIVE):
 *   1. state in DONE_STATES  -> DONE
 *   2. state in LIVE_STATES  -> LIVE
 *   3. scoreboard active     -> LIVE  (fallback when state is absent)
 *   4. tipoff in the past    -> LIVE  (game has started but state unknown)
 *   5. otherwise             -> PREGAME
 *
 * @param state       Raw live.state string from the API (may be absent/null/undefined).
 * @param tipoffMs    Unix ms of game tipoff (optional). When absent the heuristic is skipped.
 * @param nowMs       Current time in Unix ms (default: Date.now()). Injected for testability.
 * @param scoreboardActive  True when the live scoreboard indicates an active game clock.
 */
export function deriveGameStatus(
  state: LiveStateString | null | undefined,
  tipoffMs?: number | null,
  nowMs: number = Date.now(),
  scoreboardActive = false,
): GameStatus {
  const normalised = (state ?? "").toLowerCase().trim().replace(/[-\s]/g, "_");

  // DONE wins first -- a completed game must never flip back to LIVE.
  if (DONE_STATES.has(normalised)) return "DONE";

  // Explicit live state.
  if (LIVE_STATES.has(normalised)) return "LIVE";

  // Scoreboard heuristic (game clock is running without a state string).
  if (scoreboardActive) return "LIVE";

  // Tipoff-in-the-past heuristic when state is absent/unrecognised.
  if (tipoffMs != null && nowMs >= tipoffMs) return "LIVE";

  return "PREGAME";
}

// ---------------------------------------------------------------------------
// isLikelyDone
// ---------------------------------------------------------------------------

/**
 * Stale-guard: returns true when the tipoff is old enough that the game has
 * almost certainly ended, even if `state` is absent or unrecognised.
 *
 * Typical NBA game duration: ~130 min (regulation + stoppages).
 * Typical soccer: ~110 min. Caller supplies the domain value.
 *
 * A generous 20% buffer is added internally so a slightly long game is not
 * misclassified.  Only applies when `state` is absent or unrecognised; known
 * DONE / LIVE states are authoritative and bypass this guard.
 *
 * @param tipoffMs          Unix ms of game tipoff.
 * @param nowMs             Current time in Unix ms (default: Date.now()).
 * @param typicalDurationMin Typical total duration of one game in minutes (default: 130).
 */
export function isLikelyDone(
  tipoffMs: number,
  nowMs: number = Date.now(),
  typicalDurationMin = 130,
): boolean {
  const bufferFactor = 1.2; // 20% buffer over typical duration
  const thresholdMs = typicalDurationMin * 60 * 1000 * bufferFactor;
  return nowMs - tipoffMs >= thresholdMs;
}

// ---------------------------------------------------------------------------
// statusLabel -- human-readable label for each status (ASCII only)
// ---------------------------------------------------------------------------

/** Returns the canonical display label for a GameStatus. ASCII only. */
export function statusLabel(status: GameStatus): string {
  switch (status) {
    case "LIVE":    return "LIVE";
    case "DONE":    return "DONE";
    case "PREGAME": return "PREGAME";
  }
}
