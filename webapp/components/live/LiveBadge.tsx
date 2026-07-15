/**
 * LiveBadge -- shared presentational primitive that visualizes the useLiveData
 * contract honestly. Pure props-driven; does NOT fetch or poll.
 * Direction A "Amber Console": flat, token-driven freshness stamp.
 *
 * States (exclusive priority: loading > error > stale > live):
 *   loading (isLoading && ageSec===null)  -> neutral "checking..." spinner
 *   error   (error && ageSec===null)      -> neutral "unavailable" (amber, NOT red-failed)
 *   stale   (isStale || error w/ last-good) -> amber "stale (Xm old)", no live pulse
 *   live    (!isStale && !error)          -> success pulse dot + "updated Xs ago"
 *
 * Honesty rails (match RAILS in workstream spec):
 *   - stale-never-green: live pulse ONLY when not stale and not errored.
 *   - unavailable is neutral amber, never red "failed".
 *   - "checking" (not "loading" / "connecting") while no data yet.
 *   - No dollar figures; ASCII only.
 *   - aria-live="polite" + aria-atomic so screen-readers announce transitions.
 */

import * as React from "react";
import { cn } from "@/lib/utils";
import { UpdatedAge } from "./UpdatedAge";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LiveBadgeProps {
  /**
   * Age of last-good data in seconds. null = no data received yet.
   * Drives the "updated Xs ago" label and is required for the live pulse.
   */
  ageSec: number | null;
  /**
   * True when the data is considered stale by the polling hook
   * (e.g. last poll was too long ago or server returned stale flag).
   */
  isStale: boolean;
  /**
   * Error from the most recent poll attempt. null/undefined = no error.
   * When error is set AND ageSec is null -> unavailable state.
   * When error is set AND ageSec is non-null -> stale-with-error (shows last age).
   */
  error?: Error | string | null;
  /**
   * True while the hook is performing its first (or a retry) fetch with no
   * cached data yet. Once ageSec is non-null the spinner is suppressed.
   */
  isLoading?: boolean;
  /** Optional class name forwarded to the wrapper span. */
  className?: string;
  /** Optional test hook forwarded to the wrapper span. */
  "data-testid"?: string;
}

// ---------------------------------------------------------------------------
// Internal sub-components (inline for <= 300 LOC budget)
// ---------------------------------------------------------------------------

/** Success pulse dot -- only rendered in the "live" (fresh) state. */
function LivePulseDot({ className }: { className?: string }) {
  return (
    <span
      className={cn("relative flex h-2 w-2 shrink-0", className)}
      aria-hidden="true"
    >
      {/* Ping ring */}
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-75" />
      {/* Solid center */}
      <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
    </span>
  );
}

/** Neutral spinner -- shown during initial load only. */
function CheckingSpinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn("h-3 w-3 animate-spin text-faint", className)}
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * LiveBadge -- visualizes the useLiveData contract as a small inline badge.
 * All state transitions are driven by props; no internal fetching.
 */
export function LiveBadge({
  ageSec,
  isStale,
  error,
  isLoading = false,
  className,
  "data-testid": dataTestId,
}: LiveBadgeProps) {
  const hasError = Boolean(error);
  const hasData = ageSec !== null;

  // ------------------------------------------------------------------
  // Derive display state (mutually exclusive, evaluated top -> bottom)
  // ------------------------------------------------------------------

  // 1. No data yet + still loading -> "checking..."
  const isCheckingState = isLoading && !hasData;

  // 2. Error with NO last-good data -> "unavailable" (amber, not red)
  const isUnavailableState = hasError && !hasData;

  // 3. Stale: either explicitly stale or errored but still has last-good age
  const isStaleState = !isCheckingState && !isUnavailableState && (isStale || hasError);

  // 4. Live: none of the above, has data, not stale, not errored
  const isLiveState = !isCheckingState && !isUnavailableState && !isStaleState && hasData;

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 border px-2 py-0.5 font-data text-[11px]",
        // Live (fresh): success ink, flat border -- never rounded/glowing
        isLiveState && "border-success/40 text-success",
        // Stale: amber/stale ink (freshness violation)
        isStaleState && "border-warning/40 text-stale",
        // Checking: neutral faint ink
        isCheckingState && "border-border text-faint",
        // Unavailable: neutral amber (NOT red/destructive)
        isUnavailableState && "border-warning/40 text-stale",
        className,
      )}
      data-testid={dataTestId}
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-label={derivedAriaLabel({ isLiveState, isStaleState, isCheckingState, isUnavailableState, ageSec })}
    >
      {/* Live state: success pulse + updated age */}
      {isLiveState && (
        <>
          <LivePulseDot />
          <UpdatedAge ageSec={ageSec} className="text-success" />
        </>
      )}

      {/* Stale state: amber dot + stale label + age when available */}
      {isStaleState && (
        <>
          <span className="h-2 w-2 shrink-0 rounded-full bg-warning" aria-hidden="true" />
          <span>
            {"stale"}
            {hasData && (
              <span className="ml-1 opacity-75">
                {"("}
                {humanizeAgeShort(ageSec!)}
                {" old)"}
              </span>
            )}
          </span>
        </>
      )}

      {/* Checking state: spinner + "checking..." */}
      {isCheckingState && (
        <>
          <CheckingSpinner />
          <span>{"checking..."}</span>
        </>
      )}

      {/* Unavailable state: neutral amber, NOT "failed" */}
      {isUnavailableState && (
        <>
          <span className="h-2 w-2 shrink-0 rounded-full bg-warning/70" aria-hidden="true" />
          <span>{"unavailable"}</span>
        </>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Helpers (internal)
// ---------------------------------------------------------------------------

/** Short humanized age for inline stale label ("5s" / "2m" / "1h"). */
function humanizeAgeShort(ageSec: number): string {
  const s = Math.max(0, Math.round(ageSec));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h`;
}

interface AriaLabelArgs {
  isLiveState: boolean;
  isStaleState: boolean;
  isCheckingState: boolean;
  isUnavailableState: boolean;
  ageSec: number | null;
}

function derivedAriaLabel({
  isLiveState,
  isStaleState,
  isCheckingState,
  isUnavailableState,
  ageSec,
}: AriaLabelArgs): string {
  if (isLiveState && ageSec !== null) return `Live, updated ${humanizeAgeShort(ageSec)} ago`;
  if (isStaleState && ageSec !== null) return `Stale data, ${humanizeAgeShort(ageSec)} old`;
  if (isStaleState) return "Stale data";
  if (isCheckingState) return "Checking for live data";
  if (isUnavailableState) return "Data unavailable";
  return "Data status unknown";
}
