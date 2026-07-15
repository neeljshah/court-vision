"use client";

// BookShoppingRow.tsx -- multi-book line comparison for one market.
//
// Renders a row of book pills showing each book's odds/line for a market.
// The best-book pill carries a visible "best" tag AND an explicit aria-label
// so screen readers don't rely on color alone (WCAG 1.4.1 / Success Criterion
// 1.4.1: use of color). Odds are shown in American format via fmtDecimalOdds.
//
// Display-only. No $ anywhere. When no books are available renders the honest
// Unavailable primitive -- never a guess or fabricated number.

import * as React from "react";
import { cn, fmtDecimalOdds } from "@/lib/utils";
import { Unavailable } from "@/components/p6/Primitives";

export interface BookOddsEntry {
  book: string;
  odds: number;   // decimal odds (e.g. 1.91)
  line?: number | null;
  is_best?: boolean;
}

export interface BookShoppingRowProps {
  books: BookOddsEntry[];
  /** The side label (e.g. "home", "over") used in screen-reader labels. */
  side?: string;
}

function fmtLine(line: number): string {
  return line > 0 ? `+${line}` : `${line}`;
}

export function BookShoppingRow({ books, side }: BookShoppingRowProps) {
  if (!books || books.length === 0) {
    return <Unavailable reason="no book lines available" />;
  }

  return (
    <ul
      className="flex flex-wrap gap-2"
      aria-label={`Book lines${side ? ` for ${side}` : ""}`}
    >
      {books.map((entry, i) => {
        const oddsStr = fmtDecimalOdds(entry.odds);
        const ariaLabel = [
          entry.book,
          entry.line != null ? `line ${fmtLine(entry.line)}` : null,
          `odds ${oddsStr}`,
          entry.is_best ? "best available line" : null,
        ]
          .filter(Boolean)
          .join(", ");

        return (
          <li key={`${entry.book}-${i}`}>
            <span
              role="img"
              aria-label={ariaLabel}
              className={cn(
                "inline-flex flex-col items-center gap-0.5 border px-2.5 py-1.5",
                entry.is_best
                  ? "border-border bg-surface-3"
                  : "border-border bg-surface-2",
              )}
              data-testid={entry.is_best ? "best-book-pill" : "book-pill"}
            >
              {/* Book name + optional best label on the same row */}
              <span className="flex items-center gap-1">
                <span
                  className={cn(
                    "font-data text-[9px] uppercase tracking-widest",
                    entry.is_best ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {entry.book}
                </span>
                {entry.is_best && (
                  <span
                    className="bg-surface-3 px-1 font-data text-[8px] font-bold uppercase tracking-wide text-foreground"
                    aria-hidden="true"  /* spoken via the parent aria-label */
                  >
                    best
                  </span>
                )}
              </span>

              {/* Odds */}
              <span
                className={cn(
                  "font-data tabular text-xs font-semibold leading-none",
                  entry.is_best ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {oddsStr}
              </span>

              {/* Line (spread / total), if provided */}
              {entry.line != null ? (
                <span className="font-data text-[10px] leading-none text-muted-foreground">
                  {fmtLine(entry.line)}
                </span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
