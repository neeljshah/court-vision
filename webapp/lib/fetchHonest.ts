// fetchHonest.ts -- the ONE hardened fetch primitive every client call routes
// through. It adds, on top of the browser fetch, the three robustness rails the
// rest of the app relies on:
//
//   1. a bounded TIMEOUT (a hung backend can never freeze a panel forever),
//   2. a bounded RETRY with capped exponential backoff (a transient blip
//      self-heals without a human), and
//   3. NEVER-THROWS: every failure mode -- network error, abort, timeout, a
//      4xx/5xx, or a non-JSON body -- degrades to the explicit honest
//      Unavailable sentinel. It is impossible for a caller to receive a thrown
//      exception or a fabricated body.
//
// This mirrors the backend http_cache retry primitive and the honesty_mw
// fail-closed contract: a degraded result is the SUCCESS state under failure,
// never a crash and never a green-on-missing value. UNITS/probability only --
// this layer is transport, it invents no numbers and strips nothing.

import type { Unavailable } from "./types";

// ---------------------------------------------------------------------------
// Snapshot data mode -- static-demo build (NEXT_PUBLIC_DATA_MODE=snapshot).
// GET requests are redirected to a pre-baked JSON file under /demo-data/ so the
// exported site needs no backend at all. Inlined by Next at build time.
// ponytail: path -> filename is a dumb slug (strip query, non-alnum -> "_");
// the exporter (scripts/platformkit/publish_demo/export_snapshot.py) must slug
// identically so client requests resolve to files it wrote.
// ---------------------------------------------------------------------------
export const isSnapshotMode = process.env.NEXT_PUBLIC_DATA_MODE === "snapshot";

// Next's basePath (set to /court-vision in next.config.mjs when SNAPSHOT) is
// NOT auto-prepended to plain fetch() calls -- only to Link/Image/router nav.
// Mirror it here via a public env var so a GitHub Pages project-site build
// resolves /demo-data/*.json correctly instead of 404ing at the site root.
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

export function snapshotPath(url: string): string {
  // Keep the query string in the slug -- several endpoints (board/slate,
  // produce/status) differ ONLY by ?sport=, so dropping it would collide
  // different sports onto one file. The exporter must slug identically.
  const slug = url.replace(/^\/+/, "").replace(/[^a-zA-Z0-9]+/g, "_");
  return `${BASE_PATH}/demo-data/${slug}.json`;
}

export interface FetchHonestOptions {
  /** Caller's abort signal (page unmount). Composed with the timeout. */
  signal?: AbortSignal;
  /** Per-attempt timeout in ms (default 8000). 0 disables the timeout. */
  timeoutMs?: number;
  /** Number of retries AFTER the first attempt (default 2 -> 3 attempts). */
  retries?: number;
  /** Base backoff in ms; grows 1x,2x,4x... capped at backoffCapMs (default 250). */
  backoffMs?: number;
  /** Upper bound on a single backoff sleep (default 2000). */
  backoffCapMs?: number;
  /** POST body. When present the request method becomes POST with JSON. */
  body?: unknown;
}

const DEFAULTS = {
  timeoutMs: 8000,
  retries: 2,
  backoffMs: 250,
  backoffCapMs: 2000,
};

function unavailable(reason: string): Unavailable {
  return { status: "unavailable", reason };
}

const isAbort = (e: unknown): boolean =>
  !!e && typeof e === "object" && (e as { name?: string }).name === "AbortError";

// One attempt. Resolves to a parsed body, or an Unavailable sentinel, or throws
// ONLY a synthetic retryable marker (network error / timeout) so the caller can
// decide whether another attempt is worthwhile. A real HTTP 4xx/5xx (the server
// answered) is NOT retried -- it degrades immediately to an honest sentinel.
async function attempt<T>(
  url: string,
  opts: Required<Omit<FetchHonestOptions, "signal" | "body">> & {
    signal?: AbortSignal;
    body?: unknown;
  },
): Promise<T | Unavailable> {
  const ctrl = new AbortController();
  const onParentAbort = () => ctrl.abort();
  if (opts.signal) {
    if (opts.signal.aborted) ctrl.abort();
    else opts.signal.addEventListener("abort", onParentAbort, { once: true });
  }
  let timer: ReturnType<typeof setTimeout> | null = null;
  let timedOut = false;
  if (opts.timeoutMs > 0) {
    timer = setTimeout(() => {
      timedOut = true;
      ctrl.abort();
    }, opts.timeoutMs);
  }
  try {
    const init: RequestInit = { signal: ctrl.signal, cache: "no-store" };
    if (opts.body !== undefined) {
      init.method = "POST";
      init.headers = { "content-type": "application/json" };
      init.body = JSON.stringify(opts.body);
    }
    const r = await fetch(url, init);
    const ctype = r.headers.get("content-type") || "";
    const hasJson = ctype.includes("application/json");
    if (!r.ok) {
      // Server answered with an error. For POST we still try to surface a JSON
      // reason (e.g. a 422/409 rejection body); otherwise honest sentinel.
      if (opts.body !== undefined && hasJson) return (await r.json()) as T;
      return unavailable(`HTTP ${r.status}`);
    }
    if (!hasJson) {
      return unavailable(`non-JSON response (${ctype || "no content-type"})`);
    }
    return (await r.json()) as T;
  } catch (e) {
    // Parent aborted (page unmounted) -> honest, not retryable.
    if (isAbort(e) && opts.signal?.aborted) return unavailable("request aborted");
    // Our timeout fired -> retryable transient.
    if (timedOut) throw { retryable: true, reason: `timeout after ${opts.timeoutMs}ms` };
    // Network / DNS / connection-refused -> retryable transient.
    throw { retryable: true, reason: `fetch failed: ${String(e)}` };
  } finally {
    if (timer) clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onParentAbort);
  }
}

const sleep = (ms: number) => new Promise((res) => setTimeout(res, ms));

/**
 * Hardened JSON fetch. ALWAYS resolves; NEVER throws. On exhausting retries it
 * resolves to an explicit Unavailable sentinel (never green-on-missing, never a
 * fabricated body). A server 4xx/5xx degrades immediately (the server answered);
 * only transient transport failures (network error / timeout) are retried with
 * capped exponential backoff.
 */
export async function fetchHonest<T>(
  url: string,
  options: FetchHonestOptions = {},
): Promise<T | Unavailable> {
  const o = {
    timeoutMs: options.timeoutMs ?? DEFAULTS.timeoutMs,
    retries: options.retries ?? DEFAULTS.retries,
    backoffMs: options.backoffMs ?? DEFAULTS.backoffMs,
    backoffCapMs: options.backoffCapMs ?? DEFAULTS.backoffCapMs,
    signal: options.signal,
    body: options.body,
  };
  // Snapshot mode: GET-only demo build, redirect to the baked static file.
  // POSTs (placePaper etc.) have no snapshot equivalent -- fall through to the
  // live URL, which 404s and degrades to Unavailable, same as any dead backend.
  const targetUrl = isSnapshotMode && o.body === undefined ? snapshotPath(url) : url;
  let lastReason = "fetch failed";
  for (let i = 0; i <= o.retries; i++) {
    if (o.signal?.aborted) return unavailable("request aborted");
    try {
      return await attempt<T>(targetUrl, o);
    } catch (e) {
      const re = e as { retryable?: boolean; reason?: string };
      lastReason = re?.reason ?? lastReason;
      if (!re?.retryable || i === o.retries) break;
      const wait = Math.min(o.backoffMs * 2 ** i, o.backoffCapMs);
      await sleep(wait);
    }
  }
  return unavailable(lastReason);
}
