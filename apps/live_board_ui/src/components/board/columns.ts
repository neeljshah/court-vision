// Shared column-visibility contract: single source of truth for which optional
// columns (Odds, Total) are shown, and the responsive grid-template-columns
// string used by both the header bar and BoardRowItem's desktop grid.
import type { BoardRow } from "@/types/board";

export interface ColumnVis {
  odds: boolean;
  total: boolean;
}

/** Derive which optional columns should appear from the live row set. */
export function computeColumns(rows: BoardRow[]): ColumnVis {
  const odds = rows.some(
    (r) => r.market_odds != null && String(r.market_odds).trim() !== ""
  );
  const total = rows.some(
    (r) => r.total != null && !Number.isNaN(r.total)
  );
  return { odds, total };
}

/**
 * Returns a Tailwind md:grid-cols-[...] utility whose tracks match:
 * Status 110px, Matchup minmax(180px,1fr), Score 90px, Win% 150px,
 * [Odds 110px], [Total 70px], Source 110px, Updated 90px.
 *
 * IMPORTANT: these are returned as full LITERAL class strings (one per combo)
 * rather than built by interpolation -- Tailwind's JIT only generates arbitrary
 * grid-template classes it can find verbatim in source. A dynamically assembled
 * string is never emitted and the grid silently collapses to flow layout.
 */
export function rowGridClass(c: ColumnVis): string {
  if (c.odds && c.total)
    return "md:grid-cols-[110px_minmax(180px,1fr)_90px_150px_110px_70px_110px_90px]";
  if (c.odds)
    return "md:grid-cols-[110px_minmax(180px,1fr)_90px_150px_110px_110px_90px]";
  if (c.total)
    return "md:grid-cols-[110px_minmax(180px,1fr)_90px_150px_70px_110px_90px]";
  return "md:grid-cols-[110px_minmax(180px,1fr)_90px_150px_110px_90px]";
}
