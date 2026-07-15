"use client";

// HomeStatusRow -- the live, honest status strip on the Home page.
//
// Polling: powered by useLiveData (shared resilient hook) which:
//   - polls every POLL_MS with a single AbortController per tick,
//   - pauses polling when the tab is hidden (visibilitychange),
//   - retains last-good data + sets isStale/error on a failed poll,
//   - ticks ageSec every ~1 s so the age label stays current without a
//     second bespoke setInterval in this component.
//
// On a failed poll the strip degrades HONESTLY:
//   - last-good values remain visible,
//   - a "stale" badge appears next to the age label,
//   - NEVER blanks out, never crashes.
//
// Before the first successful fetch isLoading is true -- we show a
// neutral "checking..." skeleton (never green-on-null, never red).
//
// Color dots are aria-hidden; the text value carries state (WCAG 1.4.1).
// No $ field anywhere (units-not-$ rail). Real-money is always DENY (paper).

import { useCallback } from "react";
import {
  getProductStatus,
  getParityHeadline,
  type ProductStatus,
  type ParityHeadline,
} from "@/lib/api";
import { useLiveData } from "@/lib/useLiveData";
import type { Unavailable } from "@/lib/types";
import { cn } from "@/lib/utils";

// Poll every 20 s; data is stale after 60 s with no successful refresh.
const POLL_MS = 20_000;
const STALE_SEC = 60;

// ---------------------------------------------------------------------------
// Combined payload shape -- both endpoints bundled into one useLiveData call.
// ---------------------------------------------------------------------------

interface StatusPayload {
  status: ProductStatus | null;
  parity: ParityHeadline | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type Tone = "green" | "amber" | "red" | "grey";
const DOT: Record<Tone, string> = {
  green: "bg-success",
  amber: "bg-warning",
  red: "bg-danger",
  grey: "bg-muted-foreground",
};

/** Format seconds-since-last-update as a human-readable age string. */
function formatAge(seconds: number): string {
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const mins = Math.floor(seconds / 60);
  return `${mins}m ago`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Cell({
  tone,
  label,
  value,
}: {
  tone: Tone;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2 border border-border bg-surface-1 px-3 py-2">
      <span
        className={cn("h-2 w-2 shrink-0 rounded-full", DOT[tone])}
        aria-hidden="true"
      />
      <div className="min-w-0">
        <div className="microlabel">{label}</div>
        <div className="truncate text-xs font-medium text-foreground">{value}</div>
      </div>
    </div>
  );
}

/** Neutral skeleton shown while the very first fetch is in-flight. */
function CheckingStrip() {
  return (
    <div
      className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5"
      aria-label="status checking"
      data-testid="checking-strip"
    >
      {(
        ["all_honest", "live now", "parity", "self-improve", "real-money"] as const
      ).map((label) => (
        <div
          key={label}
          className="flex items-center gap-2 border border-border bg-surface-1 px-3 py-2"
        >
          <span
            className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground opacity-40"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <div className="microlabel">{label}</div>
            <div className="truncate text-xs font-medium text-muted-foreground/60">
              checking...
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function HomeStatusRow() {
  // Combined fetcher: both endpoints in one Promise.allSettled so a single
  // useLiveData instance owns the interval + age tick. A per-endpoint failure
  // degrades that half to null while the other stays intact.
  const fetcher = useCallback(
    async (signal: AbortSignal): Promise<StatusPayload | Unavailable> => {
      const [statusResult, parityResult] = await Promise.allSettled([
        getProductStatus(signal),
        getParityHeadline(signal),
      ]);

      // If BOTH rejected, return the unavailable sentinel so useLiveData
      // retains last-good data and sets isStale.
      if (
        statusResult.status === "rejected" &&
        parityResult.status === "rejected"
      ) {
        return { status: "unavailable", reason: "both endpoints failed" };
      }

      return {
        status:
          statusResult.status === "fulfilled" ? statusResult.value : null,
        parity:
          parityResult.status === "fulfilled" ? parityResult.value : null,
      };
    },
    [],
  );

  const { data, ageSec, isStale, isLoading, error } = useLiveData<StatusPayload>(
    fetcher,
    { intervalMs: POLL_MS, staleAfterSec: STALE_SEC, cacheKey: "home:status" },
  );

  // Show the checking strip only while we've never had ANY poll response yet.
  // Once the hook surfaces an error (even with no data), the first poll has
  // settled -- switch to degraded cells ("unknown") rather than infinite checking.
  const showChecking = isLoading && error === null;

  const status = data?.status ?? null;
  const parity = data?.parity ?? null;

  // -------------------------------------------------------------------------
  // Derive cell values
  // -------------------------------------------------------------------------

  const honestTone: Tone =
    status?.allHonest == null ? "grey" : status.allHonest ? "green" : "red";
  const honestValue =
    status?.allHonest == null
      ? "unknown"
      : status.allHonest
        ? "TRUE"
        : "FALSE";

  const liveValue =
    status == null
      ? "unknown"
      : status.liveSports.length > 0
        ? status.liveSports.join(" / ")
        : "no games live now";
  const liveTone: Tone =
    status != null && status.liveSports.length > 0 ? "green" : "grey";

  const parityTone: Tone =
    parity?.green == null ? "grey" : parity.green ? "green" : "red";
  const parityValue =
    parity?.green == null
      ? "unknown"
      : parity.green
        ? "FULLY GREEN"
        : "not green";

  const selfImproveValue = status
    ? status.selfImprove === "ENABLED"
      ? "ENABLED"
      : "READY (inert)"
    : "unknown";

  // -------------------------------------------------------------------------
  // Age label -- uses ageSec from the hook (no bespoke clock interval here).
  // -------------------------------------------------------------------------

  const ageLabel: string = (() => {
    if (ageSec === null) return "";
    return `updated ${formatAge(Math.max(0, ageSec))}`;
  })();

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <section
      className="mx-auto max-w-5xl px-4 py-2 sm:px-6"
      aria-label="live status"
    >
      {showChecking ? (
        <CheckingStrip />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <Cell tone={honestTone} label="all_honest" value={honestValue} />
            <Cell tone={liveTone} label="live now" value={liveValue} />
            <Cell tone={parityTone} label="parity" value={parityValue} />
            <Cell
              tone="amber"
              label="self-improve"
              value={selfImproveValue}
            />
            <Cell tone="amber" label="real-money" value="DENY (paper)" />
          </div>
          {ageLabel && (
            <p
              className="mt-1.5 text-right font-data text-[10px] uppercase tracking-wider text-faint"
              data-testid="last-updated-label"
              aria-live="polite"
              aria-atomic="true"
            >
              {ageLabel}
              {isStale && (
                <span
                  className="ml-2 text-stale"
                  data-testid="stale-badge"
                  aria-label="data may be stale"
                >
                  (stale)
                </span>
              )}
            </p>
          )}
        </>
      )}
    </section>
  );
}
