import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSlate, type SlatePayload } from "@/lib/api";

const POLL_MS = 30_000;

export interface UseSlateState {
  data: SlatePayload | null;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  reload: () => void;
}

/** Fetch the slate for a sport, with an optional 30s auto-poll. Shared by every screen. */
export function useSlate(sport: string, autoPoll: boolean): UseSlateState {
  const [data, setData] = useState<SlatePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const timer = useRef<number | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchSlate(sport)
      .then((payload) => {
        setData(payload);
        setLastUpdated(new Date());
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [sport]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    if (timer.current) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
    if (autoPoll) {
      timer.current = window.setInterval(reload, POLL_MS);
    }
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [autoPoll, reload]);

  return { data, loading, error, lastUpdated, reload };
}
