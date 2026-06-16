/** Pure filter helper: narrows BoardRow[] by live-state and/or team-name text query. No sorting. */

import type { BoardRow } from "@/types/board";

export function filterRows(
  rows: BoardRow[],
  query: string,
  liveOnly: boolean
): BoardRow[] {
  const trimmed = query.trim().toLowerCase();

  return rows.filter((row) => {
    if (liveOnly && row.state !== "in") return false;
    if (trimmed.length > 0) {
      const matchHome = row.home.toLowerCase().includes(trimmed);
      const matchAway = row.away.toLowerCase().includes(trimmed);
      if (!matchHome && !matchAway) return false;
    }
    return true;
  });
}
