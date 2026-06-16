/** Stable per-game identifier that survives polling and row re-sorting. */
import type { BoardRow } from "@/types/board";

/**
 * Returns a string key unique per game across sports and leagues.
 * Composed of: sport | league | away | home | start_time.
 * Pure function -- no side effects.
 */
export function gameKey(r: BoardRow): string {
  return `${r.sport}|${r.league}|${r.away}|${r.home}|${r.start_time ?? ""}`;
}
