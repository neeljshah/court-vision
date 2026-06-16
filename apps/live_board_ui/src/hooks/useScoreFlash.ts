/**
 * Detects score changes between renders and returns the set of gameKeys
 * currently within the flash window (matches the CSS score-flash duration).
 */
import { useEffect, useRef, useState } from "react";
import type { BoardRow } from "@/types/board";
import { gameKey } from "@/lib/gameKey";

/** Signature captures both scores as a comparable string. */
function scoreSig(r: BoardRow): string {
  return `${r.away_score}|${r.home_score}`;
}

/** Returns true when both scores are non-null (skip pre-game rows). */
function hasScore(r: BoardRow): boolean {
  return r.away_score !== null && r.home_score !== null;
}

// Keep in sync with the tailwind "score-flash" animation duration (1.6s).
const FLASH_MS = 1600;

/**
 * useScoreFlash
 *
 * Tracks score signatures across renders. When a row's score changes from a
 * previously seen value the gameKey is added to the returned Set for FLASH_MS,
 * then removed. Initial appearance of a key never triggers a flash so that the
 * first load does not light up every in-progress game.
 *
 * @param rows - Current board rows from the polling hook.
 * @returns Set<string> of gameKeys whose score recently changed.
 */
export function useScoreFlash(rows: BoardRow[]): Set<string> {
  // Last-seen score signatures keyed by gameKey.
  const sigsRef = useRef<Map<string, string>>(new Map());
  // Active timeout ids so we can cancel on unmount.
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const [flashing, setFlashing] = useState<Set<string>>(new Set());

  useEffect(() => {
    const newlyFlashing: string[] = [];

    for (const row of rows) {
      if (!hasScore(row)) continue;

      const key = gameKey(row);
      const sig = scoreSig(row);
      const prev = sigsRef.current.get(key);

      if (prev === undefined) {
        // First time seeing this key -- record but do not flash.
        sigsRef.current.set(key, sig);
      } else if (prev !== sig) {
        // Score changed since last render.
        sigsRef.current.set(key, sig);
        newlyFlashing.push(key);
      }
    }

    if (newlyFlashing.length === 0) return;

    // Add all newly flashing keys to state.
    setFlashing((prev) => {
      const next = new Set(prev);
      for (const k of newlyFlashing) next.add(k);
      return next;
    });

    // Schedule removal for each key independently.
    for (const key of newlyFlashing) {
      // Cancel any existing timer for this key before starting a new one.
      const existing = timersRef.current.get(key);
      if (existing !== undefined) clearTimeout(existing);

      const id = setTimeout(() => {
        setFlashing((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
        timersRef.current.delete(key);
      }, FLASH_MS);

      timersRef.current.set(key, id);
    }
  }, [rows]); // eslint-disable-line react-hooks/exhaustive-deps

  // Clear all pending timers on unmount.
  useEffect(() => {
    return () => {
      for (const id of timersRef.current.values()) clearTimeout(id);
    };
  }, []);

  return flashing;
}
