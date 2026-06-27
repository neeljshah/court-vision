"use client";

// LineShopPanel.tsx -- compact line-shopping display from a card's books[].
//
// Each entry: { book, price (decimal odds), line, as_of, fresh, is_pm }.
// The freshest BETTABLE book with the best price is highlighted "best". A
// prediction-market book (is_pm=true) is shown for context but NEVER tagged
// "best bettable" (it is labeled "PM" and excluded from best selection).
// A stale entry (fresh=false) is dimmed and never highlighted as best.
//
// HONESTY RAILS: UNITS only -- NO "$" token; stale-never-green (fresh=false
// dimmed); PM books labeled and never "best bettable". ASCII only.

import * as React from "react";
import { cn, fmtDecimalOdds } from "@/lib/utils";
import type { BookShopEntry } from "@/lib/types";

function fmtLine(line: number | null | undefined): string | null {
  if (line == null) return null;
  return line > 0 ? `+${line}` : `${line}`;
}

// pick the index of the best BETTABLE (non-PM, fresh) price (highest decimal odds).
function bestBettableIndex(books: BookShopEntry[]): number {
  let best = -1;
  let bestPrice = -Infinity;
  books.forEach((b, i) => {
    if (b.is_pm || !b.fresh || b.price == null) return;
    if (b.price > bestPrice) {
      bestPrice = b.price;
      best = i;
    }
  });
  return best;
}

export interface LineShopPanelProps {
  books: BookShopEntry[];
  side?: string;
}

export function LineShopPanel({ books, side }: LineShopPanelProps) {
  if (!books || books.length === 0) {
    return (
      <span className="font-mono text-[10px] text-slate-600">
        no multi-book lines available
      </span>
    );
  }
  const bestIdx = bestBettableIndex(books);

  return (
    <ul
      className="flex flex-wrap gap-1.5"
      aria-label={`Line shopping${side ? ` for ${side}` : ""}`}
      data-testid="line-shop-panel"
    >
      {books.map((b, i) => {
        const isBest = i === bestIdx;
        const lineStr = fmtLine(b.line);
        const priceStr = b.price != null ? fmtDecimalOdds(b.price) : "--";
        const ariaLabel = [
          b.book,
          lineStr ? `line ${lineStr}` : null,
          `price ${priceStr}`,
          b.is_pm ? "prediction market, not best-bettable" : null,
          isBest ? "best bettable line" : null,
          !b.fresh ? "stale" : null,
        ]
          .filter(Boolean)
          .join(", ");

        return (
          <li key={`${b.book}-${i}`}>
            <span
              role="img"
              aria-label={ariaLabel}
              data-testid={isBest ? "line-shop-best" : "line-shop-entry"}
              className={cn(
                "inline-flex flex-col items-center gap-0.5 rounded-md border px-2 py-1",
                isBest
                  ? "border-tier-a/50 bg-tier-a/10"
                  : "border-slate-700 bg-slate-900/60",
                !b.fresh && "opacity-50",
              )}
            >
              <span className="flex items-center gap-1">
                <span
                  className={cn(
                    "font-mono text-[9px] uppercase tracking-wide",
                    isBest ? "text-tier-a" : "text-slate-500",
                  )}
                >
                  {b.book}
                </span>
                {b.is_pm && (
                  <span
                    className="rounded bg-slate-800 px-1 font-mono text-[8px] font-bold uppercase text-slate-400"
                    aria-hidden="true"
                  >
                    PM
                  </span>
                )}
                {isBest && (
                  <span
                    className="rounded bg-tier-a/20 px-1 font-mono text-[8px] font-bold uppercase text-tier-a"
                    aria-hidden="true"
                  >
                    best
                  </span>
                )}
                {!b.fresh && (
                  <span
                    className="rounded bg-amber-950/40 px-1 font-mono text-[8px] font-bold uppercase text-amber-500"
                    aria-hidden="true"
                  >
                    stale
                  </span>
                )}
              </span>
              <span
                className={cn(
                  "font-mono text-[11px] font-semibold tabular-nums leading-none",
                  isBest ? "text-tier-a" : "text-slate-300",
                )}
              >
                {priceStr}
              </span>
              {lineStr ? (
                <span
                  className={cn(
                    "font-mono text-[9px] leading-none",
                    isBest ? "text-tier-a/70" : "text-slate-500",
                  )}
                >
                  {lineStr}
                </span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
