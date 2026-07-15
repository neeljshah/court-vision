"use client";
// /bets/[sport] -- sport-filtered best-bets board. Fetches GET
// /api/bestbets/board?sport=<sport> via api.bestbetsBoard and renders ranked
// calibrated divergence cards (tier / confidence / units / CLV). Uses
// useLiveData for auto-refresh (no bespoke setInterval).
//
// HONESTY RAILS: UNITS only (NO $); ranked by tier then confidence (calibrated
// divergence + signal proxy); CLV null -> INSUFFICIENT_DATA (never greened);
// stale-never-green (amber when generated_at > 15m old); honest empty state when
// 0 cards clear the tier floor; real money default-DENY; edge_claimed always
// false (never a profit/ROI claim).

import { useParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import { api, isUnavailable } from "@/lib/p5api";
import type { BestBetsBoard, BestBetsCard } from "@/lib/p5api";
import { HONEST_DISCLAIMER } from "@/lib/api";
import { useLiveData } from "@/lib/useLiveData";
import { Badge, timeAgoIso } from "@/components/p6/Primitives";
import { freshnessStatus } from "@/components/p6/LiveLinesPanel";
import { BetCard, type BetCardData } from "@/components/bets/BetCard";
import { Panel, PanelHead } from "@/components/ui/terminal";

const AUTO_REFRESH_MS = 120_000;

// Map BestBetsCard -> BetCardData (the shape BetCard consumes).
function cardToBetCardData(c: BestBetsCard): BetCardData {
  const allBooks = (c.all_books ?? []).map((b) => ({
    book: b.book,
    odds: b.odds,
    line: b.line ?? null,
    is_best: b.book === c.best_book,
  }));
  return {
    game_id: c.game_id,
    sport: c.sport,
    matchup: c.matchup,
    market_type: c.market_type,
    side: c.side,
    model_prob: c.model_prob,
    market_prob: c.market_prob,
    best_book: c.best_book,
    best_odds: c.best_odds,
    all_books: allBooks,
    edge_vs_market: c.edge_vs_market,
    units: c.units,
    tier: c.tier,
    confidence: c.confidence,
    clv: c.clv?.clv_pct ?? null,
    clv_is_proxy: c.clv?.clv_is_proxy ?? c.clv_is_proxy,
    status: (c.status as BetCardData["status"]) ?? "pregame",
    // Pass line/tipoff/prop fields through so prop cards render (not empty).
    line: c.line ?? null,
    tipoff_utc: c.tipoff_utc ?? null,
    prop_player: c.prop_player ?? null,
    prop_stat: c.prop_stat ?? null,
    proj: c.proj ?? null,
    model_only: c.model_only,
    honest_note: c.honest_note ?? null,
    books: c.books,
  };
}

// AgeBadge: amber when stale (> 15m); slate otherwise. NEVER green.
function AgeBadge({ asOf }: { asOf: string | null }) {
  if (!asOf) {
    return (
      <Badge tone="slate">
        <span className="font-mono text-[10px]">data age: checking</span>
      </Badge>
    );
  }
  const stale = freshnessStatus(asOf) === "stale";
  const age = timeAgoIso(asOf);
  return (
    <span title={`data as-of: ${asOf}`} data-testid="sport-age-badge">
      <Badge tone={stale ? "amber" : "slate"}>
        <span className="font-mono text-[10px]">
          {stale ? `data ${age} -- aging` : `data ${age}`}
        </span>
      </Badge>
    </span>
  );
}

// EmptyReason: no_slate=no games today; suppressed=0 cleared tier floor;
// unavailable=fetch error; empty=0 cards no context. deriveEmptyReason reads
// board.reason / board.honest_note to classify.
type EmptyReason = "no_slate" | "suppressed" | "unavailable" | "empty";

function deriveEmptyReason(board: BestBetsBoard | null, fetchError: string | null): EmptyReason {
  if (fetchError && !board) return "unavailable";
  if (!board) return "empty";
  const hint = (board.reason ?? board.honest_note ?? "").toLowerCase();
  if (hint.includes("no game") || hint.includes("no slate") || hint.includes("offseason") || hint.includes("off season")) return "no_slate";
  // count > 0 = games evaluated; 0 cards = all suppressed by tier floor.
  if (board.cards.length === 0 && board.count != null && board.count > 0) return "suppressed";
  return "empty";
}

const REASON_COPY: Record<EmptyReason, { headline: string; detail: string }> = {
  no_slate: {
    headline: "No calibrated bets right now -- no games on slate",
    detail: "No scheduled games for this sport today. No cards fabricated to fill the space. Check back when the slate is live.",
  },
  suppressed: {
    headline: "No calibrated bets right now -- all below tier floor",
    detail: "Games evaluated but 0 cleared the confidence + tier floor. Model matching the efficient close is a calibration success. No fabricated cards shown.",
  },
  unavailable: {
    headline: "Board unavailable -- data could not be loaded",
    detail: "Best-bets service unreachable or returned an error. Retry shortly. No fabricated cards shown while data is absent.",
  },
  empty: {
    headline: "No calibrated bets right now",
    detail: "Cards only shown when a real calibrated divergence clears the tier floor -- never fabricated.",
  },
};

// EmptyState: honest 0-card board; never blank and never a fake card.
function EmptyState({ sport, reason, apiReason, apiNote }: {
  sport: string; reason: EmptyReason; apiReason?: string | null; apiNote?: string | null;
}) {
  const copy = REASON_COPY[reason];
  return (
    <div
      className="border border-border bg-surface-2 px-6 py-12 text-center"
      data-testid="sport-empty-state"
      data-reason={reason}
    >
      <p
        className="font-data text-sm text-foreground"
        data-testid="sport-empty-headline"
      >
        {copy.headline}
      </p>
      <p className="mt-2 text-[11px] text-muted-foreground">
        {sport.toUpperCase()}: {copy.detail}
      </p>
      {/* Surface the raw API reason/note when present so nothing is hidden */}
      {(apiReason || apiNote) && (
        <p
          className="mt-3 font-data text-[10px] text-faint"
          data-testid="sport-empty-api-note"
        >
          API: {apiReason ?? apiNote}
        </p>
      )}
      <p className="mt-4 font-data text-[10px] text-faint">
        CLV may show INSUFFICIENT_DATA when no live in-play prices exist.
        Real money is default-DENY.
      </p>
    </div>
  );
}

// SportBetsBoard -- the sport-filtered board using useLiveData.
function SportBetsBoard({ sport }: { sport: string }) {
  const fetcher = useCallback(
    (signal: AbortSignal) => api.bestbetsBoard({ sport }, signal),
    [sport],
  );

  const { data, ageSec: _ageSec, isStale, error, isLoading } = useLiveData<
    BestBetsBoard
  >(fetcher, { intervalMs: AUTO_REFRESH_MS, staleAfterSec: 15 * 60, cacheKey: `bets:${sport}` });

  const asOf = data && !isUnavailable(data) ? (data as BestBetsBoard).generated_at : null;

  // Sort: tier (S=0,A=1,B=2,C=3) then confidence desc.
  const cards: BetCardData[] = useMemo(() => {
    if (!data || isUnavailable(data)) return [];
    const board = data as BestBetsBoard;
    const raw: BestBetsCard[] = board.cards ?? [];
    const order: Record<string, number> = { S: 0, A: 1, B: 2, C: 3 };
    return [...raw]
      .sort((a, b) => {
        const ta = order[a.tier ?? "C"] ?? 3;
        const tb = order[b.tier ?? "C"] ?? 3;
        if (ta !== tb) return ta - tb;
        return b.confidence - a.confidence;
      })
      .map(cardToBetCardData);
  }, [data]);

  const anyFetched = data !== null;
  const showError = error !== null && !anyFetched;

  // Derive the honest empty-state reason from board metadata + fetch error.
  const board = data && !isUnavailable(data) ? (data as BestBetsBoard) : null;
  const emptyReason = deriveEmptyReason(board, error);

  const asOfStamp = useMemo(() => {
    if (!asOf) return null;
    const t = Date.parse(asOf);
    if (Number.isNaN(t)) return null;
    return new Date(t).toLocaleTimeString("en-US", { hour12: false });
  }, [asOf]);

  return (
    <Panel>
      <PanelHead
        title={`${sport.toUpperCase()} best bets board`}
        asOf={asOfStamp}
        stale={isStale}
        right={<AgeBadge asOf={asOf ?? null} />}
      />
      <section aria-label={`${sport.toUpperCase()} best bets board`} className="flex flex-col gap-4 p-4">
      {isStale && anyFetched && error && (
        <span className="font-data text-[10px] text-stale">
          poll failed -- showing last-good data
        </span>
      )}

      {/* Board content */}
      {isLoading && !anyFetched ? (
        <div
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          data-testid="sport-board-loading"
        >
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton-shimmer h-64" />
          ))}
        </div>
      ) : showError ? (
        <EmptyState
          sport={sport}
          reason="unavailable"
          apiReason={error ?? "Could not load best bets."}
        />
      ) : cards.length === 0 ? (
        <EmptyState
          sport={sport}
          reason={emptyReason}
          apiReason={board?.reason ?? null}
          apiNote={board?.honest_note ?? null}
        />
      ) : (
        <div
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          role="list"
          aria-label={`${sport.toUpperCase()} best bets -- ranked calibrated divergence cards`}
          data-testid="sport-cards-grid"
        >
          {cards.map((card, i) => (
            <div
              key={`${card.game_id}-${card.market_type}-${card.side}-${i}`}
              role="listitem"
            >
              <BetCard card={card} />
            </div>
          ))}
        </div>
      )}
      </section>
    </Panel>
  );
}

// Page component -- the /bets/[sport] route.
export default function SportBetsPage() {
  const params = useParams();
  const sport = typeof params?.sport === "string" ? params.sport : "nba";

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          {sport.toUpperCase()} Best Bets{" "}
          <span className="font-data text-sm text-muted-foreground">
            ranked calibrated divergence -- units only, no edge claimed
          </span>
        </h1>
        <span className="font-data text-[11px] text-muted-foreground">
          paper only -- no $
        </span>
      </header>

      {/* Honesty banner */}
      <Panel className="px-4 py-3 text-[12px] text-muted-foreground">
        <span className="microlabel mr-2">units only -- no dollars</span>
        <span>
          Cards ranked by <strong className="text-foreground">calibrated model-vs-market divergence</strong>{" "}
          and tier. This is <span className="font-data">CALIBRATION</span>, not a
          profit claim. Real money is{" "}
          <span className="font-data uppercase text-foreground">DENY</span> (paper
          only). CLV may show{" "}
          <span className="font-data">INSUFFICIENT_DATA</span> when no live
          in-play prices exist.
        </span>
      </Panel>

      {/* Sport board */}
      <SportBetsBoard sport={sport} />

      <footer className="mt-4 text-center text-[11px] text-muted-foreground">
        {HONEST_DISCLAIMER} Best bets = ranked calibrated divergence + tier +
        confidence + CLV, never a fabricated profit claim. Units only -- no $
        anywhere. Real money is default-DENY.
      </footer>
    </main>
  );
}
