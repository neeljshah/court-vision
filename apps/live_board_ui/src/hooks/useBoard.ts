import { useCallback, useEffect, useRef, useState } from "react";
import { fetchBoard } from "@/lib/api";
import type { BoardResponse, Sport } from "@/types/board";

const POLL_MS = 25_000;

export interface UseBoardResult {
  data: BoardResponse | null;
  error: string | null;
  loading: boolean; // first load / sport switch (no data yet)
  refreshing: boolean; // background poll with data already on screen
  lastUpdated: string | null;
  refresh: () => void;
}

/**
 * Polls /api/board every 25s for the active sport/league. Keeps the previous
 * payload visible during refreshes (no flicker), cancels in-flight requests on
 * sport/league switch, and surfaces a retryable error without blanking the board.
 */
export function useBoard(sport: Sport, leagues?: string): UseBoardResult {
  const [data, setData] = useState<BoardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const sportRef = useRef(sport);
  sportRef.current = sport;

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
    return () => {
      window.clearInterval(id);
      abortRef.current?.abort();
    };
  }, [load]);

  return {
    data,
    error,
    loading: data === null && error === null,
    refreshing,
    lastUpdated: data?.generated_at ?? null,
    refresh: load,
  };
}
