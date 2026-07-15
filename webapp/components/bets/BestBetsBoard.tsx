"use client";
// BestBetsBoard.tsx -- Best Bets board (W3). UNITS only; stale-never-green rail.
//
// Data source: GET /api/bestbets/board?sport=<sport> (richer board envelope) for
// each sport in parallel.  Returns BestBetsCard[] with model_prob, market_prob,
// best_book/best_odds, edge_vs_market, units, tier, status, tipoff_utc, clv.
//
// Partitioning:
//   - status "live"            -> Live tab
//   - status "pregame"         -> Pregame tab (default)
//   - status "done"            -> Done tab
//   - status "post"|"final"    -> EXCLUDED (game already over; skip_reason surfaced)
//
// Honest-empty: when a sport returns count===0 (e.g. NBA offseason) the banner
// renders "no cards -- <reason from API>" rather than a fabricated empty state.
//
// Auto-refresh via useLiveData (no bespoke setInterval). AgeBadge: amber when
// stale >15m, slate otherwise, NEVER green (stale-never-green rail).
//
// Pure helpers, types, SportSectionEmpty: BestBetsBoardHelpers.tsx (LOC split).

import { useState, useCallback, useMemo } from "react";
import { SPORTS } from "@/lib/p5api";
import { Unavailable } from "@/components/p6/Primitives";
import { useLiveData } from "@/lib/useLiveData";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";
import { StatusTabs, type BetStatus } from "./StatusTabs";
import { MarketTypeTabs, marketBucket, type MarketFilter } from "./MarketTypeTabs";
import { SortControls, type SortKey } from "./SortControls";
import { BetCard } from "./BetCard";
import { PanelErrorBoundary } from "@/components/p6/PanelErrorBoundary";
import { AgeBadge, RefreshAffordance } from "./RefreshAffordance";
import { UnavailableReasonBanner, EmptySection } from "./BestBetsStates";
import {
  fetchAllSports,
  extractFetchResult,
  cardToBetCardData,
  sortCards,
  SportSectionEmpty,
  shouldSuppressBet,
  type FetchResult,
} from "./BestBetsBoardHelpers";

// Re-export AgeBadge so existing test imports from "../BestBetsBoard" continue to resolve.
export { AgeBadge };

const AUTO_REFRESH_MS = 30_000; // 30 seconds -- W3 live refresh spec

// BestBetsBoard -- useLiveData-backed board. No bespoke data setInterval remains.
export function BestBetsBoard() {
  const [tab, setTab] = useState<BetStatus>("pregame");
  const [market, setMarket] = useState<MarketFilter>("all");
  const [sort, setSort] = useState<SortKey>("confidence");

  const fetcher = useCallback((signal: AbortSignal) => fetchAllSports(signal), []);

  const { data: result, lastUpdatedAt, ageSec, isStale, error, isLoading, refresh } =
    useLiveData<FetchResult>(fetcher, { intervalMs: AUTO_REFRESH_MS, staleAfterSec: 15 * 60 });

  const { boards, unavailableReasons } = extractFetchResult(
    result as FetchResult | Record<string, unknown> | null,
  );

  const asOf = useMemo(() => {
    if (!boards) return null;
    const dates = Object.values(boards)
      .map((sr) => sr?.board?.generated_at)
      .filter((d): d is string => Boolean(d));
    return dates.length > 0 ? (dates.sort().at(-1) ?? null) : null;
  }, [boards]);

  // asOfStamp: HH:MM:SS for PanelHead. Falls back to fetch time when no feed
  // timestamp is present so the stamp is never fabricated.
  const asOfStamp = useMemo(() => {
    const src = asOf ?? (lastUpdatedAt != null ? new Date(lastUpdatedAt).toISOString() : null);
    if (!src) return null;
    const t = Date.parse(src);
    if (Number.isNaN(t)) return null;
    return new Date(t).toLocaleTimeString("en-US", { hour12: false });
  }, [asOf, lastUpdatedAt]);

  // perSportCards: per-sport eligible cards (post/final excluded; degenerate kept with label).
  // UI-side guard: shouldSuppressBet is applied as a second layer against backend leaks.
  //   - settled (post/final): excluded from grid entirely (counted in uiSkippedCount)
  //   - degenerate_model=true: kept in grid, rendered with explicit decision=no_bet label
  const { perSportCards, allCards, uiSkippedCount } = useMemo(() => {
    if (!boards) {
      return {
        perSportCards: {} as Record<string, ReturnType<typeof cardToBetCardData>[]>,
        allCards: [] as ReturnType<typeof cardToBetCardData>[],
        uiSkippedCount: 0,
      };
    }
    const bySport: Record<string, ReturnType<typeof cardToBetCardData>[]> = {};
    const allAcc: ReturnType<typeof cardToBetCardData>[] = [];
    let uiSkipped = 0;
    for (const [sport, sr] of Object.entries(boards)) {
      if (!sr?.board) continue;
      const sportCards: ReturnType<typeof cardToBetCardData>[] = [];
      for (const card of sr.board.cards ?? []) {
        const suppressReason = shouldSuppressBet(card);
        if (suppressReason === "live_state_settled" || suppressReason === "status_settled") {
          uiSkipped += 1;
          continue;
        }
        const mapped = cardToBetCardData(card, suppressReason);
        sportCards.push(mapped);
        allAcc.push(mapped);
      }
      bySport[sport] = sportCards;
    }
    return { perSportCards: bySport, allCards: allAcc, uiSkippedCount: uiSkipped };
  }, [boards]);

  // skippedCount: total post/final cards excluded (fetch-time + UI-side guard)
  const skippedCount = useMemo(() => {
    if (!boards) return uiSkippedCount;
    const fetchSkipped = Object.values(boards).reduce(
      (n, sr) => n + (sr?.skipped?.length ?? 0), 0,
    );
    return fetchSkipped + uiSkippedCount;
  }, [boards, uiSkippedCount]);

  const counts = {
    live: allCards.filter((c) => c.status === "live").length,
    pregame: allCards.filter((c) => c.status === "pregame").length,
    done: allCards.filter((c) => c.status === "done").length,
  };

  // Market-type counts within the active status tab (drives the filter badges).
  const tabCards = allCards.filter((c) => c.status === tab);
  const marketCounts: Partial<Record<MarketFilter, number>> = {
    all: tabCards.length,
    moneyline: tabCards.filter((c) => marketBucket(c.market_type) === "moneyline").length,
    total: tabCards.filter((c) => marketBucket(c.market_type) === "total").length,
    spread: tabCards.filter((c) => marketBucket(c.market_type) === "spread").length,
    prop: tabCards.filter((c) => marketBucket(c.market_type) === "prop").length,
  };
  // Total prop count across ALL sports/statuses -- surfaced as a cap note since
  // the board API caps/ranks the (potentially large) prop set.
  const totalPropCount = allCards.filter((c) => marketBucket(c.market_type) === "prop").length;
  const anyFetched = result !== null;
  const showError = error !== null && !anyFetched;

  const unavailableSports = Object.entries(unavailableReasons).filter(
    ([, reason]) => Boolean(reason),
  );

  // activeSports: SPORTS list ordered; only sports present in boards are shown.
  const activeSports: string[] = boards ? SPORTS.filter((s) => s in boards) : [];

  return (
    <PanelErrorBoundary label="best bets board">
      <Panel>
        <PanelHead title="Best bets board" asOf={asOfStamp} stale={isStale} />
        <section aria-label="Best bets board" className="flex flex-col gap-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <StatusTabs value={tab} onChange={setTab} counts={counts} panelId="bets-board-panel" />
          <SortControls value={sort} onChange={setSort} />
        </div>
        {/* Market-type filter: every market (ML/total/spread/prop) as its own bet */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <MarketTypeTabs value={market} onChange={setMarket} counts={marketCounts} panelId="bets-board-panel" />
          {totalPropCount > 0 && (
            <span
              data-testid="prop-cap-note"
              className="font-data text-[10px] text-faint"
            >
              {totalPropCount} prop card{totalPropCount !== 1 ? "s" : ""} -- board API
              caps/ranks props; filter by sport / tier / Props tab
            </span>
          )}
        </div>
        <RefreshAffordance onRefresh={refresh} loading={isLoading} lastFetchedAt={lastUpdatedAt}
          asOf={asOf} ageSec={ageSec} isStale={isStale} intervalMs={AUTO_REFRESH_MS} />
        {isStale && anyFetched && error && (
          <div role="status" data-testid="stale-banner"
            className="border border-border bg-surface-2 px-3 py-2">
            <span className="font-data text-[10px] text-stale">
              poll failed -- showing last-good data. {error}
            </span>
          </div>
        )}
        {skippedCount > 0 && (
          <div role="status" data-testid="skipped-cards-notice"
            className="border border-border bg-surface-2 px-3 py-2">
            <span className="font-data text-[10px] text-faint">
              {skippedCount} card{skippedCount !== 1 ? "s" : ""} excluded: status=post/final
              (game already over -- not rendered as active bets)
            </span>
          </div>
        )}
        {unavailableSports.length > 0 && (
          <div className="flex flex-col gap-2" data-testid="unavailable-reasons-section">
            {unavailableSports.map(([sport, reason]) => (
              <UnavailableReasonBanner key={sport} sport={sport} reason={reason} />
            ))}
          </div>
        )}
        <div id="bets-board-panel" role="tabpanel" aria-label={`${tab} best bets`}
          aria-labelledby={`status-tab-${tab}`}>
          {isLoading && !anyFetched ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3].map((i) => <div key={i} className="skeleton-shimmer h-64" />)}
            </div>
          ) : showError ? (
            <Unavailable reason={error ?? "Could not load best bets."} />
          ) : activeSports.length === 0 ? (
            <EmptySection status={tab}
              label={anyFetched
                ? "No bet decisions cleared the tier floor -- matching the efficient close is a calibration success."
                : "No data returned from the predict service."} />
          ) : (
            <div className="flex flex-col gap-6" data-testid="cards-grid">
              {activeSports.map((sport) => {
                const sportCards = (perSportCards[sport] ?? [])
                  .filter((c) => c.status === tab)
                  .filter((c) => market === "all" || marketBucket(c.market_type) === market);
                const sorted = sortCards(sportCards, sort);
                const reason = unavailableReasons[sport] ?? null;
                return (
                  <section key={sport} aria-label={`${sport.toUpperCase()} best bets`}
                    data-testid={`sport-section-${sport}`} className="flex flex-col gap-3">
                    <div className="flex items-center gap-2">
                      <span className="microlabel">
                        {sport}
                      </span>
                      {sorted.length > 0 && (
                        <Num className="text-[10px] text-faint">
                          {sorted.length} card{sorted.length !== 1 ? "s" : ""}
                        </Num>
                      )}
                    </div>
                    {sorted.length === 0 ? (
                      <SportSectionEmpty sport={sport} reason={reason} />
                    ) : (
                      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" role="list"
                        aria-label={`${sport.toUpperCase()} ${tab} best bets`}>
                        {sorted.map((card, i) => (
                          <div key={`${card.game_id}-${card.market_type}-${card.side}-${i}`}
                            role="listitem" data-testid="card-row">
                            <BetCard card={card} />
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                );
              })}
            </div>
          )}
        </div>
        </section>
      </Panel>
    </PanelErrorBoundary>
  );
}
