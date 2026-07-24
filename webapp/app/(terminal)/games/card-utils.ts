// card-utils.ts -- pure helpers that turn a PredictRecord + per-game GameEdge
// into the small, honest summary a GameCard renders. Kept separate from the
// component so the honesty invariants are unit-testable without a DOM.
//
// HONESTY RAILS: UNITS / probability only -- NO $ field is ever produced here.
// edge_claimed is always false (we never derive a dollar/ROI number). A missing
// price/prob is null (rendered as a dash), NEVER a fabricated number. When no
// candidate clears the tier floor the chip is an honest NO BET, not invented.

import type { PredictRecord, BestBet, GameEdge } from "@/lib/p5api";
import { isUnavailable } from "@/lib/p5api";
import type { Slate, SlateGame } from "@/lib/board";

// The single coherent headline pick for a card: the highest-probability side of
// the anchor (moneyline) market, in probability terms only. No $.
export interface CoherentPick {
  side: string; // "home" | "away" | "draw"
  teamLabel: string; // the team name for that side (or the raw side key)
  prob: number | null; // P(side) in [0,1], or null if not present
}

// The best-bet chip: a tier + units stake, or an honest NO_BET. Never a $.
export interface BestBetChip {
  decision: "bet" | "no_bet"; // never anything else
  tier: string | null;
  stakeUnits: number | null; // units only; null when no_bet
  market: string | null; // e.g. "moneyline home"
}

/** The coherent headline pick from the pregame anchor probabilities. */
export function coherentPick(rec: PredictRecord): CoherentPick {
  const probs = rec.pregame_probs || {};
  // Anchor on the moneyline tri(home_ml / away_ml / draw); fall back to the
  // single largest probability key. Never invent a probability.
  const entries = Object.entries(probs).filter(
    ([, v]) => typeof v === "number" && Number.isFinite(v),
  ) as Array<[string, number]>;
  if (entries.length === 0) {
    return { side: "?", teamLabel: rec.home || "?", prob: null };
  }
  let [bestKey, bestVal] = entries[0];
  for (const [k, v] of entries) if (v > bestVal) [bestKey, bestVal] = [k, v];
  const side = bestKey.replace(/_ml$/, "");
  const teamLabel =
    side === "home" ? rec.home : side === "away" ? rec.away : side;
  return { side, teamLabel: teamLabel || side, prob: bestVal };
}

/** A few key markets (anchor first), de-duplicated by market_type+side. */
export function keyMarkets(rec: PredictRecord, limit = 3) {
  const seen = new Set<string>();
  const out: typeof rec.markets = [];
  for (const m of rec.markets || []) {
    const k = `${m.market_type}|${m.side}|${m.line ?? ""}`;
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(m);
    if (out.length >= limit) break;
  }
  return out;
}

/**
 * Pick the single best-bet chip for a card from the per-game GameEdge.
 * - If the edge is unavailable -> honest no_bet (we do not fabricate a tier).
 * - Prefer a real 'bet' decision (highest units); else honest no_bet.
 * Never returns a $ figure -- stakeUnits is units, or null.
 */
export function bestBetChip(edge: GameEdge | null | undefined): BestBetChip {
  const NONE: BestBetChip = {
    decision: "no_bet",
    tier: null,
    stakeUnits: null,
    market: null,
  };
  if (!edge || isUnavailable(edge) || edge.status === "unavailable") return NONE;
  const bets: BestBet[] = (edge.best_bets || []).filter(
    (b) => b.decision === "bet",
  );
  if (bets.length === 0) return NONE;
  let top = bets[0];
  for (const b of bets) if ((b.stake_units || 0) > (top.stake_units || 0)) top = b;
  return {
    decision: "bet",
    tier: top.tier ?? null,
    stakeUnits: typeof top.stake_units === "number" ? top.stake_units : null,
    market: `${top.market_type} ${top.side}`,
  };
}

// Display sports in a stable order; soccer_intl rendered as a distinct slate.
export const GAME_SPORTS = [
  "nba",
  "mlb",
  "soccer",
  "soccer_intl",
  "tennis",
] as const;

export function sportLabel(s: string): string {
  if (s === "soccer_intl") return "SOCCER (INTL)";
  return s.toUpperCase();
}

/**
 * Match a predict-envelope record to its /api/board/slate row by team pair.
 * The two services can use different game_id schemes, so team names are the
 * only reliable join key. No match -> null (honest: never fabricate a price).
 * ponytail: best-effort string match, not a canonical team-id join; upgrade
 * if the two services ever disagree on team-name spelling.
 */
export function matchSlateGame(
  slate: Slate | null | undefined,
  rec: Pick<PredictRecord, "home" | "away">,
): SlateGame | null {
  if (!slate?.games?.length) return null;
  const key = (away: string, home: string) =>
    `${away.trim().toUpperCase()}|${home.trim().toUpperCase()}`;
  const want = key(rec.away, rec.home);
  return slate.games.find((g) => key(g.away, g.home) === want) ?? null;
}
