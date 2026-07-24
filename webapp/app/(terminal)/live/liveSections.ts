// liveSections.ts -- pure section-classifier for the /live page.
//
// Takes a flat list of games (from predict + bestbets envelopes) and sorts
// them into three buckets: LIVE (in-progress), PREGAME (today, not started),
// DONE (settled/final). No network calls; no React; fully testable.
//
// HONESTY RAILS: UNITS / probability only. No $ field is produced here.
// Stale-never-green: a game is only "live" when the live state explicitly
// signals it. Missing/absent state defaults to "pregame" (safe side).

import type { PredictRecord } from "@/lib/p5api";
import type { BestBet, GameEdge, LiveState, ResultRow } from "@/lib/types";

// Re-export the shared LiveState type so components can import from one place.
export type { LiveState };

export type SectionKey = "LIVE" | "PREGAME" | "DONE";

// Final score surfaced on DONE cards -- real reported scores or nothing.
export interface FinalScore {
  home_score: number;
  away_score: number;
  // Human-readable label e.g. "Final" from status_detail.
  label: string;
}

// Model's pregame call on the winning side (probability only, no $).
export interface ModelCall {
  // Which team the model favoured: "home" | "away" | null (no prob available).
  favoured: "home" | "away" | null;
  // Probability assigned to the favoured team.
  prob: number | null;
  // Whether the favoured team actually won (null = cannot determine).
  correct: boolean | null;
}

// Model-vs-market probability pair for the paired amber/blue bar (Direction A
// spec). Real data only -- taken from the best_bets envelope's leading
// candidate, never fabricated. null when no market-priced candidate exists.
export interface EdgeProb {
  marketType: string;
  side: string;
  modelProb: number;
  marketProb: number;
}

// A single enriched row consumed by LiveGameRow.
export interface LiveGameEntry {
  game_id: string;
  sport: string;
  home: string;
  away: string;
  tipoff: string | null;
  // Coherent win-prob (home side) -- null when absent.
  homeWinProb: number | null;
  // Raw live state from the bestbets envelope (null when not live).
  liveState: LiveState | null;
  // Section derived by classifySection.
  section: SectionKey;
  // DONE cards only: real final scores (null/absent for LIVE/PREGAME).
  finalScore?: FinalScore | null;
  // DONE cards only: the model's pregame call vs the actual outcome.
  modelCall?: ModelCall | null;
  // Model-vs-market pair for the paired bar, when a priced candidate exists.
  edgeProb?: EdgeProb | null;
}

/**
 * Classify a single game into LIVE / PREGAME / DONE.
 *
 * Decision tree (in priority order):
 *   1. live.status === "live" -> LIVE
 *   2. live.state === "post" or game.status in {"done","settled","final"} -> DONE
 *   3. otherwise -> PREGAME (today or unknown -- safe default)
 */
export function classifySection(
  gameStatus: string | undefined,
  liveState: LiveState | null | undefined,
): SectionKey {
  // Check live state first (most specific).
  if (liveState) {
    if (liveState.status === "live") return "LIVE";
    const s = liveState.state ?? liveState.status ?? "";
    if (s === "post" || s === "final" || s === "done") return "DONE";
  }
  // Check envelope-level status.
  const gs = (gameStatus ?? "").toLowerCase();
  if (gs === "done" || gs === "settled" || gs === "final") return "DONE";
  return "PREGAME";
}

/**
 * Extract the home-win probability from a PredictRecord.
 * Returns null when absent rather than inventing a number.
 */
export function extractHomeWinProb(rec: PredictRecord): number | null {
  const p = rec.pregame_probs ?? {};
  // Prefer home_ml; fall back to any "home"-keyed entry.
  if (typeof p["home_ml"] === "number" && Number.isFinite(p["home_ml"])) {
    return p["home_ml"];
  }
  for (const [k, v] of Object.entries(p)) {
    if (k.includes("home") && typeof v === "number" && Number.isFinite(v)) {
      return v;
    }
  }
  return null;
}

/**
 * Pull the leading priced candidate (model_prob + market_prob) off a GameEdge
 * for the paired model-vs-market bar. Returns null when absent -- never
 * invents a market number.
 */
export function extractEdgeProb(edge: GameEdge | null | undefined): EdgeProb | null {
  const candidates: BestBet[] = edge?.best_bets ?? edge?.candidates ?? [];
  const pick = candidates.find(
    (c) => typeof c.model_prob === "number" && typeof c.market_prob === "number",
  );
  if (!pick) return null;
  return {
    marketType: pick.market_type,
    side: pick.side,
    modelProb: pick.model_prob,
    marketProb: pick.market_prob,
  };
}

/**
 * Build a LiveGameEntry for one game by merging a PredictRecord + an optional
 * GameEdge (which carries the live state from the bestbets envelope).
 */
export function buildEntry(
  rec: PredictRecord,
  edge: GameEdge | null | undefined,
): LiveGameEntry {
  const liveState: LiveState | null =
    (edge?.live as LiveState | null | undefined) ?? null;
  const section = classifySection(edge?.status, liveState);
  return {
    game_id: rec.game_id,
    sport: rec.sport ?? "nba",
    home: rec.home,
    away: rec.away,
    tipoff: rec.tipoff ?? null,
    homeWinProb: extractHomeWinProb(rec),
    liveState,
    section,
    finalScore: null,
    modelCall: null,
    edgeProb: extractEdgeProb(edge),
  };
}

/**
 * Build a DONE LiveGameEntry from a /api/results/{sport} ResultRow.
 * An optional PredictRecord provides the model's pregame call so we can show
 * what the model said before the game vs what actually happened.
 * Returns null when the row is not completed (not yet settled).
 */
export function buildDoneEntryFromResult(
  row: ResultRow,
  sport: string,
  predRec: PredictRecord | null | undefined,
): LiveGameEntry | null {
  // Only surface completed (settled) games in the DONE section.
  if (!row.completed) return null;

  const finalScore: FinalScore | null =
    row.home_score != null && row.away_score != null
      ? {
          home_score: row.home_score,
          away_score: row.away_score,
          label: row.status_detail ?? "Final",
        }
      : null;

  let modelCall: ModelCall | null = null;
  if (predRec) {
    const homeProb = extractHomeWinProb(predRec);
    if (homeProb != null) {
      const awayProb = 1 - homeProb;
      const favoured: "home" | "away" = homeProb >= awayProb ? "home" : "away";
      const prob = favoured === "home" ? homeProb : awayProb;
      let correct: boolean | null = null;
      if (finalScore != null) {
        const homeWon = finalScore.home_score > finalScore.away_score;
        correct = favoured === "home" ? homeWon : !homeWon;
      }
      modelCall = { favoured, prob, correct };
    }
  }

  return {
    game_id: row.game_id,
    sport,
    home: row.home ?? "",
    away: row.away ?? "",
    tipoff: row.commence_time ?? null,
    homeWinProb: predRec ? extractHomeWinProb(predRec) : null,
    liveState: null,
    section: "DONE",
    finalScore,
    modelCall,
    edgeProb: null,
  };
}

/** Classify a flat array of entries into the three section buckets. */
export function partitionEntries(entries: LiveGameEntry[]): {
  live: LiveGameEntry[];
  pregame: LiveGameEntry[];
  done: LiveGameEntry[];
} {
  const live: LiveGameEntry[] = [];
  const pregame: LiveGameEntry[] = [];
  const done: LiveGameEntry[] = [];
  for (const e of entries) {
    if (e.section === "LIVE") live.push(e);
    else if (e.section === "DONE") done.push(e);
    else pregame.push(e);
  }
  return { live, pregame, done };
}
