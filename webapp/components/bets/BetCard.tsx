"use client";

// BetCard.tsx -- one best-bet card for the Bets board.
// A11Y: <article> with aria-label naming matchup/market/side/tier. Detail Link has
// focus ring + sr-only accessible name. Divergence column = "Calibrated divergence".
// HONESTY: UNITS only (no $); CLV null -> INSUFFICIENT_DATA (never greened);
// divergence is a calibrated signal, NEVER an edge/profit claim.
//
// WS6: ModelVsMarketBar wired (replaces inline prob strip). tipoff_utc shown.
// units labeled "X.Xu UNITS" explicitly per WS6 spec.
//
// Helpers/sub-components: BetCardHelpers.tsx (split to keep file <=300 LOC).

import * as React from "react";
import Link from "next/link";
import { cn, tierClass } from "@/lib/utils";
import { Badge } from "@/components/p6/Primitives";
import { BookShoppingRow, type BookOddsEntry } from "./BookShoppingRow";
import type { SuppressReason } from "./BestBetsCardGuards";
import {
  clvLabel,
  statusDot,
  fmtAmericanOdds,
  buildArticleLabel,
  fmtTipoff,
  UNITS_TIP,
  SuppressedCard,
} from "./BetCardHelpers";
import { ModelVsMarketBar } from "./ModelVsMarketBar";
import { formatDivergence, isDivergenceSignal } from "./cardDepth";
import { PropCard } from "./PropCard";
import { LineShopPanel } from "./LineShopPanel";
import type { BookShopEntry } from "@/lib/types";
import { humanizeMatchup, describeBet } from "@/lib/betdesc";

export interface BetCardData {
  game_id: string;
  sport: string;
  matchup: string;           // e.g. "NYK @ SAS"
  market_type: string;       // "moneyline" | "total" | "spread" | "prop"
  side: string;              // e.g. "home", "over", "NYK +3.5"
  model_prob: number;        // [0,1] calibrated model probability
  market_prob: number | null; // [0,1] devigged market prob; null for model-only props
  best_book: string;
  best_odds: number;         // decimal odds
  all_books: BookOddsEntry[];
  // edge_vs_market: model_prob - market_prob (display as divergence, NOT profit).
  // null for model-only props (no market line -> no edge claim).
  edge_vs_market: number | null;
  units: number;             // stake in units
  tier: string | null;       // "S"|"A"|"B"|"C"
  confidence: number;        // [0,1] confidence in the calibrated signal
  clv: number | null;        // null -> INSUFFICIENT_DATA
  clv_is_proxy: boolean;
  status: "live" | "pregame" | "done";
  line?: number | null;
  tipoff_utc?: string | null; // ISO timestamp -- shown as "Tipoff: HH:MM ET" when present
  // -- prop fields (market_type === "prop") ---------------------------------
  prop_player?: string | null;
  prop_stat?: string | null;
  proj?: number | null;       // model point projection for the prop stat
  model_only?: boolean;       // true -> no market line; "model-only" badge, no edge
  honest_note?: string | null;
  // books[] -- richer line-shopping array (price/line/as_of/fresh/is_pm).
  books?: BookShopEntry[];
  // UI-side guard: non-null means the card must NOT render as an actionable bet.
  // "degenerate_model" -> render decision=no_bet EXPLICITLY (not silently suppressed).
  // "live_state_settled" / "status_settled" -> render settled/no-bet label.
  suppress_reason?: SuppressReason;
}

export interface BetCardProps {
  card: BetCardData;
}

export function BetCard({ card }: BetCardProps) {
  // UI-side guard: render suppressed state when suppress_reason is set.
  if (card.suppress_reason != null) {
    return <SuppressedCard card={card} />;
  }

  // Prop cards take a dedicated layout (player/stat/line/proj + model-only badge).
  if (card.market_type === "prop") {
    return <PropCard card={card} books={card.books} />;
  }

  // Game markets: edge_vs_market may be null (rare); fall back to a 0 divergence.
  const divergence = card.edge_vs_market ?? 0; // signed: model_prob - market_prob
  const marketProb = card.market_prob ?? 0;
  const divergenceLabel = formatDivergence(divergence);
  const divergenceIsSignal = card.edge_vs_market != null && isDivergenceSignal(divergence);

  // Card-link guard: only link to a detail route when game_id is real. An empty
  // / missing game_id would build /bets/<sport>/ which 308-redirects back to the
  // board -- so we DISABLE the link instead of rendering a dead one.
  const hasGameId = typeof card.game_id === "string" && card.game_id.trim() !== "";
  const detailHref = `/bets/${encodeURIComponent(card.sport)}/${encodeURIComponent(card.game_id)}`;
  const detailLinkLabel = `View details: ${card.matchup} ${card.market_type} ${card.side}`;

  const tipoffStr = fmtTipoff(card.tipoff_utc ?? null);

  return (
    <article
      aria-label={buildArticleLabel(card)}
      className={cn(
        "rounded-xl border bg-bg-panel transition-colors",
        card.status === "live"
          ? "border-amber-900/60"
          : "border-border",
      )}
      data-testid="bet-card-article"
    >
      <div className="p-4">
        {/* Header row */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              {statusDot(card.status)}
              <span className="font-mono text-[11px] text-faint">{card.sport.toUpperCase()}</span>
              {tipoffStr ? (
                <span
                  className="font-mono text-[10px] text-faint"
                  data-testid="tipoff-display"
                  aria-label={`Tipoff: ${tipoffStr}`}
                >
                  {tipoffStr}
                </span>
              ) : null}
            </div>
            <div className="mt-0.5 font-semibold text-foreground truncate">
              {humanizeMatchup(card.matchup)}
            </div>
            <div className="mt-0.5 font-mono text-xs text-foreground">
              {describeBet({
                market_type: card.market_type,
                side: card.side,
                line: card.line,
                matchup: card.matchup,
              })}
            </div>
          </div>
          {/* Tier badge */}
          <span
            className={cn(
              "inline-flex rounded border px-2 py-1 font-mono text-[11px] font-semibold shrink-0",
              tierClass(card.tier ?? undefined),
            )}
            aria-label={card.tier ? `tier ${card.tier}` : "untiered"}
            data-testid="tier-badge"
          >
            {card.tier ?? "--"}
          </span>
        </div>

        {/* Model vs Market probability bar -- WS6: use ModelVsMarketBar component */}
        <div className="mt-3">
          <ModelVsMarketBar
            model_prob={card.model_prob}
            market_prob={marketProb}
            divergence={divergence}
            divergence_label={divergenceLabel}
            divergence_is_signal={divergenceIsSignal}
            framing="bet"
            confidence={card.confidence}
            aria_suffix={`${card.matchup} ${card.market_type} ${card.side}`}
          />
        </div>

        {/* Best line + units */}
        <div className="mt-3 flex items-center gap-3 flex-wrap">
          <div className="flex flex-col">
            <span className="font-mono text-[9px] uppercase tracking-widest text-faint">Best book</span>
            <span className="font-mono text-xs text-foreground">
              {card.best_book}
              {card.best_odds != null ? (
                <span className="ml-1 text-muted-foreground" data-testid="odds-value">
                  {fmtAmericanOdds(card.best_odds)}
                </span>
              ) : null}
            </span>
          </div>
          <div className="flex flex-col ml-auto text-right">
            <span className="font-mono text-[9px] uppercase tracking-widest text-faint">Units</span>
            {/* WS6: explicit "UNITS" label, never "$" */}
            <span
              className="font-mono text-sm text-foreground tabular-nums cursor-help"
              title={UNITS_TIP}
              aria-label={`${card.units.toFixed(1)} UNITS, quarter-Kelly sizing capped -- stake in units not dollars`}
              data-testid="units-value"
            >
              {card.units.toFixed(1)}{" "}
              <span className="text-[10px] text-muted-foreground uppercase">UNITS</span>
            </span>
          </div>
        </div>

        {/* Line shopping -- prefer richer books[] (price/fresh/is_pm), else all_books */}
        {card.books && card.books.length > 0 ? (
          <div className="mt-3">
            <span className="mb-1 block font-mono text-[9px] uppercase tracking-widest text-faint">
              Line shopping
            </span>
            <LineShopPanel books={card.books} side={card.side} />
          </div>
        ) : card.all_books.length > 0 ? (
          <div className="mt-3">
            <span className="mb-1 block font-mono text-[9px] uppercase tracking-widest text-faint">
              All books
            </span>
            <BookShoppingRow books={card.all_books} side={card.side} />
          </div>
        ) : null}

        {/* CLV footer -- INSUFFICIENT_DATA shown honestly when clv is null */}
        <div className="mt-3 flex items-center justify-between flex-wrap gap-1">
          {clvLabel(card.clv, card.clv_is_proxy)}
        </div>

        {/* Honest units-only note */}
        <div className="mt-2 border-t border-border pt-2 text-right">
          <Badge tone="slate">units only -- no $</Badge>
        </div>

        {/* Detail link -- accessible name via sr-only text; visible focus ring.
            Guarded: when game_id is missing we render a disabled, non-clickable
            placeholder so a click can't 308-redirect back to the board. */}
        <div className="mt-3">
          {hasGameId ? (
            <Link
              href={detailHref}
              className={cn(
                "group inline-flex w-full items-center justify-center gap-1.5 rounded-lg border",
                "border-border bg-surface-2 px-3 py-2",
                "font-mono text-[11px] text-muted-foreground transition-colors",
                "hover:border-muted-foreground hover:text-foreground",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-bg-panel",
              )}
              aria-label={detailLinkLabel}
              data-testid="bet-card-detail-link"
            >
              <span aria-hidden="true">View detail</span>
              {/* sr-only span provides explicit accessible name for non-visual context */}
              <span className="sr-only">{detailLinkLabel}</span>
            </Link>
          ) : (
            <span
              className={cn(
                "inline-flex w-full cursor-not-allowed items-center justify-center gap-1.5 rounded-lg border",
                "border-border bg-card px-3 py-2",
                "font-mono text-[11px] text-faint",
              )}
              aria-disabled="true"
              data-testid="bet-card-detail-link-disabled"
              title="No game id yet -- detail view unavailable"
            >
              detail unavailable
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
