"use client";

// BetCardHelpers.tsx -- Extracted helper functions and sub-components for BetCard.tsx.
// Keeps BetCard.tsx under the 300-LOC rail (split per repo invariant).
// Exports: clvLabel, statusDot, fmtAmericanOdds, fmtTipoff, buildArticleLabel,
//          DIVERGENCE_TIP, UNITS_TIP, SuppressedCard.

import * as React from "react";
import Link from "next/link";
import { cn, fmtPct, tierClass } from "@/lib/utils";
import { Badge } from "@/components/p6/Primitives";
import { suppressReasonLabel } from "./BestBetsCardGuards";
import type { SuppressReason } from "./BestBetsCardGuards";
import type { BetCardData } from "./BetCard";

// ---------------------------------------------------------------------------
// Tooltip constants
// ---------------------------------------------------------------------------

// Tooltip for divergence value: calibrated signal, NOT a profit/edge claim.
export const DIVERGENCE_TIP =
  "Calibrated divergence (model prob minus devigged market prob). " +
  "A negative value means model is below market -- e.g. an under or away pick -- " +
  "which is a valid stance, not an error. This is NOT a profit or edge claim.";

// Tooltip for units: quarter-Kelly sizing in abstract units, NEVER dollars.
export const UNITS_TIP =
  "Stake in units (quarter-Kelly sizing, capped). " +
  "Can be <1.0 or >1.0 depending on Kelly fraction. " +
  "NEVER dollars -- this is a units-only display.";

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

// clvLabel: CLV null -> INSUFFICIENT_DATA (amber, never green); numeric -> colored.
export function clvLabel(clv: number | null, proxy: boolean): React.ReactNode {
  if (clv === null) {
    return (
      <span
        className="font-data text-[10px] text-stale"
        aria-label="CLV: INSUFFICIENT_DATA -- no live prices available"
      >
        CLV: INSUFFICIENT_DATA
      </span>
    );
  }
  return (
    <span
      className={cn("font-data tabular text-[10px]", clv > 0 ? "text-up" : "text-down")}
      aria-label={`CLV ${clv > 0 ? "+" : ""}${(clv * 100).toFixed(1)}%${proxy ? " (proxy)" : ""}`}
    >
      CLV {clv > 0 ? "+" : ""}{(clv * 100).toFixed(1)}%
      {proxy ? " (proxy)" : ""}
    </span>
  );
}

// statusDot: inline dot + label for live/pregame/done statuses.
export function statusDot(status: BetCardData["status"]): React.ReactNode {
  const map = {
    live: { cls: "bg-amber-400 animate-pulse", label: "LIVE" },
    pregame: { cls: "bg-muted-foreground", label: "PREGAME" },
    // DONE: visible neutral (not the near-invisible bg-slate-700, not green, not pulsing).
    done: { cls: "bg-slate-500", label: "DONE" },
  } as const;
  const { cls, label } = map[status];
  return (
    <span className="inline-flex items-center gap-1.5 font-data text-[10px] text-muted-foreground">
      <span
        className={cn("h-1.5 w-1.5", cls)}
        data-testid={`status-dot-${status}`}
        aria-hidden="true"
      />
      {label}
    </span>
  );
}

// fmtAmericanOdds: decimal -> American. <= 1.0 -> '--'; == 2.0 -> '+100'.
export function fmtAmericanOdds(o: number): string {
  if (o <= 1.0) return "--";
  if (o === 2.0) return "+100";
  if (o > 2.0) return `+${Math.round((o - 1) * 100)}`;
  // 1.0 < o < 2.0
  return `-${Math.round(100 / (o - 1))}`;
}

// fmtTipoff: format a tipoff_utc ISO timestamp to a short "Tipoff HH:MM ET" label.
// Returns null when tipoff_utc is absent/null/invalid.
export function fmtTipoff(tipoff_utc: string | null | undefined): string | null {
  if (!tipoff_utc) return null;
  const d = new Date(tipoff_utc);
  if (Number.isNaN(d.getTime())) return null;
  // Format in US/Eastern; browsers may not have the full IANA DB but toLocaleTimeString
  // with timeZone is widely supported. If it throws, fall back to UTC display.
  try {
    const time = d.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      timeZone: "America/New_York",
    });
    return `Tipoff ${time} ET`;
  } catch {
    const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
    return `Tipoff ${time} UTC`;
  }
}

// buildArticleLabel: aria-label for the article -- matchup, market, side, tier.
export function buildArticleLabel(card: BetCardData): string {
  const tierStr = card.tier ? `tier ${card.tier}` : "untiered";
  const lineStr =
    card.line != null
      ? ` ${card.line > 0 ? "+" : ""}${card.line}`
      : "";
  return (
    `${card.matchup} -- ${card.market_type}${lineStr} ${card.side}, ${tierStr}, ` +
    `calibrated divergence signal, not a profit or edge claim`
  );
}

// ---------------------------------------------------------------------------
// SuppressedCard -- shown when card has a suppress_reason (degenerate/settled).
// Renders the honest reason and a detail link; never renders decision=bet.
// ---------------------------------------------------------------------------

export function SuppressedCard({ card }: { card: BetCardData }) {
  const reason: SuppressReason | null = card.suppress_reason ?? null;
  const label = suppressReasonLabel(reason);
  const detailHref = `/bets/${encodeURIComponent(card.sport)}/${encodeURIComponent(card.game_id)}`;
  const isDegenerate = reason === "degenerate_model";

  return (
    <article
      aria-label={`${card.matchup} -- ${card.market_type} ${card.side} -- ${label}`}
      className="border border-border bg-card"
      data-testid="bet-card-article"
      data-suppress-reason={reason ?? "none"}
    >
      <div className="p-4 flex flex-col gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="microlabel">{card.sport.toUpperCase()}</span>
          {card.tier && (
            <span className={cn("inline-flex border px-2 py-0.5 font-data text-[11px] font-semibold", tierClass(card.tier))}>
              {card.tier}
            </span>
          )}
        </div>
        <div className="font-semibold text-foreground truncate">{card.matchup}</div>
        <div className="font-data text-xs text-muted-foreground">{card.market_type} <span className="text-foreground">{card.side}</span></div>
        {/* Explicit no_bet / settled label -- never decision=bet */}
        <div
          className={cn(
            "mt-1 border px-3 py-2 font-data text-[11px]",
            isDegenerate
              ? "border-warning/40 bg-warning/10 text-warning"
              : "border-border bg-surface-2 text-muted-foreground",
          )}
          data-testid={isDegenerate ? "degenerate-no-bet-label" : "settled-no-bet-label"}
          role="status"
          aria-label={label}
        >
          {label}
        </div>
        {/* Calibrated divergence (context only) */}
        <div className="flex gap-3 items-center flex-wrap">
          <span className="microlabel">Calibrated divergence (context only)</span>
          <span className="font-data tabular text-xs text-faint">
            {card.edge_vs_market != null ? fmtPct(card.edge_vs_market) : "--"}
          </span>
        </div>
        {/* edge_vs_market label -- always "calibrated divergence", never profit */}
        <div className="border-t border-border pt-2 text-right">
          <Badge tone="slate">calibrated divergence -- no $ edge</Badge>
        </div>
        <div>
          <Link
            href={detailHref}
            className={cn(
              "group inline-flex w-full items-center justify-center gap-1.5 border",
              "border-border bg-surface-2 px-3 py-2",
              "font-data text-[11px] text-muted-foreground transition-colors",
              "hover:border-muted-foreground hover:text-foreground",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-card",
            )}
            aria-label={`View details: ${card.matchup} ${card.market_type} ${card.side}`}
            data-testid="bet-card-detail-link"
          >
            <span aria-hidden="true">View detail</span>
            <span className="sr-only">{`View details: ${card.matchup} ${card.market_type} ${card.side}`}</span>
          </Link>
        </div>
      </div>
    </article>
  );
}
