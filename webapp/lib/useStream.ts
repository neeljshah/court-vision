"use client";

import { useEffect, useRef, useState } from "react";

// StreamMode now includes an explicit "disconnected" state: live (sse) AND the
// poll fallback have BOTH failed to yield data. A panel must render an honest
// "live feed unavailable" instead of freezing the last frame as if it were live.
export type StreamMode = "sse" | "poll" | "disconnected" | "idle";

// useStream -- subscribe to an SSE endpoint that re-emits a JSON payload.
// Falls back to polling `pollFn` every `pollMs` if EventSource errors or is
// unavailable. Always returns the latest payload (or null) plus the live mode.
// The connection state is HONEST: when the poll fallback itself keeps failing
// (with no data ever received) the mode becomes "disconnected" so the UI can
// say "live feed unavailable" rather than presenting a frozen panel as live.
export function useStream<T>(opts: {
  sseUrl?: string;
  pollFn: (signal: AbortSignal) => Promise<T>;
  pollMs?: number;
  enabled?: boolean;
}): { data: T | null; mode: StreamMode; updatedAt: number | null } {
  const { sseUrl, pollFn, pollMs = 5000, enabled = true } = opts;
  const [data, setData] = useState<T | null>(null);
  const [mode, setMode] = useState<StreamMode>("idle");
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const pollFnRef = useRef(pollFn);
  pollFnRef.current = pollFn;

  useEffect(() => {
    if (!enabled) return;
    let es: EventSource | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let abort: AbortController | null = null;
    let cancelled = false;

    // Track consecutive poll failures so we can flip to an HONEST "disconnected"
    // mode instead of silently presenting a frozen/last-good frame as live.
    let consecutiveFailures = 0;
    const DISCONNECT_AFTER = 2; // two failed polls in a row -> honest disconnect

    // A pollFn may either throw OR resolve to the honest Unavailable sentinel
    // ({status:"unavailable"}). Treat BOTH as a failed poll so a degraded backend
    // never reads as a fresh live frame.
    const isUnavailablePayload = (p: unknown): boolean =>
      !!p &&
      typeof p === "object" &&
      (p as { status?: string }).status === "unavailable";

    const apply = (payload: T): boolean => {
      if (cancelled) return false;
      if (isUnavailablePayload(payload)) return false;
      consecutiveFailures = 0;
      setData(payload);
      setUpdatedAt(Date.now());
      return true;
    };

    const startPolling = () => {
      if (pollTimer) return;
      setMode((m) => (m === "disconnected" ? m : "poll"));
      const tick = async () => {
        abort?.abort();
        abort = new AbortController();
        let ok = false;
        try {
          ok = apply(await pollFnRef.current(abort.signal));
        } catch {
          ok = false;
        }
        if (cancelled) return;
        if (ok) {
          setMode("poll");
          return;
        }
        // leave last-good data; the connection is degraded. After a couple of
        // failures in a row, surface an honest "disconnected" so the panel can
        // say the live feed is unavailable rather than freeze as live.
        consecutiveFailures += 1;
        if (consecutiveFailures >= DISCONNECT_AFTER) setMode("disconnected");
      };
      void tick();
      pollTimer = setInterval(tick, pollMs);
    };

    const startSse = () => {
      try {
        es = new EventSource(sseUrl as string);
      } catch {
        startPolling();
        return;
      }
      es.onopen = () => setMode("sse");
      es.onmessage = (ev) => {
        try {
          apply(JSON.parse(ev.data) as T);
        } catch {
          /* ignore malformed frame */
        }
      };
      es.onerror = () => {
        es?.close();
        es = null;
        startPolling(); // graceful degrade -- never a guessed number
      };
    };

    if (sseUrl && typeof EventSource !== "undefined") startSse();
    else startPolling();

    return () => {
      cancelled = true;
      es?.close();
      abort?.abort();
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [sseUrl, pollMs, enabled]);

  return { data, mode, updatedAt };
}
