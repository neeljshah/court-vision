"use client";

// PropCard.tsx -- one player-prop bet card for the Bets board.
//
// Prop cards show: player + stat + line (or "no line") + side + model_prob +
// proj (model point projection). When model_only=true (no market line) a clear
// "MODEL-ONLY (no line)" badge is shown and NO edge claim is made. When priced,
// edge_vs_market is shown as a probability divergence (NOT a profit claim).
//
// HONESTY RAILS: UNITS only -- NO "$"; model-only props make NO edge claim;
// CLV null -> INSUFFICIENT_DATA. ASCII only. <=300 LOC.

import * as React from "react";
import Link from "next/link";
import { cn, tierClass } from "@/lib/utils";
import { Badge } from "@/components/p6/Primitives";
import type { BetCardData } from "./BetCard";
import { LineShopPanel } from "./LineShopPanel";
import type { BookShopEntry } from "@/lib/types";
import { clvLabel, statusDot, fmtTipoff } from "./BetCardHelpers";
import { formatDivergence } from "./cardDepth";

function fmtProbPct(p: number | null | undefined): string {
  if (p == null || !isFinite(p)) return "--";
  return `${(p * 100).toFixed(1)}%`;
}

export interface PropCardProps {
  card: BetCardData;
  books?: BookShopEntry[];
}

export function PropCard({ card, books }: PropCardProps) {
  const isModelOnly = card.model_only === true || card.line == null;
  const player = card.prop_player ?? card.matchup;
  const stat = (card.prop_stat ?? "").toUpperCase();
  const lineStr = card.line != null ? String(card.line) : null;

  // Card-link guard: only link to detail when game_id is real. Empty/missing
  // game_id -> /bets/<sport>/ 308-redirects back to the board, so disable it.
  const hasGameId = typeof card.game_id === "string" && card.game_id.trim() !== "";
  const detailHref = `/bets/${encodeURIComponent(card.sport)}/${encodeURIComponent(card.game_id)}`;
  const detailLinkLabel = `View details: ${player} ${stat} ${card.side}`;
  const tipoffStr = fmtTipoff(card.tipoff_utc ?? null);

  const edge = card.edge_vs_market;
  const showEdge = !isModelOnly && edge != null;

  return (
    <article
      aria-label={`${player} -- ${stat} prop ${card.side}${isModelOnly ? " -- model-only, no line, no edge claim" : ""}`}
      data-testid="prop-card-article"
      data-model-only={isModelOnly ? "true" : "false"}
      className={cn(
        "border bg-card transition-colors",
        card.status === "live" ? "border-warning/60" : "border-border",
      )}
    >
      <div className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              {statusDot(card.status)}
              <span className="microlabel">{card.sport.toUpperCase()}</span>
              <span className="bg-surface-2 px-1.5 microlabel">
                prop
              </span>
              {tipoffStr ? (
                <span className="font-data text-[10px] text-faint">{tipoffStr}</span>
              ) : null}
            </div>
            <div className="mt-0.5 font-semibold text-foreground truncate">{player}</div>
            <div className="mt-0.5 font-data text-xs text-muted-foreground">
              {stat}
              {lineStr != null ? ` ${lineStr}` : ""}{" "}
              <span className="text-foreground">{card.side}</span>
            </div>
          </div>
          <span
            className={cn(
              "inline-flex border px-2 py-1 font-data text-[11px] font-semibold shrink-0",
              tierClass(card.tier ?? undefined),
            )}
            aria-label={card.tier ? `tier ${card.tier}` : "untiered"}
            data-testid="tier-badge"
          >
            {card.tier ?? "--"}
          </span>
        </div>

        {/* Model-only badge OR priced divergence */}
        {isModelOnly ? (
          <div
            className="mt-3 border border-warning/40 bg-warning/10 px-3 py-2"
            data-testid="model-only-badge"
            role="status"
            aria-label="model-only: no market line, no edge claimed"
          >
            <span className="font-data text-[10px] font-semibold uppercase tracking-wide text-warning">
              model-only (no line)
            </span>
            <p className="mt-0.5 font-data text-[10px] text-faint">
              No market line for this prop -- a calibrated projection only. No edge is claimed.
            </p>
          </div>
        ) : (
          <div className="mt-3 flex items-center justify-end gap-1.5" data-testid="prop-divergence">
            <span className="microlabel">
              Calibrated divergence
            </span>
            <span
              className="inline-flex items-center border border-border bg-surface-3 px-2 py-0.5 font-data text-[10px] font-semibold tabular text-foreground"
              aria-label={`calibrated divergence ${formatDivergence(edge ?? 0)} -- not an edge or profit claim`}
            >
              {showEdge ? formatDivergence(edge!) : "--"}
            </span>
          </div>
        )}

        {/* Model prob / projection / market prob */}
        <div className="mt-3 grid grid-cols-3 gap-2">
          <div className="flex flex-col">
            <span className="microlabel">Model p({card.side})</span>
            <span className="font-data tabular text-sm text-foreground">{fmtProbPct(card.model_prob)}</span>
          </div>
          <div className="flex flex-col">
            <span className="microlabel">Proj</span>
            <span className="font-data tabular text-sm text-foreground" data-testid="prop-proj">
              {card.proj != null ? card.proj.toFixed(1) : "--"}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="microlabel">Market p</span>
            <span className="font-data tabular text-sm text-muted-foreground">
              {card.market_prob != null ? fmtProbPct(card.market_prob) : "INSUF"}
            </span>
          </div>
        </div>

        {/* Best book + units */}
        <div className="mt-3 flex items-center gap-3 flex-wrap">
          <div className="flex flex-col">
            <span className="microlabel">Best book</span>
            <span className="font-data text-xs text-foreground">
              {isModelOnly ? "no line" : card.best_book || "--"}
            </span>
          </div>
          <div className="flex flex-col ml-auto text-right">
            <span className="microlabel">Units</span>
            <span
              className="font-data tabular text-sm text-foreground"
              aria-label={`${card.units.toFixed(1)} UNITS -- stake in units not dollars`}
              data-testid="units-value"
            >
              {card.units.toFixed(1)} <span className="text-[10px] uppercase text-muted-foreground">UNITS</span>
            </span>
          </div>
        </div>

        {/* Line shopping (priced props only) */}
        {!isModelOnly && books && books.length > 0 ? (
          <div className="mt-3">
            <span className="mb-1 block microlabel">
              Line shopping
            </span>
            <LineShopPanel books={books} side={card.side} />
          </div>
        ) : null}

        {/* CLV */}
        <div className="mt-3 flex items-center justify-between flex-wrap gap-1">
          {clvLabel(card.clv, card.clv_is_proxy)}
        </div>

        {/* honest note */}
        {card.honest_note ? (
          <p className="mt-2 font-data text-[9px] text-faint">{card.honest_note}</p>
        ) : null}

        <div className="mt-2 border-t border-border pt-2 text-right">
          <Badge tone="slate">units only -- no $</Badge>
        </div>

        <div className="mt-3">
          {hasGameId ? (
            <Link
              href={detailHref}
              className={cn(
                "group inline-flex w-full items-center justify-center gap-1.5 border",
                "border-border bg-surface-2 px-3 py-2",
                "font-data text-[11px] text-muted-foreground transition-colors",
                "hover:border-muted-foreground hover:text-foreground",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-card",
              )}
              aria-label={detailLinkLabel}
              data-testid="bet-card-detail-link"
            >
              <span aria-hidden="true">View detail</span>
              <span className="sr-only">{detailLinkLabel}</span>
            </Link>
          ) : (
            <span
              className={cn(
                "inline-flex w-full cursor-not-allowed items-center justify-center gap-1.5 border",
                "border-border bg-surface-1 px-3 py-2",
                "font-data text-[11px] text-faint",
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
