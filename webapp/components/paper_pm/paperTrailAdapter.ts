// paperTrailAdapter -- pure adapters: PaperTrailRow -> ExecutionTrailProps
//                      and PmTrailRow[] -> PmDisplayRow[].
//
// WS4 (paper-detail-exec-trail): mounts the orphaned ExecutionTrail under
// ExecutionDetail on /paper/[betId].
//
// WS8 (pm-trail-table-adapter): toPaperTrailRows maps PM paper trades
// (PmTrailRow from types_w12) to honest display rows:
//   - venue, units, CLV (null -> "INSUFFICIENT_DATA"), executed=false
//   - rows with missing required fields (bet_id, venue, units) are DROPPED,
//     never filled with fabricated values
//   - produces no $ / pnl / roi field anywhere
//
// HONESTY RAILS (must hold -- verified by tests):
//   - UNITS only. No $ field is ever produced.
//   - clv_status null / INSUFFICIENT_DATA propagates unchanged -- never fabricated.
//   - Book lines: taken_book + taken_decimal become a single best-marked row.
//     When taken_book or taken_decimal is absent -> bookLines = [] (honest empty).
//   - Devig: derived from model_prob when available (Shin-implied fair prob).
//     vig_pct is estimated as 1 - model_prob * taken_decimal when both present,
//     clamped to [0, 1]; null when inputs are absent.
//   - decision: "bet" when stake_units > 0 and status != "open"; else "no_bet".
//   - No market or odds are ever fabricated; absent data -> null / [].

import type { PaperTrailRow } from "@/lib/types";
import type { PmTrailRow } from "@/lib/types_w12";
import type {
  ExecutionTrailProps,
  BookLineRow,
  DevigResult,
  TierLabel,
} from "@/components/execution/ExecutionTrail";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Normalise tier string to the TierLabel union (S/A/B/C) or null. */
function toTierLabel(tier: string | null | undefined): TierLabel {
  if (!tier) return null;
  const t = tier.toUpperCase();
  if (t === "S" || t === "A" || t === "B" || t === "C") return t;
  return null;
}

/**
 * Derive a Shin-style devig result from model_prob + taken_decimal.
 *
 * fair_prob = model_prob (the model's implied probability -- unitless ratio).
 * vig_pct   = 1 - (model_prob * taken_decimal), clamped to [0, 0.5].
 *   Interpretation: the fraction of the handle the book captures as vig,
 *   estimated from the single side we took. This is an approximation for
 *   display only -- it is labeled "prob ratio -- no $" in ExecutionTrail.
 *
 * Returns null if either input is absent / non-finite.
 */
function deriveDevig(
  modelProb: number | null,
  takenDecimal: number | null,
): DevigResult | null {
  if (
    modelProb == null ||
    takenDecimal == null ||
    !Number.isFinite(modelProb) ||
    !Number.isFinite(takenDecimal) ||
    modelProb <= 0 ||
    modelProb >= 1 ||
    takenDecimal <= 1
  ) {
    return null;
  }
  const vig_pct = Math.max(0, Math.min(0.5, 1 - modelProb * takenDecimal));
  return { fair_prob: modelProb, vig_pct };
}

/**
 * Build the bookLines array from the taken book/price.
 *
 * Paper trades have a single execution venue (taken_book) with one price
 * (taken_decimal). Companion venue quotes are not stored in PaperTrailRow --
 * the schema has no multi-venue field. So we produce at most one row.
 *
 * If taken_book is absent/empty, return [] (honest empty: ExecutionTrail will
 * render the "No book quotes captured yet" state).
 */
function buildBookLines(row: PaperTrailRow): {
  bookLines: BookLineRow[];
  bestBook: string | null;
} {
  const book = row.taken_book?.trim();
  if (!book) {
    return { bookLines: [], bestBook: null };
  }

  const bl: BookLineRow = {
    book,
    decimal_odds: row.taken_decimal ?? null,
    line: row.line ?? null,
    is_pm: true,
    captured_at: row.ts ?? null,
  };

  return { bookLines: [bl], bestBook: book };
}

/**
 * Derive the CLV status string to pass to ExecutionTrail.
 *
 * Rules:
 *   - clv_unavailable=true OR clv_status="no_close" -> "INSUFFICIENT_DATA"
 *   - clv_status present -> pass through unchanged
 *   - null -> null (ExecutionTrail renders INSUFFICIENT_DATA for null too)
 *
 * Never fabricate a positive CLV status.
 */
function deriveClvStatus(row: PaperTrailRow): string | null {
  if (row.clv_unavailable || row.clv_status === "no_close") {
    return "INSUFFICIENT_DATA";
  }
  return row.clv_status ?? null;
}

/**
 * Derive the decision label for the ExecutionTrail decision trail.
 *
 * - "bet" when the trade was placed (stake_units > 0) and not open/pending.
 * - "no_bet" otherwise (open bets awaiting settlement, or zero-stake rows).
 *
 * We intentionally do NOT encode any dollar amount or ROI in this field.
 */
function deriveDecision(row: PaperTrailRow): "bet" | "no_bet" {
  if (row.stake_units != null && row.stake_units > 0) return "bet";
  return "no_bet";
}

// ---------------------------------------------------------------------------
// Main adapter
// ---------------------------------------------------------------------------

/**
 * paperRowToExecutionTrail -- maps one PaperTrailRow to ExecutionTrailProps.
 *
 * Pure function: no side effects, no network calls, no $ fields.
 * Safe to call in a render path or a test.
 */
export function paperRowToExecutionTrail(row: PaperTrailRow): ExecutionTrailProps {
  const { bookLines, bestBook } = buildBookLines(row);
  const devig = deriveDevig(row.model_prob, row.taken_decimal);
  const clvStatus = deriveClvStatus(row);
  const decision = deriveDecision(row);
  const tier = toTierLabel(row.tier);

  // decisionNote: surface clv_note when available (honest context, no $).
  const decisionNote: string | null = row.clv_note ?? null;

  return {
    bookLines,
    bestBook,
    devig,
    decision,
    stakeUnits: row.stake_units ?? null,
    tier,
    clvStatus,
    modelProb: row.model_prob ?? null,
    decisionNote,
  };
}

// ---------------------------------------------------------------------------
// WS8: PM trail display row
// ---------------------------------------------------------------------------

/**
 * PmDisplayRow -- the honest display shape for one PM paper trade.
 *
 * HONESTY RAILS:
 *   - units is a plain number (never a $ string).
 *   - clvDisplay is the CLV % as a number, OR the string "INSUFFICIENT_DATA"
 *     when no real close exists. It is NEVER null (callers don't need a null
 *     check -- they get an explicit sentinel instead of a missing value).
 *   - executed is ALWAYS false (paper-only).
 *   - No pnl/roi/dollar field is ever present on this type.
 *   - dropped=true marks rows that were missing required fields; they are
 *     included in the output only for diagnostic purposes and must NOT be
 *     rendered as valid trades.
 */
export type PmDisplayRow = {
  bet_id: string;
  venue: string;
  market_id: string;
  model_prob: number | null;
  confidence: number | null;
  units: number;
  tier: TierLabel;
  result: string | null;
  /** CLV as a probability ratio, or "INSUFFICIENT_DATA" when absent/unavailable. */
  clvDisplay: number | "INSUFFICIENT_DATA";
  clv_is_proxy: boolean;
  clv_status: string | null;
  price_taken: number | null;
  ts: string;
  executed: false; // ALWAYS false (paper-only)
  dropped: false;
};

/** Shape returned when a required field is absent -- row is invalid/dropped. */
export type PmDroppedRow = {
  dropped: true;
  reason: string;
  raw: Partial<PmTrailRow>;
};

export type PmMappedRow = PmDisplayRow | PmDroppedRow;

/**
 * Resolve the CLV display value for a PM trade.
 *
 * Rules:
 *   - clv_status="INSUFFICIENT_DATA" OR clv is null -> "INSUFFICIENT_DATA"
 *   - clv is a finite number -> pass through as-is (probability ratio)
 *   - Never coerce null to 0 or any fabricated numeric value.
 */
function resolveClvDisplay(row: PmTrailRow): number | "INSUFFICIENT_DATA" {
  if (
    row.clv_status === "INSUFFICIENT_DATA" ||
    row.clv == null ||
    !Number.isFinite(row.clv)
  ) {
    return "INSUFFICIENT_DATA";
  }
  return row.clv;
}

/**
 * toPaperTrailRows -- maps PmTrailRow[] from the API to PmMappedRow[].
 *
 * Rows that are missing required fields (bet_id, venue, units) are returned
 * as PmDroppedRow with a reason string. They are NEVER filled with fabricated
 * values and MUST NOT be rendered as valid trades.
 *
 * Pure function: no side effects, no network calls, no $ fields.
 */
export function toPaperTrailRows(trades: PmTrailRow[]): PmMappedRow[] {
  return trades.map((row): PmMappedRow => {
    // Required field validation: drop rows that cannot be rendered honestly.
    if (!row.bet_id || !row.bet_id.trim()) {
      return { dropped: true, reason: "missing bet_id", raw: row };
    }
    if (!row.venue || !row.venue.trim()) {
      return { dropped: true, reason: "missing venue", raw: row };
    }
    if (row.units == null || !Number.isFinite(row.units)) {
      return { dropped: true, reason: "missing or non-finite units", raw: row };
    }

    return {
      bet_id: row.bet_id,
      venue: row.venue,
      market_id: row.market_id,
      model_prob: Number.isFinite(row.model_prob) ? row.model_prob : null,
      confidence: Number.isFinite(row.confidence) ? row.confidence : null,
      units: row.units,
      tier: toTierLabel(row.tier),
      result: row.result ?? null,
      clvDisplay: resolveClvDisplay(row),
      clv_is_proxy: row.clv_is_proxy,
      clv_status: row.clv_status ?? null,
      price_taken: row.price_taken ?? null,
      ts: row.ts,
      executed: false,
      dropped: false,
    };
  });
}
