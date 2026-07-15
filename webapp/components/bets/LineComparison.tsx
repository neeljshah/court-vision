"use client";

// LineComparison.tsx -- mini-table comparing lines across multiple books.
//
// HONESTY RAILS:
//   - Best line is highlighted by icon + aria + border, NOT by color alone (WCAG 1.4.1)
//   - Devigged market probability shown per-book so the user sees the real price
//   - No $ anywhere; odds shown in American format
//   - CLV absent -> 'INSUFFICIENT_DATA', never 0
//   - When books list is empty: honest Unavailable primitive, never guessed data

import * as React from "react";
import { cn } from "@/lib/utils";
import { Unavailable } from "@/components/p6/Primitives";
import type { BookLine } from "./cardDepth";
import { findBestLine, devigProb } from "./cardDepth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LineComparisonEntry extends BookLine {
  /** Optional CLV for this book's line. Null -> INSUFFICIENT_DATA. */
  clv?: number | null;
  /** Whether this CLV value is a proxy (estimated, not real-time). */
  clv_is_proxy?: boolean;
}

export interface LineComparisonProps {
  /** List of book lines for the same market side. */
  books: LineComparisonEntry[];
  /** Market side label, e.g. "over", "home". Used in aria labels. */
  side?: string;
  /** Market type label, e.g. "totals", "moneyline". */
  market_type?: string;
  /** Optional: odds for the opposing side (enables two-outcome devig). */
  opposing_odds?: number | null;
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function fmtAmericanOdds(o: number): string {
  if (o <= 1) return "--";
  if (o === 2.0) return "+100";
  if (o >= 2.0) return `+${Math.round((o - 1) * 100)}`;
  return `-${Math.round(100 / (o - 1))}`;
}

function fmtLine(line: number): string {
  return line > 0 ? `+${line}` : `${line}`;
}

function fmtDevig(prob: number): string {
  return `${(prob * 100).toFixed(1)}%`;
}

function fmtClv(clv: number | null | undefined, is_proxy?: boolean): string {
  if (clv == null) return "INSUFFICIENT_DATA";
  const sign = clv > 0 ? "+" : "";
  const pct = `${sign}${(clv * 100).toFixed(1)}%`;
  return is_proxy ? `${pct}*` : pct;
}

function clvColorClass(clv: number | null | undefined): string {
  if (clv == null) return "text-stale";
  if (clv > 0) return "text-up";
  return "text-down";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function BestBadge() {
  return (
    <span
      className="inline-flex items-center bg-surface-3 px-1 font-data text-[8px] font-bold uppercase tracking-wide text-foreground border border-border"
      aria-hidden="true"
    >
      best
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const TABLE_ARIA_TIP =
  "Line comparison across books. Best line = highest decimal odds. " +
  "Market p = devigged implied probability (Shin two-outcome approximation). " +
  "CLV = closing-line value vs final market. INSUFFICIENT_DATA means no live prices.";

export function LineComparison({
  books,
  side,
  market_type,
  opposing_odds,
}: LineComparisonProps) {
  if (!books || books.length === 0) {
    return <Unavailable reason="no book lines available for comparison" />;
  }

  const bestIdx = findBestLine(books);
  const sideLabel = side ? ` for ${side}` : "";
  const marketLabel = market_type ? `${market_type} ` : "";

  return (
    <div
      className="flex flex-col gap-1"
      aria-label={`${marketLabel}line comparison${sideLabel}. ${TABLE_ARIA_TIP}`}
      data-testid="line-comparison"
    >
      {/* Header row */}
      <div
        className="grid gap-x-3 microlabel pb-1 border-b border-border"
        style={{ gridTemplateColumns: "1fr auto auto auto" }}
        aria-hidden="true"
      >
        <span>Book</span>
        <span className="text-right">Odds</span>
        <span className="text-right">Market p</span>
        <span className="text-right">CLV</span>
      </div>

      {/* Book rows */}
      <ul className="flex flex-col gap-0.5" role="list">
        {books.map((entry, i) => {
          const isBest = i === bestIdx;
          const devigged = devigProb(
            entry.odds,
            opposing_odds ?? undefined,
          );
          const americanOdds = fmtAmericanOdds(entry.odds);
          const devigStr = fmtDevig(devigged);
          const clvStr = fmtClv(entry.clv, entry.clv_is_proxy);
          const lineStr =
            entry.line != null ? ` ${fmtLine(entry.line)}` : "";

          const rowAriaLabel = [
            entry.book,
            lineStr ? `line ${lineStr.trim()}` : null,
            `odds ${americanOdds}`,
            `market probability ${devigStr}`,
            entry.clv != null
              ? `CLV ${clvStr}`
              : "CLV insufficient data",
            isBest ? "best line" : null,
          ]
            .filter(Boolean)
            .join(", ");

          return (
            <li
              key={`${entry.book}-${i}`}
              role="listitem"
              aria-label={rowAriaLabel}
              data-testid={isBest ? "best-line-row" : "book-line-row"}
            >
              <div
                className={cn(
                  "grid gap-x-3 items-center px-2 py-1.5",
                  "text-[11px] font-data tabular transition-colors",
                  isBest
                    ? "border border-border bg-surface-2"
                    : "border border-transparent hover:bg-surface-2",
                )}
                style={{ gridTemplateColumns: "1fr auto auto auto" }}
              >
                {/* Book name + optional best badge */}
                <div className="flex items-center gap-1.5 min-w-0">
                  <span
                    className={cn(
                      "truncate font-data text-[10px] uppercase tracking-wide",
                      isBest ? "text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {entry.book}
                  </span>
                  {entry.line != null ? (
                    <span className="text-[9px] text-faint">{lineStr}</span>
                  ) : null}
                  {isBest ? <BestBadge /> : null}
                </div>

                {/* American odds */}
                <span
                  className={cn(
                    "text-right",
                    isBest ? "text-foreground" : "text-muted-foreground",
                  )}
                  aria-hidden="true"
                >
                  {americanOdds}
                </span>

                {/* Devigged market probability */}
                <span
                  className="text-right text-faint"
                  aria-hidden="true"
                  data-testid={isBest ? "best-line-devig" : "devig-prob"}
                >
                  {devigStr}
                </span>

                {/* CLV */}
                <span
                  className={cn("text-right", clvColorClass(entry.clv))}
                  aria-hidden="true"
                  data-testid={
                    entry.clv == null ? "clv-insufficient" : "clv-value"
                  }
                >
                  {clvStr}
                </span>
              </div>
            </li>
          );
        })}
      </ul>

      {/* Footer footnote: honesty copy */}
      <p
        className="mt-1 font-data text-[8px] text-faint leading-tight"
        aria-hidden="true"
      >
        Market p = devigged implied probability. CLV = closing-line value.
        INSUFFICIENT_DATA = no live prices. Best = highest decimal odds.
        Units only -- no $.
      </p>
    </div>
  );
}
