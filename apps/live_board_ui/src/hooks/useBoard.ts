import { useCallback, useEffect, useRef, useState } from "react";
import { fetchBoard } from "@/lib/api";
import type { BoardResponse, Sport } from "@/types/board";

const POLL_MS = 25_000;
const STALE_MS = 90_000;
const TICK_MS = 15_000;

export interface UseBoardResult {
  data: BoardResponse | null;
  error: string | null;
  loading: boolean; // first load / sport switch (no data yet)
  refreshing: boolean; // background poll with data already on screen
  lastUpdated: string | null;
  refresh: () => void;
  stale: boolean; // true when data exists and generated_at is >90s old
}

/**
 * Polls /api/board every 25s for the active sport/league. Keeps the previous
 * payload visible during refreshes (no flicker), cancels in-flight requests on
 * sport/league switch, and surfaces a retryable error without blanking the board.
 * Adds a 15s tick to flip `stale` without a new fetch, and pauses polling while
 * the document is hidden (resumes + refreshes immediately on visibility restore).
 */
export function useBoard(sport: Sport, leagues?: string): UseBoardResult {
  const [data, setData] = useState<BoardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const abortRef = useRef<AbortController | null>(null);
  const sportRef = useRef(sport);
  sportRef.current = sport;
  // Ref to the 25s poll interval so the visibility handler can clear/restart it.
  const pollIdRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setRefreshing(true);
    try {
      const res = await fetchBoard(sport, leagues, ctrl.signal);
      if (ctrl.signal.aborted || res.sport !== sportRef.current) return;
      setData(res);
      setError(null);
    } catch (err) {
      if (ctrl.signal.aborted) return;
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      if (!ctrl.signal.aborted) setRefreshing(false);
    }
  }, [sport, leagues]);

  // Reset visible data immediately on sport/league change, then poll.
  useEffect(() => {
    setData(null);
    setError(null);
    load();
    const id = window.setInterval(load, POLL_MS);
    pollIdRef.current = id;
    return () => {
      // Clear whatever interval is currently live via the ref -- a hide/show
      // cycle may have replaced the original `id` with a new one, and closing
      // over the stale `id` here would leak the resume-created interval.
      if (pollIdRef.current !== null) {
        window.clearInterval(pollIdRef.current);
        pollIdRef.current = null;
      }
      abortRef.current?.abort();
    };
  }, [load]);

  // 15s tick to keep `now` fresh so `stale` flips without a new fetch.
  useEffect(() => {
    const tickId = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(tickId);
  }, []);

  // Visibility-aware polling: pause the 25s interval while hidden; on return to
  // visible, refresh immediately and restart the interval. SSR-safe guard.
  useEffect(() => {
    if (typeof document === "undefined") return;

    const handleVisibility = () => {
      if (document.hidden) {
        // Pause: clear the running poll interval.
        if (pollIdRef.current !== null) {
          window.clearInterval(pollIdRef.current);
          pollIdRef.current = null;
        }
      } else {
        // Resume: refresh now, then reinstall the interval.
        load();
        if (pollIdRef.current === null) {
          const id = window.setInterval(load, POLL_MS);
          pollIdRef.current = id;
        }
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [load]);

  // Compute stale: true only when data exists and generated_at is >90s behind now.
  const stale: boolean = (() => {
    if (!data || !data.generated_at) return false;
    const ts = Date.parse(data.generated_at);
    if (isNaN(ts)) return false;
    return now - ts > STALE_MS;
  })();

  return {
    data,
    error,
    loading: data === null && error === null,
    refreshing,
    lastUpdated: data?.generated_at ?? null,
    refresh: load,
    stale,
  };
}
