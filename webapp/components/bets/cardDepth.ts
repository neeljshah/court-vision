// cardDepth.ts -- helper types and framing logic for BetCard depth layer.
//
// HONESTY RULES:
//   - CLV null -> INSUFFICIENT_DATA (never 0, never greened)
//   - game DONE or degenerate_model -> descriptive/no-bet framing
//   - divergence = "calibrated divergence" (NOT "edge" or "profit")
//   - units only, no $
//
// Pure functions; zero side effects. All types exported for downstream consumers.

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

/** One book's odds entry for a given market side. */
export interface BookLine {
  book: string;
  /** Decimal odds, e.g. 1.91. Must be > 1 to be valid. */
  odds: number;
  /** Spread / total line, null for moneyline. */
  line?: number | null;
}

/** Framing mode the card should adopt. */
export type CardFraming = "bet" | "descriptive";

/** Output of resolveCardFraming -- tells the card what to render. */
export interface CardDepthState {
  framing: CardFraming;
  /** Human-readable reason for descriptive/no-bet framing; null when framing='bet'. */
  descriptive_reason: string | null;
  /** CLV value when available, always null when no live prices exist. */
  clv_display: number | null;
  /** True when clv_display is a proxy estimate rather than a real-time quote. */
  clv_is_proxy: boolean;
  /** 'INSUFFICIENT_DATA' when clv_display is null; formatted string otherwise. */
  clv_label: string;
  /** Signed divergence: model_prob - devigged_market_prob. */
  divergence: number;
  /** Formatted divergence label. Never says 'edge' or 'profit'. */
  divergence_label: string;
  /** Whether the divergence is large enough to be considered signal-grade (>= 5pp abs). */
  divergence_is_signal: boolean;
}

// ---------------------------------------------------------------------------
// CLV helpers
// ---------------------------------------------------------------------------

const CLV_INSUFFICIENT = "INSUFFICIENT_DATA";

/**
 * Formats a CLV value for display. Returns INSUFFICIENT_DATA when clv is null.
 * Never returns "0" or "0.0%" to avoid implying a neutral baseline exists.
 */
export function formatClv(clv: number | null, is_proxy: boolean): string {
  if (clv === null) return CLV_INSUFFICIENT;
  const sign = clv > 0 ? "+" : "";
  const pct = `${sign}${(clv * 100).toFixed(1)}%`;
  return is_proxy ? `${pct} (proxy)` : pct;
}

// ---------------------------------------------------------------------------
// Divergence helpers
// ---------------------------------------------------------------------------

/**
 * Formats a calibrated divergence for display. Signed, never labeled 'edge'/'profit'.
 * Positive divergence = model sees this side as more likely than market.
 * Negative divergence = model sees this side as less likely (valid under/away signal).
 */
export function formatDivergence(divergence: number): string {
  const sign = divergence >= 0 ? "+" : "";
  return `${sign}${(divergence * 100).toFixed(1)}pp`;
}

/** True when |divergence| >= 0.05 (5pp) -- signal-grade threshold. */
export function isDivergenceSignal(divergence: number): boolean {
  return Math.abs(divergence) >= 0.05;
}

// ---------------------------------------------------------------------------
// Framing resolver -- core logic
// ---------------------------------------------------------------------------

export interface ResolveFramingInput {
  /** True when the game has ended / settled. */
  game_done: boolean;
  /**
   * True when the model output is degenerate:
   *   - model_prob is 0, 1, NaN, or out of [0,1]
   *   - or the signal stack flagged the prediction as unreliable
   */
  degenerate_model: boolean;
  /** [0,1] calibrated model probability. */
  model_prob: number;
  /** [0,1] devigged market probability. */
  market_prob: number;
  /** Null when no live prices exist (offseason / no feed). */
  clv: number | null;
  /** True when clv is a proxy estimate, not a real-time quote. */
  clv_is_proxy: boolean;
}

/**
 * resolveCardFraming -- returns the canonical CardDepthState for a bet card.
 *
 * DONE or degenerate_model always yields 'descriptive' framing, suppressing
 * the bet recommendation. CLV null always yields INSUFFICIENT_DATA. Divergence
 * is always a calibrated signal, never an edge/profit claim.
 */
export function resolveCardFraming(input: ResolveFramingInput): CardDepthState {
  const {
    game_done,
    degenerate_model,
    model_prob,
    market_prob,
    clv,
    clv_is_proxy,
  } = input;

  const divergence = model_prob - market_prob;
  const divergence_label = formatDivergence(divergence);
  const divergence_is_signal = isDivergenceSignal(divergence);

  const clv_display = clv;
  const clv_label = formatClv(clv, clv_is_proxy);

  // Determine framing
  let framing: CardFraming = "bet";
  let descriptive_reason: string | null = null;

  if (game_done) {
    framing = "descriptive";
    descriptive_reason = "Game has ended -- no active bet recommendation.";
  } else if (degenerate_model) {
    framing = "descriptive";
    descriptive_reason =
      "Model output is degenerate for this market. Showing calibration context only.";
  } else if (model_prob <= 0 || model_prob >= 1 || !isFinite(model_prob)) {
    framing = "descriptive";
    descriptive_reason =
      "Model probability is out of range -- calibration unavailable.";
  }

  return {
    framing,
    descriptive_reason,
    clv_display,
    clv_is_proxy,
    clv_label,
    divergence,
    divergence_label,
    divergence_is_signal,
  };
}

// ---------------------------------------------------------------------------
// Devigged market probability helper
// ---------------------------------------------------------------------------

/**
 * Devig a pair of decimal odds (two-outcome market) using the Shin method
 * approximation. For a moneyline: impliedP = 1/odds_A / (1/odds_A + 1/odds_B).
 * When only one side's odds are given (single entry), falls back to simple inversion.
 *
 * Returns a probability in [0.01, 0.99], never 0 or 1.
 */
export function devigProb(oddsFor: number, oddsAgainst?: number): number {
  if (oddsFor <= 1) return 0.5; // degenerate guard
  const rawFor = 1 / oddsFor;
  if (oddsAgainst == null || oddsAgainst <= 1) {
    // Single-side devig: simple inversion, clamped
    return Math.max(0.01, Math.min(0.99, rawFor));
  }
  const rawAgainst = 1 / oddsAgainst;
  const total = rawFor + rawAgainst;
  if (total <= 0) return 0.5;
  return Math.max(0.01, Math.min(0.99, rawFor / total));
}

// ---------------------------------------------------------------------------
// Best-line finder
// ---------------------------------------------------------------------------

/**
 * findBestLine -- returns the index of the best line (highest decimal odds)
 * among a list of BookLine entries. Ties broken by first occurrence.
 * Returns -1 if the list is empty.
 */
export function findBestLine(books: BookLine[]): number {
  if (books.length === 0) return -1;
  let bestIdx = 0;
  let bestOdds = books[0].odds;
  for (let i = 1; i < books.length; i++) {
    if (books[i].odds > bestOdds) {
      bestOdds = books[i].odds;
      bestIdx = i;
    }
  }
  return bestIdx;
}
