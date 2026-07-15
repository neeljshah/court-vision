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

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchHonest } from "./fetchHonest";
import type { Unavailable } from "./types";

// ---------------------------------------------------------------------------
// Public contract
// ---------------------------------------------------------------------------

export interface LiveDataState<T> {
  /** Last successfully fetched data (null until first success). */
  data: T | null;
  /** Timestamp (Date.now()) of the last successful poll. null before first success. */
  lastUpdatedAt: number | null;
  /** Seconds since last successful poll. null before first success. */
  ageSec: number | null;
  /** True when ageSec exceeds staleAfterSec. */
  isStale: boolean;
  /** Error message from the most recent failed poll. null when last poll succeeded. */
  error: string | null;
  /** True only during the very first load (no data yet, no prior good state). */
  isLoading: boolean;
  /**
   * Number of consecutive failed polls since the last success (0 = no backoff).
   * Exposed so badges/consumers can show an honest "backing off" hint.
   */
  consecutiveFailures: number;
  /** True when consecutiveFailures > 0 (backoff actively in effect). */
  backoffActive: boolean;
  /** Manually trigger an immediate re-fetch (e.g. pull-to-refresh). */
  refresh: () => void;
}

export interface UseLiveDataOptions {
  /** Polling interval in ms (default 20000). */
  intervalMs?: number;
  /** Age threshold in seconds after which isStale flips true (default 60). */
  staleAfterSec?: number;
  /** Per-attempt timeout forwarded to fetchHonest (default 8000). */
  timeoutMs?: number;
  /** Disable polling entirely (default true). */
  enabled?: boolean;
  /** Max backoff multiplier cap (default 5x). */
  maxBackoffMultiplier?: number;
  /**
   * Opt-in last-known-value cache key. When set, the hook seeds its initial
   * state from the last successful payload for this key (module memory,
   * falling back to sessionStorage) so navigations paint INSTANTLY with
   * honest age/stale stamps instead of skeletons, then refreshes in the
   * background. Cached data is never presented as fresh: lastUpdatedAt is
   * the ORIGINAL fetch time, so ageSec/isStale stay truthful.
   */
  cacheKey?: string;
}

// ---------------------------------------------------------------------------
// Last-known-value cache (opt-in via cacheKey). Module map survives client
// navigations; sessionStorage survives reloads within the tab session.
// ---------------------------------------------------------------------------

type LkvEntry = { data: unknown; ts: number };
const _LKV = new Map<string, LkvEntry>();
const _LKV_PREFIX = "cv-lkv:";

function lkvGet(key: string): LkvEntry | null {
  const mem = _LKV.get(key);
  if (mem) return mem;
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(_LKV_PREFIX + key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as LkvEntry;
    if (parsed && typeof parsed.ts === "number") {
      _LKV.set(key, parsed);
      return parsed;
    }
  } catch {
    /* corrupt/quota -> behave as cache miss */
  }
  return null;
}

function lkvPut(key: string, data: unknown, ts: number): void {
  const entry: LkvEntry = { data, ts };
  _LKV.set(key, entry);
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(_LKV_PREFIX + key, JSON.stringify(entry));
  } catch {
    /* quota exceeded -> memory cache still works */
  }
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function isUnavailableSentinel(v: unknown): v is Unavailable {
  return (
    v !== null &&
    typeof v === "object" &&
    (v as { status?: string }).status === "unavailable"
  );
}

/**
 * Compute the next poll delay with capped exponential backoff.
 * consecutiveFailures=0 -> base intervalMs. f>=1 -> intervalMs*2^(f-1) capped.
 */
export function backoffDelay(
  intervalMs: number,
  consecutiveFailures: number,
  maxMultiplier = 5,
): number {
  if (consecutiveFailures <= 0) return intervalMs;
  const multiplier = Math.min(Math.pow(2, consecutiveFailures - 1), maxMultiplier);
  return Math.round(intervalMs * multiplier);
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useLiveData<T>(
  fetcher: (signal: AbortSignal) => Promise<T | Unavailable>,
  options: UseLiveDataOptions = {},
): LiveDataState<T> {
  const {
    intervalMs = 20_000,
    staleAfterSec = 60,
    timeoutMs = 8_000,
    enabled = true,
    maxBackoffMultiplier = 5,
    cacheKey,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const [ageSec, setAgeSec] = useState<number | null>(null);
  const [isStale, setIsStale] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
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
    if (!cacheKey) return;
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

  const abortRef = useRef<AbortController | null>(null);
  const lastUpdatedAtRef = useRef<number | null>(null);
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
      setIsLoading((prev) => (lastUpdatedAtRef.current === null ? prev : false));
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

  // Age ticker: increments ageSec ~every 1 s without triggering a fetch.
  useEffect(() => {
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
  options: UseLiveDataOptions = {},
): LiveDataState<T> {
  const fetcher = useCallback(
    (signal: AbortSignal) =>
      fetchHonest<T>(url, { signal, timeoutMs: options.timeoutMs }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [url, options.timeoutMs],
  );
  return useLiveData<T>(fetcher, options);
}
