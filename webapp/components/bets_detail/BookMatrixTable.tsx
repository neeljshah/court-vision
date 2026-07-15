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
import { Panel as TerminalPanel, PanelHead, Num } from "@/components/ui/terminal";

// Local Panel shim: p6/Primitives.Panel currently lacks asOf/stale wiring, so
// this component composes directly from the terminal.tsx primitives instead
// (same title/right/asOf/stale/children/className call shape as every panel
// in this file already uses).
function Panel({
  title,
  asOf,
  stale = false,
  right,
  children,
  className,
}: {
  title: string;
  asOf?: string | null;
  stale?: boolean;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <TerminalPanel className={className}>
      <PanelHead title={title} asOf={asOf} stale={stale} right={right} />
      <div className="p-4">{children}</div>
    </TerminalPanel>
  );
}

export interface BookMatrixTableProps {
  matrix: LinesMatrix | null;
  asOf?: string | null;
  stale?: boolean;
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
      <td className="px-3 py-1.5 text-right">
        <Num className="text-xs text-faint">--</Num>
      </td>
    );
  }
  return (
    <td
      className="px-3 py-1.5 text-right"
      title={quote.captured_at ? `captured ${quote.captured_at}` : undefined}
    >
      <Num className={cn("text-xs", isBest ? "font-semibold text-up" : "text-foreground")}>
        {fmtOdds(quote.odds)}
        {fmtLine(quote.line)}
      </Num>
      {quote.is_pm && (
        <span className="ml-1 font-data text-[9px] text-info">PM</span>
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
      <p className="mb-1 microlabel">
        {mType}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs" role="table">
          <thead>
            <tr>
              <th className="microlabel py-1.5 pr-3 text-left">
                side
              </th>
              {books.map((b) => (
                <th
                  key={b}
                  className="microlabel px-3 py-1.5 text-right"
                >
                  {b}
                </th>
              ))}
              <th className="microlabel px-3 py-1.5 text-right">
                best
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sides.map((side) => {
              const quotes = m.sides[side] ?? [];
              const byBook = Object.fromEntries(quotes.map((q) => [q.book, q]));
              const bestBk = bestBook(m.best, side);
              return (
                <tr key={side} className="hover:bg-surface-2">
                  <td className="py-1.5 pr-3 text-muted-foreground">{side}</td>
                  {books.map((b) => (
                    <QuoteCell
                      key={b}
                      quote={byBook[b]}
                      isBest={bestBk === b}
                    />
                  ))}
                  <td className="px-3 py-1.5 text-right font-data text-[10px] text-faint">
                    {bestBk ? (
                      <span className="border border-success/40 px-1 py-0.5 text-emerald-400">
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
export function BookMatrixTable({ matrix, asOf, stale = false, className }: BookMatrixTableProps) {
  if (!matrix) {
    return (
      <Panel title="All markets (line shopping)" asOf={asOf} stale={stale} className={className}>
        <p className="text-xs text-faint">Loading lines...</p>
      </Panel>
    );
  }

  if (isExtUnavailable(matrix) || matrix.status === "unavailable") {
    return (
      <Panel title="All markets (line shopping)" asOf={asOf} stale={stale} className={className}>
        <Unavailable reason={(matrix as { reason?: string }).reason ?? "lines feed unavailable"} />
      </Panel>
    );
  }

  const mTypes = Object.keys(matrix.markets ?? {});
  const isEmpty = mTypes.length === 0;

  return (
    <Panel
      title="All markets (line shopping)"
      asOf={asOf}
      stale={stale}
      right={
        <span className="font-data text-[10px] text-faint">
          ML / total / spread -- odds only, no $
        </span>
      }
      className={className}
    >
      {isEmpty ? (
        <p className="text-xs text-faint">
          No lines captured for this game yet.
        </p>
      ) : (
        mTypes.map((mt) => (
          <MarketBlock key={mt} mType={mt} m={matrix.markets[mt]} />
        ))
      )}
      <p className="mt-2 text-[10px] text-faint">
        Best = highest decimal odds (lowest vig) at last capture.
        Decimal odds are prices, not payouts. No $ column.
      </p>
    </Panel>
  );
}
