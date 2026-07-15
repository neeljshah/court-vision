"use client";
// BestBetsBoardHelpers.tsx -- pure helpers extracted from BestBetsBoard.tsx to
// keep that file under the 300-LOC rail (repo invariant).
//
// Exports:
//   Types:   SportBoardResult, BoardMap, FetchResult
//   Pure fns: classifyStatus, cardToBetCardData, sortCards
//   Async fn: fetchAllSports
//   Util fn:  extractFetchResult
//   Component: SportSectionEmpty

import { api, isUnavailable, SPORTS } from "@/lib/p5api";
import type { BestBetsBoard as BestBetsBoardType, BestBetsCard } from "@/lib/p5api";
import type { BetCardData } from "./BetCard";
import type { BookOddsEntry } from "./BookShoppingRow";
import type { BetStatus } from "./StatusTabs";
import type { SortKey } from "./SortControls";
import {
  shouldSuppressBet,
  type SuppressReason,
} from "./BestBetsCardGuards";

// POST/FINAL statuses: cards excluded from the bets grid (game already over).
const POST_STATUSES = new Set(["post", "final"]);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// skipped: cards excluded because status is post/final.
export type SportBoardResult = {
  board: BestBetsBoardType | null;
  skipped: BestBetsCard[];
};
export type BoardMap = Record<string, SportBoardResult>;
export type FetchResult = {
  boards: BoardMap;
  unavailableReasons: Record<string, string>;
};

// ---------------------------------------------------------------------------
// classifyStatus -- map board card status to the three display buckets.
// ---------------------------------------------------------------------------
export function classifyStatus(raw: string): BetStatus {
  if (raw === "live") return "live";
  if (raw === "done" || raw === "settled" || raw === "post" || raw === "final") return "done";
  return "pregame";
}

// ---------------------------------------------------------------------------
// cardToBetCardData -- map one BestBetsCard -> BetCardData for BetCard.
// ---------------------------------------------------------------------------
export function cardToBetCardData(
  card: BestBetsCard,
  suppressReason: SuppressReason = null,
): BetCardData {
  const clvNum = card.clv?.clv_pct ?? null;
  const bestEntry: BookOddsEntry = {
    book: card.best_book,
    odds: card.best_odds,
    line: null,
    is_best: true,
  };
  const allBooks: BookOddsEntry[] = (card.all_books ?? []).map((b) => ({
    book: b.book,
    odds: b.odds,
    line: b.line,
    is_best: false,
  }));
  // best_odds may be 0/undefined for model-only props -- guard the best pill so
  // we never fabricate a price entry.
  const hasBest = card.best_book != null && card.best_odds != null;
  return {
    game_id: card.game_id,
    sport: card.sport,
    matchup: card.matchup,
    market_type: card.market_type,
    side: card.side,
    model_prob: card.model_prob,
    market_prob: card.market_prob,
    best_book: card.best_book,
    best_odds: card.best_odds,
    all_books: allBooks.length > 0 ? allBooks : hasBest ? [bestEntry] : [],
    // books[] line-shopping array surfaced verbatim (price/line/as_of/fresh/is_pm).
    books: card.books ?? undefined,
    edge_vs_market: card.edge_vs_market,
    units: card.units,
    tier: card.tier,
    confidence: card.confidence,
    clv: clvNum,
    clv_is_proxy: card.clv_is_proxy,
    status: classifyStatus(card.status),
    line: card.line ?? null,
    tipoff_utc: card.tipoff_utc ?? null,
    // prop fields
    prop_player: card.prop_player ?? null,
    prop_stat: card.prop_stat ?? null,
    proj: card.proj ?? null,
    model_only: card.model_only ?? false,
    honest_note: card.honest_note ?? null,
    suppress_reason: suppressReason,
  };
}

// ---------------------------------------------------------------------------
// sortCards -- sort BetCardData[] by tier then confidence descending.
// ---------------------------------------------------------------------------
export function sortCards(cards: BetCardData[], key: SortKey): BetCardData[] {
  return [...cards].sort((a, b) => {
    if (key === "tier") {
      const order: Record<string, number> = { S: 0, A: 1, B: 2, C: 3 };
      const ta = order[a.tier ?? "C"] ?? 3;
      const tb = order[b.tier ?? "C"] ?? 3;
      if (ta !== tb) return ta - tb;
    }
    return b.confidence - a.confidence;
  });
}

// ---------------------------------------------------------------------------
// fetchAllSports -- single fetcher for useLiveData. Parallel per sport.
// Uses /api/bestbets/board?sport=<sport>.  Returns a never-empty FetchResult.
// ---------------------------------------------------------------------------
export async function fetchAllSports(signal: AbortSignal): Promise<FetchResult> {
  const results = await Promise.allSettled(
    SPORTS.map(async (sport) => ({
      sport,
      r: await api.bestbetsBoard({ sport }, signal),
    })),
  );
  const boards: BoardMap = {};
  const unavailableReasons: Record<string, string> = {};

  for (const res of results) {
    if (res.status !== "fulfilled") continue;
    const { sport, r } = res.value;
    if (isUnavailable(r)) {
      boards[sport] = { board: null, skipped: [] };
      const reason = (r as { reason?: string }).reason;
      if (reason) unavailableReasons[sport] = reason;
    } else {
      const board = r as BestBetsBoardType;
      const eligible: BestBetsCard[] = [];
      const skipped: BestBetsCard[] = [];
      for (const card of board.cards ?? []) {
        if (POST_STATUSES.has(card.status)) {
          skipped.push(card);
        } else {
          eligible.push(card);
        }
      }
      boards[sport] = { board: { ...board, cards: eligible }, skipped };
      if (board.reason) unavailableReasons[sport] = board.reason;
      if ((board.count === 0 || eligible.length === 0) && board.honest_note) {
        unavailableReasons[sport] = board.honest_note;
      }
    }
  }
  return { boards, unavailableReasons };
}

// ---------------------------------------------------------------------------
// extractFetchResult -- tolerates both the current FetchResult shape and the
// legacy EnvelopeMap shape (used by existing tests that inject data directly).
// ---------------------------------------------------------------------------
export function extractFetchResult(
  result: FetchResult | Record<string, unknown> | null,
): { boards: BoardMap | null; unavailableReasons: Record<string, string> } {
  if (!result) return { boards: null, unavailableReasons: {} };
  if ("boards" in result && result.boards != null && typeof result.boards === "object") {
    return {
      boards: result.boards as BoardMap,
      unavailableReasons: (result.unavailableReasons as Record<string, string>) ?? {},
    };
  }
  // Legacy test shape: treat top-level sport keys as an EnvelopeMap.
  const legacyBoards: BoardMap = {};
  for (const [sport, val] of Object.entries(result)) {
    if (val == null) {
      legacyBoards[sport] = { board: null, skipped: [] };
    } else if (typeof val === "object" && "cards" in (val as object)) {
      legacyBoards[sport] = { board: val as BestBetsBoardType, skipped: [] };
    } else {
      legacyBoards[sport] = { board: null, skipped: [] };
    }
  }
  return { boards: legacyBoards, unavailableReasons: {} };
}

// ---------------------------------------------------------------------------
// SportSectionEmpty -- per-sport honest "none right now" inside the tab panel.
// Rendered when a sport has 0 cards for the current status tab.
// ---------------------------------------------------------------------------
export function SportSectionEmpty({ sport, reason }: { sport: string; reason?: string | null }) {
  const label = reason
    ? `none right now -- ${reason}`
    : "No qualifying bets -- all games started, offseason, or below tier floor. Matching the efficient close is a calibration success.";
  return (
    <div
      role="status"
      aria-label={`${sport.toUpperCase()}: none right now`}
      data-testid={`sport-section-empty-${sport}`}
      className="border border-border bg-surface-2 px-3 py-3"
    >
      <span className="microlabel">
        {sport.toUpperCase()}
      </span>
      <p className="mt-0.5 font-data text-[10px] text-faint">{label}</p>
    </div>
  );
}

// Re-export shouldSuppressBet so BoardMap consumers can keep a single import path.
export { shouldSuppressBet };
