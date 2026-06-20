// riskUtils.ts -- pure helpers that turn a per-game GameEdge into the honest,
// unit-space RISK rows the /risk page renders. Kept separate from the components
// so the honesty invariants are unit-testable without a DOM.
//
// HONESTY RAILS: UNITS / probability only -- NO $ field is ever produced here.
// edge_claimed is always false; vs_close is UNPROVEN. A below-floor pick is an
// honest NO BET with a reason, never a fabricated tier/stake. A missing prob is
// null (rendered as a dash), never invented.

import type { BestBet, GameEdge } from "@/lib/api";

// One per-bet RISK row: the descriptive size + the model-vs-close picture.
export interface BetRiskRow {
  gameId: string;
  matchup: string;        // "AWAY @ HOME" or the game_id when absent
  market: string;         // e.g. "moneyline home"
  tier: string | null;    // S/A/B/C or null (no_bet)
  decision: "bet" | "no_bet";
  stakeUnits: number | null;  // capped quarter-Kelly + flat, UNITS only
  flatUnit: number | null;
  kellyUnits: number | null;  // capped quarter-Kelly fraction, in UNITS
  modelProb: number | null;   // P(side) in [0,1]
  devigClose: number | null;  // devigged closing/market prob in [0,1]
  ev: number | null;          // probability-space EV per unit
  reason: string | null;      // honest no-bet / floor reason when present
}

function matchupLabel(edge: GameEdge): string {
  const a = edge.away || "";
  const h = edge.home || "";
  if (a && h) return `${a} @ ${h}`;
  return edge.game_id || "(game)";
}

function num(x: unknown): number | null {
  return typeof x === "number" && Number.isFinite(x) ? x : null;
}

/** Build the per-bet risk row from one BestBet candidate. NO $ ever. */
export function betRiskRow(edge: GameEdge, b: BestBet): BetRiskRow {
  const decision: "bet" | "no_bet" = b.decision === "bet" ? "bet" : "no_bet";
  return {
    gameId: edge.game_id || "",
    matchup: matchupLabel(edge),
    market: `${b.market_type} ${b.side}`.trim(),
    tier: b.tier ?? null,
    decision,
    stakeUnits: decision === "bet" ? num(b.stake_units) : null,
    flatUnit: decision === "bet" ? num(b.flat_unit) : null,
    kellyUnits: decision === "bet" ? num(b.kelly_units) : null,
    modelProb: num(b.model_prob),
    devigClose: num(b.market_prob),
    ev: num(b.ev),
    reason: b.reason ?? null,
  };
}

/**
 * Collect the QUALIFYING (decision='bet') risk rows from a sport's games, sorted
 * by stake (largest first). When no candidate clears a tier floor this returns an
 * empty list -- the page renders an honest empty state, never a fabricated bet.
 */
export function qualifyingRows(games: GameEdge[]): BetRiskRow[] {
  const out: BetRiskRow[] = [];
  for (const g of games || []) {
    const cands = g.best_bets || g.candidates || [];
    for (const b of cands) {
      if (b.decision !== "bet") continue;
      out.push(betRiskRow(g, b));
    }
  }
  out.sort((x, y) => (y.stakeUnits ?? 0) - (x.stakeUnits ?? 0));
  return out;
}

/** Format a probability in [0,1] as a percent string, or a dash when absent. */
export function pctOrDash(p: number | null, dash = "--"): string {
  if (p == null) return dash;
  return `${(p * 100).toFixed(1)}%`;
}

/** Format a unit count, or a dash when absent. */
export function unitsOrDash(u: number | null, dash = "--"): string {
  if (u == null) return dash;
  return `${u.toFixed(2)}u`;
}

// Tier EV floors (probability-space EV per 1 unit), mirrored from
// frontend.exec_decision.TIER_FLOORS for the policy panel. Display-only.
export const TIER_FLOORS: Array<{ tier: string; floor: number; note: string }> = [
  { tier: "A", floor: 0.08, note: "strongest -- clears the highest EV floor" },
  { tier: "B", floor: 0.04, note: "middle confidence band" },
  { tier: "C", floor: 0.02, note: "weakest tier that still bets" },
];
export const PROXY_FLOOR_BUMP = 0.01;
