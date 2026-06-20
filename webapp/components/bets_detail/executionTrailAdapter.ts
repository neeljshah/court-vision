// executionTrailAdapter.ts -- pure adapter: LinesMatrix + edge -> ExecutionTrail props.
//
// WS5-card-detail-exec-trail: wires the orphaned ExecutionTrail into CardDetailView
// as a pure data-transform layer. CardDetailView only needs an import + one mounted
// section; no business logic leaks into the view.
//
// HONESTY RAILS:
//   - Best line = highest decimal odds across ALL books / sides (lowest vig).
//   - UNITS not $ anywhere. No dollar column, no dollar P&L.
//   - When matrix is null or unavailable, bookLines is empty (honest unavailable).
//   - devig.fair_prob derived from best_odds via Shin-implied inverse;
//     vig_pct = 1 - fair_prob (rough vig estimate -- presented as a label, not $ edge).
//   - decision/tier/units threaded from the edge's BestBet for the supplied market.
//   - CLV may be INSUFFICIENT_DATA -- passed through honestly, never fabricated.

import type { LinesMatrix, MarketMatrix } from "@/lib/p5api_ext";
import { isExtUnavailable } from "@/lib/p5api_ext";
import type { GameEdge, BestBet } from "@/lib/types";
import type {
  BookLineRow,
  DevigResult,
  DecisionStep,
  TierLabel,
} from "@/components/execution/ExecutionTrail";

// ---------------------------------------------------------------------------
// Exported adapter result shape
// ---------------------------------------------------------------------------

export type ExecutionTrailData = {
  /** All books sorted by descending decimal odds; best-marked row has isBest=true. */
  bookLines: BookLineRow[];
  /** Name of the book offering the best (highest) decimal odds. Null when empty. */
  bestBook: string | null;
  /** Shin-implied devig from the best quote. Null when no quotes exist. */
  devig: DevigResult | null;
  /** Decision from the edge BestBet for the primary market (or null). */
  decision: DecisionStep | null;
  /** Stake in UNITS (never $). Null when no decision or no_bet. */
  stakeUnits: number | null;
  /** Tier from the edge BestBet. Null when absent. */
  tier: TierLabel;
  /**
   * CLV status. May be INSUFFICIENT_DATA -- always passed through honestly.
   * Null when no BestBet.
   */
  clvStatus: string | null;
  /** Calibrated model prob from the BestBet (probability, never $ edge). */
  modelProb: number | null;
  /** Human-readable note from the BestBet reason field. */
  decisionNote: string | null;
};

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Collect every BookQuote from all sides of a single MarketMatrix. */
function flattenMarketQuotes(
  m: MarketMatrix,
): Array<{ book: string; odds: number | null; line: number | null; is_pm: boolean; captured_at: string | null }> {
  const seen = new Map<string, { odds: number | null; line: number | null; is_pm: boolean; captured_at: string | null }>();
  for (const quotes of Object.values(m.sides)) {
    for (const q of quotes) {
      // Keep the best (highest) odds seen per book across all sides.
      const prev = seen.get(q.book);
      const qOdds = q.odds ?? -Infinity;
      const prevOdds = prev?.odds ?? -Infinity;
      if (!prev || qOdds > prevOdds) {
        seen.set(q.book, { odds: q.odds, line: q.line, is_pm: q.is_pm, captured_at: q.captured_at });
      }
    }
  }
  return Array.from(seen.entries()).map(([book, rest]) => ({ book, ...rest }));
}

/**
 * Simple Shin-implied fair probability from a single decimal odds quote.
 * For a balanced two-sided market: fair_prob ~ 1 / odds.
 * vig_pct = 1 - fair_prob (approximate overround on one leg).
 * Presented as a descriptive ratio -- NOT a $ edge.
 */
function shinDevig(decimalOdds: number): DevigResult {
  const fair_prob = 1 / decimalOdds;
  const vig_pct = Math.max(0, 1 - fair_prob);
  return { fair_prob, vig_pct };
}

// Primary market to show in the trail (first bet, or moneyline fallback).
function primaryBet(edge: GameEdge | null): BestBet | null {
  const bets = edge?.best_bets ?? edge?.candidates ?? [];
  if (bets.length === 0) return null;
  // Prefer the bet decision; otherwise first candidate.
  return bets.find((b) => b.decision === "bet") ?? bets[0];
}

// ---------------------------------------------------------------------------
// Main adapter
// ---------------------------------------------------------------------------

/**
 * Transforms a LinesMatrix + GameEdge into ExecutionTrailData for ExecutionTrail.
 *
 * Rules:
 *   - bookLines: sorted descending by decimal_odds (best = highest odds).
 *   - bestBook: book with the highest decimal_odds across all markets / sides.
 *   - devig: Shin-implied from bestBook's odds; null when no quotes.
 *   - decision/tier/stakeUnits/modelProb/clvStatus: from the primary BestBet.
 *   - When matrix is null, unavailable, or has no markets: bookLines = [].
 */
export function linesMatrixToExecutionTrail(
  matrix: LinesMatrix | null,
  edge: GameEdge | null,
): ExecutionTrailData {
  // Gather book lines from the matrix.
  let bookLines: BookLineRow[] = [];

  const matrixOk =
    matrix !== null &&
    !isExtUnavailable(matrix) &&
    matrix.status !== "unavailable" &&
    typeof matrix.markets === "object" &&
    matrix.markets !== null;

  if (matrixOk && matrix) {
    const rawQuotes: Array<{ book: string; odds: number | null; line: number | null; is_pm: boolean; captured_at: string | null }> = [];

    for (const m of Object.values(matrix.markets)) {
      const quotes = flattenMarketQuotes(m);
      for (const q of quotes) {
        rawQuotes.push(q);
      }
    }

    // De-dup by book name -- keep highest decimal_odds per book.
    const byBook = new Map<string, { odds: number | null; line: number | null; is_pm: boolean; captured_at: string | null }>();
    for (const q of rawQuotes) {
      const prev = byBook.get(q.book);
      const qOdds = q.odds ?? -Infinity;
      const prevOdds = prev?.odds ?? -Infinity;
      if (!prev || qOdds > prevOdds) {
        byBook.set(q.book, { odds: q.odds, line: q.line, is_pm: q.is_pm, captured_at: q.captured_at });
      }
    }

    // Build BookLineRow[], sorted descending by decimal_odds.
    bookLines = Array.from(byBook.entries())
      .map(([book, rest]) => ({
        book,
        decimal_odds: rest.odds,
        line: rest.line,
        is_pm: rest.is_pm,
        captured_at: rest.captured_at,
      }))
      .sort((a, b) => {
        const ao = a.decimal_odds ?? -Infinity;
        const bo = b.decimal_odds ?? -Infinity;
        return bo - ao; // descending: best (highest) first
      });
  }

  // Determine the best book (highest decimal_odds).
  const bestEntry = bookLines.length > 0 ? bookLines[0] : null;
  const bestBook = bestEntry && bestEntry.decimal_odds != null ? bestEntry.book : null;

  // Compute devig from the best-line odds.
  const bestOdds = bestEntry?.decimal_odds;
  const devig =
    bestOdds != null && Number.isFinite(bestOdds) && bestOdds > 1
      ? shinDevig(bestOdds)
      : null;

  // Thread decision/tier/units/clv from the primary BestBet.
  const bet = primaryBet(edge);
  const decision: DecisionStep | null = bet?.decision ?? null;
  const tier = (bet?.tier ?? null) as TierLabel;
  const stakeUnits =
    bet && bet.decision === "bet" ? (bet.stake_units ?? null) : null;
  const modelProb = bet?.model_prob ?? null;
  // CLV status: derive from clv_is_proxy or pass through edge reason.
  const clvStatus: string | null = bet
    ? bet.clv_is_proxy
      ? "INSUFFICIENT_DATA"
      : "proxy"
    : null;
  const decisionNote = bet?.reason ?? null;

  return {
    bookLines,
    bestBook,
    devig,
    decision,
    stakeUnits,
    tier,
    clvStatus,
    modelProb,
    decisionNote,
  };
}
