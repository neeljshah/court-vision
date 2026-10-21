// liveDataSupport.ts -- the pieces of lib/useLiveData.ts that are not the hook itself:
// the public contract types, the opt-in last-known-value cache (keyed per build), the
// Unavailable sentinel guard and the capped exponential backoff. Split out to keep the
// hook module under the 300-line rail; useLiveData re-exports the public names.

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

export interface UseLiveDataOptions<T = unknown> {
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
  /**
   * First payload supplied by the caller (e.g. a server page that read the baked
   * snapshot at build time). When set, the hook starts with data=initialData and
   * isLoading=false instead of the loading state, so server-rendered HTML carries
   * the values. The first fetch and polling are unchanged: the first poll replaces
   * the seed. Takes precedence over a cacheKey seed.
   */
  initialData?: T;
  /**
   * Epoch ms the seed was produced. Pass the payload's OWN as-of timestamp (e.g.
   * the export's as_of): only then are lastUpdatedAt/ageSec/isStale honest. Left
   * undefined, the seed carries no age stamp (lastUpdatedAt stays null) until the
   * first poll succeeds. The age is stamped after mount, never in the first render,
   * because Date.now() differs between the server render and hydration.
   */
  initialUpdatedAt?: number;
}

// ---------------------------------------------------------------------------
// Last-known-value cache (opt-in via cacheKey). Module map survives client
// navigations; sessionStorage survives reloads within the tab session.
// ---------------------------------------------------------------------------

export type LkvEntry = { data: unknown; ts: number };
const _LKV = new Map<string, LkvEntry>();
// Keyed per build (next.config.mjs inlines NEXT_PUBLIC_BUILD_ID) so a redeploy never
// repaints a previous build's payload out of this tab's sessionStorage.
const _LKV_PREFIX = `cv-lkv:${process.env.NEXT_PUBLIC_BUILD_ID || "dev"}:`;

export function lkvGet(key: string): LkvEntry | null {
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

export function lkvPut(key: string, data: unknown, ts: number): void {
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

export function isUnavailableSentinel(v: unknown): v is Unavailable {
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
