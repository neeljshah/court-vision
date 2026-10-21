"use client";

// useLiveData -- canonical shared live-polling primitive for every panel.
//
// Contract: { data, lastUpdatedAt, ageSec, isStale, error, isLoading,
//             consecutiveFailures, backoffActive, refresh }
//
// Robustness rails:
//   - NEVER throws. Failed poll keeps last-good data + sets isStale/error.
//   - Unavailable sentinel ({ status:"unavailable" }) -> last-good retained.
//   - Exponential backoff on consecutive failures: delay = intervalMs * 2^(f-1)
//     capped at maxBackoffMultiplier*intervalMs (default 5x). First success resets.
//   - consecutiveFailures + backoffActive exposed for honest "backing off" badge.
//   - Pauses polling when document.hidden; resumes + refetches on visibility.
//   - ageSec ticks every ~1 s via a separate interval (no extra fetches).
//   - isStale flips true when ageSec > staleAfterSec.
//   - Cleans up timeout + visibilitychange listener on unmount.
//   - Server seed: initialData (+ initialUpdatedAt) starts the hook with data and
//     isLoading=false so server-rendered HTML carries the values; the first fetch
//     and polling are unchanged. Age/stale stamps are applied after mount.
//   - Snapshot build (NEXT_PUBLIC_DATA_MODE=snapshot): one load, no re-poll, so the
//     first answer ends isLoading even when it is the Unavailable sentinel, and the
//     age ticker is off (baked data never flips to STALE on the viewer's clock).

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchHonest, isSnapshotMode } from "./fetchHonest";
import type { Unavailable } from "./types";
import { backoffDelay, isUnavailableSentinel, lkvGet, lkvPut } from "./liveDataSupport";
import type { LiveDataState, UseLiveDataOptions } from "./liveDataSupport";

// The public contract and the backoff helper live in liveDataSupport.ts; re-exported
// here so every existing `from "@/lib/useLiveData"` import keeps working.
export { backoffDelay } from "./liveDataSupport";
export type { LiveDataState, UseLiveDataOptions } from "./liveDataSupport";

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useLiveData<T>(
  fetcher: (signal: AbortSignal) => Promise<T | Unavailable>,
  options: UseLiveDataOptions<T> = {},
): LiveDataState<T> {
  const {
    intervalMs = 20_000,
    staleAfterSec = 60,
    timeoutMs = 8_000,
    enabled = true,
    maxBackoffMultiplier = 5,
    cacheKey,
    initialData,
    initialUpdatedAt,
  } = options;

  // Seeded start (see UseLiveDataOptions.initialData): data present, not loading.
  const hasInitial = initialData !== undefined;
  const seedUpdatedAt = hasInitial ? initialUpdatedAt ?? null : null;

  const [data, setData] = useState<T | null>(initialData === undefined ? null : initialData);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(seedUpdatedAt);
  const [ageSec, setAgeSec] = useState<number | null>(null);
  const [isStale, setIsStale] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(!hasInitial);
  const [consecutiveFailures, setConsecutiveFailures] = useState(0);

  // Stable refs -- avoid re-registering effects on option changes.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const timeoutMsRef = useRef(timeoutMs);
  timeoutMsRef.current = timeoutMs;
  const staleAfterSecRef = useRef(staleAfterSec);
  staleAfterSecRef.current = staleAfterSec;
  const intervalMsRef = useRef(intervalMs);
  intervalMsRef.current = intervalMs;
  const maxBackoffMultiplierRef = useRef(maxBackoffMultiplier);
  maxBackoffMultiplierRef.current = maxBackoffMultiplier;

  const cacheKeyRef = useRef(cacheKey);
  cacheKeyRef.current = cacheKey;

  // Seed from the last-known value AFTER mount (client only) so navigation
  // paints instantly without an SSR hydration mismatch: the server always
  // renders the loading state; the very first client effect swaps in the
  // cached payload with its ORIGINAL timestamp (age/stale stay truthful).
  useEffect(() => {
    if (!cacheKey || hasInitial) return;
    // Test env: never seed -- suites assert on genuine loading states, and the
    // module-level cache would leak "instant data" across tests in a file.
    if (typeof process !== "undefined" && process.env.NODE_ENV === "test") return;
    const seed = lkvGet(cacheKey);
    if (seed === null || lastUpdatedAtRef.current !== null) return;
    const seedAge = (Date.now() - seed.ts) / 1000;
    lastUpdatedAtRef.current = seed.ts;
    setData(seed.data as T);
    setLastUpdatedAt(seed.ts);
    setAgeSec(Math.round(seedAge));
    setIsStale(seedAge > staleAfterSecRef.current);
    setIsLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey]);

  // Seeded payload: stamp its age/stale AFTER mount. Date.now() differs between
  // the server render and hydration, so the stamp must not enter the first render.
  useEffect(() => {
    if (seedUpdatedAt === null) return;
    const seedAge = (Date.now() - seedUpdatedAt) / 1000;
    setAgeSec(Math.round(seedAge));
    setIsStale(seedAge > staleAfterSecRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const abortRef = useRef<AbortController | null>(null);
  const lastUpdatedAtRef = useRef<number | null>(seedUpdatedAt);
  const consecutiveFailuresRef = useRef(0);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingActiveRef = useRef(false);

  // Forward ref for scheduleNextPoll (runFetch calls it after completion).
  const scheduleNextPollRef = useRef<() => void>(() => { /* set below */ });

  const stopPolling = useCallback(() => {
    pollingActiveRef.current = false;
    if (pollTimeoutRef.current !== null) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
  }, []);

  // Core fetch tick -- does NOT self-schedule; called by timeout and refresh.
  const runFetch = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    let result: T | Unavailable;
    try {
      result = await fetcherRef.current(ctrl.signal);
    } catch {
      result = { status: "unavailable", reason: "fetcher threw" };
    }

    if (ctrl.signal.aborted) return;

    if (isUnavailableSentinel(result)) {
      const reason = (result as Unavailable).reason ?? "unavailable";
      const newFailures = consecutiveFailuresRef.current + 1;
      consecutiveFailuresRef.current = newFailures;
      setConsecutiveFailures(newFailures);
      setError(reason);
      setIsStale(true);
      // Snapshot build: there is no retry (scheduleNextPoll returns), so the first answer
      // ends the loading state even when it is the sentinel; live keeps the skeleton until
      // a success because a re-poll is coming.
      setIsLoading((prev) => (isSnapshotMode || lastUpdatedAtRef.current !== null ? false : prev));
    } else {
      consecutiveFailuresRef.current = 0;
      setConsecutiveFailures(0);
      const now = Date.now();
      lastUpdatedAtRef.current = now;
      if (cacheKeyRef.current) lkvPut(cacheKeyRef.current, result, now);
      setData(result as T);
      setLastUpdatedAt(now);
      setAgeSec(0);
      setIsStale(false);
      setError(null);
      setIsLoading(false);
    }

    // Re-arm with appropriate (possibly backed-off) delay after each fetch.
    if (pollingActiveRef.current) {
      scheduleNextPollRef.current();
    }
  }, []); // stable -- all mutable values accessed via refs

  // Schedule the next poll with the current backoff delay.
  const scheduleNextPoll = useCallback(() => {
    if (pollTimeoutRef.current !== null) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    if (!pollingActiveRef.current) return;
    // Snapshot demo build: single load, no re-poll -- there is no live backend.
    // The baked "generated_at" in the snapshot payload is the honest asOf stamp.
    if (isSnapshotMode) return;
    const delay = backoffDelay(
      intervalMsRef.current,
      consecutiveFailuresRef.current,
      maxBackoffMultiplierRef.current,
    );
    pollTimeoutRef.current = setTimeout(() => {
      if (!document.hidden && pollingActiveRef.current) {
        void runFetch();
      } else if (pollingActiveRef.current) {
        // Tab hidden: re-arm so we keep checking. visibilitychange will re-fetch.
        scheduleNextPollRef.current();
      }
    }, delay);
  }, [runFetch]);

  scheduleNextPollRef.current = scheduleNextPoll;

  // Exposed stable refresh: abort in-flight, fetch immediately.
  const refresh = useCallback(() => {
    if (pollTimeoutRef.current !== null) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    void runFetch();
  }, [runFetch]);

  // Main effect: initial fetch + visibilitychange listener.
  // runFetch arms the next scheduled poll after each fetch completes.
  useEffect(() => {
    if (!enabled) return;
    pollingActiveRef.current = true;
    void runFetch();

    const onVisibilityChange = () => {
      if (!document.hidden) {
        // Tab visible: cancel pending (backoff) timer, fetch immediately.
        if (pollTimeoutRef.current !== null) {
          clearTimeout(pollTimeoutRef.current);
          pollTimeoutRef.current = null;
        }
        void runFetch();
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      stopPolling();
      abortRef.current?.abort();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [enabled, runFetch, stopPolling]);

  // Age ticker: increments ageSec ~every 1 s without triggering a fetch. Off in a
  // snapshot build: the baked payload cannot refresh, so counting the viewer's seconds
  // since the single load would flip honest baked data to STALE after staleAfterSec.
  useEffect(() => {
    if (isSnapshotMode) return;
    const ticker = setInterval(() => {
      const lu = lastUpdatedAtRef.current;
      if (lu === null) return;
      const age = (Date.now() - lu) / 1000;
      setAgeSec(Math.round(age));
      setIsStale(age > staleAfterSecRef.current);
    }, 1_000);
    return () => clearInterval(ticker);
  }, []); // mount-once; reads mutable values via refs

  return {
    data,
    lastUpdatedAt,
    ageSec,
    isStale,
    error,
    isLoading,
    consecutiveFailures,
    backoffActive: consecutiveFailures > 0,
    refresh,
  };
}

// ---------------------------------------------------------------------------
// Convenience wrapper: useLiveDataUrl
// ---------------------------------------------------------------------------

export function useLiveDataUrl<T>(
  url: string,
  options: UseLiveDataOptions<T> = {},
): LiveDataState<T> {
  const fetcher = useCallback(
    (signal: AbortSignal) =>
      fetchHonest<T>(url, { signal, timeoutMs: options.timeoutMs }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [url, options.timeoutMs],
  );
  return useLiveData<T>(fetcher, options);
}
