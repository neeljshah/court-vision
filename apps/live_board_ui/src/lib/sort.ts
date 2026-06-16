/**
 * Sort modes and section-level sorter for the live board.
 * Operates on ONE state-homogeneous section at a time (live/upcoming/finished).
 */

import type { BoardRow } from "@/types/board";
import { hasPrediction } from "@/lib/format";

export type SortMode = "default" | "favorite" | "soonest";

export const SORT_OPTIONS: { value: SortMode; label: string }[] = [
  { value: "default", label: "Default" },
  { value: "favorite", label: "Biggest favorite" },
  { value: "soonest", label: "Starting soonest" },
];

/** Parse an ISO start_time to a numeric epoch, or Infinity when absent. */
function startMs(r: BoardRow): number {
  if (!r.start_time) return Infinity;
  const t = Date.parse(r.start_time);
  return Number.isNaN(t) ? Infinity : t;
}

/**
 * Sorts one already-state-homogeneous section of board rows.
 * Returns a new array; never mutates the input.
 *
 * "default"  -- predicted rows first, then start_time asc (mirrors sortRows).
 * "favorite" -- highest favorite probability desc; no-prob rows sink; tie -> start_time asc.
 * "soonest"  -- start_time asc (missing = last); tie -> predicted first, then home name asc.
 */
export function sortSection(rows: BoardRow[], mode: SortMode): BoardRow[] {
  const copy = rows.slice();

  if (mode === "default") {
    return copy.sort((a, b) => {
      const pa = hasPrediction(a) ? 0 : 1;
      const pb = hasPrediction(b) ? 0 : 1;
      if (pa !== pb) return pa - pb;
      return startMs(a) - startMs(b);
    });
  }

  if (mode === "favorite") {
    return copy.sort((a, b) => {
      const fa =
        a.win_home !== null || a.win_away !== null
          ? Math.max(a.win_home ?? -1, a.win_away ?? -1)
          : null;
      const fb =
        b.win_home !== null || b.win_away !== null
          ? Math.max(b.win_home ?? -1, b.win_away ?? -1)
          : null;
      // Rows with no probs sink to the bottom
      if (fa === null && fb === null) return startMs(a) - startMs(b);
      if (fa === null) return 1;
      if (fb === null) return -1;
      if (fb !== fa) return fb - fa; // DESC by favorite probability
      return startMs(a) - startMs(b);
    });
  }

  // mode === "soonest"
  return copy.sort((a, b) => {
    const ta = startMs(a);
    const tb = startMs(b);
    if (ta !== tb) return ta - tb;
    const pa = hasPrediction(a) ? 0 : 1;
    const pb = hasPrediction(b) ? 0 : 1;
    if (pa !== pb) return pa - pb;
    return a.home.localeCompare(b.home);
  });
}
