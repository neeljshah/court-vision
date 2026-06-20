"use client";

// BookMatrixTable.tsx -- per-market, per-book odds matrix for a game.
//
// Reads a LinesMatrix (W1 endpoint) and renders a sortable table of every
// book's quote for each market side, highlighting the best line. There is NO
// $ column -- odds are decimal prices, not payouts. A missing quote renders
// as "--" (never a guessed price). clv_is_proxy is shown honestly.
//
// HONESTY RAILS: odds/lines/prices are fine. NO $ payout/profit field.
// Best line is the highest decimal odds across books (lower vig = better).

import * as React from "react";
import { cn } from "@/lib/utils";
import type { LinesMatrix, MarketMatrix, BookQuote, BestLineSide } from "@/lib/p5api_ext";
import { isExtUnavailable } from "@/lib/p5api_ext";
import { Unavailable } from "@/components/honest/HonestState";
import { Panel } from "@/components/p6/Primitives";

export interface BookMatrixTableProps {
  matrix: LinesMatrix | null;
  className?: string;
}

// Format a decimal odds price (never a $ figure).
function fmtOdds(o: number | null | undefined): string {
  if (o == null || !Number.isFinite(o)) return "--";
  return o.toFixed(2);
}

function fmtLine(l: number | null | undefined): string {
  if (l == null || !Number.isFinite(l)) return "";
  return ` (${l > 0 ? "+" : ""}${l})`;
}

// Gather all unique books across all market sides.
function allBooks(m: MarketMatrix): string[] {
  const s = new Set<string>();
  for (const quotes of Object.values(m.sides)) {
    for (const q of quotes) s.add(q.book);
  }
  return [...s].sort();
}

// Find the best quote (highest decimal odds) for a side.
function bestBook(best: Record<string, BestLineSide>, side: string): string {
  return best[side]?.book ?? "";
}

function QuoteCell({
  quote,
  isBest,
}: {
  quote: BookQuote | undefined;
  isBest: boolean;
}) {
  if (!quote) {
    return (
      <td className="px-2 py-1.5 text-right font-mono text-xs text-slate-600">
        --
      </td>
    );
  }
  return (
    <td
      className={cn(
        "px-2 py-1.5 text-right font-mono text-xs tabular-nums",
        isBest ? "font-semibold text-emerald-400" : "text-slate-300",
      )}
      title={quote.captured_at ? `captured ${quote.captured_at}` : undefined}
    >
      {fmtOdds(quote.odds)}
      {fmtLine(quote.line)}
      {quote.is_pm && (
        <span className="ml-1 text-[9px] text-purple-400">PM</span>
      )}
    </td>
  );
}

function MarketBlock({
  mType,
  m,
}: {
  mType: string;
  m: MarketMatrix;
}) {
  const books = allBooks(m);
  const sides = Object.keys(m.sides);

  return (
    <div className="mb-4">
      <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-slate-500">
        {mType}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs" role="table">
          <thead>
            <tr>
              <th className="py-1 pr-3 text-left text-[10px] font-medium uppercase tracking-wide text-slate-500">
                side
              </th>
              {books.map((b) => (
                <th
                  key={b}
                  className="px-2 py-1 text-right text-[10px] font-medium uppercase tracking-wide text-slate-500"
                >
                  {b}
                </th>
              ))}
              <th className="px-2 py-1 text-right text-[10px] font-medium uppercase tracking-wide text-slate-500">
                best
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {sides.map((side) => {
              const quotes = m.sides[side] ?? [];
              const byBook = Object.fromEntries(quotes.map((q) => [q.book, q]));
              const bestBk = bestBook(m.best, side);
              return (
                <tr key={side}>
                  <td className="py-1.5 pr-3 text-slate-400">{side}</td>
                  {books.map((b) => (
                    <QuoteCell
                      key={b}
                      quote={byBook[b]}
                      isBest={bestBk === b}
                    />
                  ))}
                  <td className="px-2 py-1.5 text-right font-mono text-[10px] text-slate-500">
                    {bestBk ? (
                      <span className="rounded border border-emerald-900/50 bg-emerald-950/20 px-1 py-0.5 text-emerald-400">
                        {bestBk}
                      </span>
                    ) : (
                      "--"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Per-market, per-book odds matrix (no $ -- decimal odds only). */
export function BookMatrixTable({ matrix, className }: BookMatrixTableProps) {
  if (!matrix) {
    return (
      <Panel title="Book lines" className={className}>
        <p className="text-xs text-slate-600">Loading lines...</p>
      </Panel>
    );
  }

  if (isExtUnavailable(matrix) || matrix.status === "unavailable") {
    return (
      <Panel title="Book lines" className={className}>
        <Unavailable reason={(matrix as { reason?: string }).reason ?? "lines feed unavailable"} />
      </Panel>
    );
  }

  const mTypes = Object.keys(matrix.markets ?? {});
  const isEmpty = mTypes.length === 0;

  return (
    <Panel
      title="Book lines"
      right={
        <span className="font-mono text-[10px] text-slate-500">
          odds only -- no $
        </span>
      }
      className={className}
    >
      {isEmpty ? (
        <p className="text-xs text-slate-600">
          No lines captured for this game yet.
        </p>
      ) : (
        mTypes.map((mt) => (
          <MarketBlock key={mt} mType={mt} m={matrix.markets[mt]} />
        ))
      )}
      <p className="mt-2 text-[10px] text-slate-600">
        Green = best decimal odds (lowest vig) at last capture.
        Decimal odds are prices, not payouts. No $ column.
      </p>
    </Panel>
  );
}
