"use client";

// DataSurface -- reusable robustness wrapper for any data panel.
//
// Accepts a useLiveData result (or any LiveDataState-shaped object) and drives
// an honest state machine over the content:
//
//   isLoading (first load, no data)  -> skeleton (aria-busy, NEVER a red error)
//   error + no data (unavailable)    -> neutral amber "unavailable" + optional retry
//   last-good + stale                -> render children + amber stale badge (NEVER green)
//   empty (data loaded, empty check) -> honest empty slot via emptySlot prop
//   data present                     -> render children
//
// Honesty rails (mirror RAILS in workstream spec):
//   - stale-never-green: the stale badge is amber only; green badge never appears
//   - unavailable is neutral amber (never red "failed") and never crashes the page
//   - first-load skeleton shows aria-busy; the error path only shows after first data
//   - the component never throws on null/error/loading combinations
//   - retry affordance optional (shown when onRetry is provided + error present)
//   - last-updated age shown when ageSec is non-null (honest age, not guessed)
//
// The component is purely presentational with respect to polling: it consumes a
// LiveDataState contract and renders; it does NOT own fetching or intervals.

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import type { LiveDataState } from "@/lib/useLiveData";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DataSurfaceProps<T> {
  /** Result from useLiveData / useLiveDataUrl -- drives the state machine. */
  live: LiveDataState<T>;
  /**
   * Render function for the success state.
   * Receives the non-null data value.
   */
  children: (data: T) => ReactNode;
  /**
   * Optional predicate: called with data when live.data is non-null.
   * If it returns true the component renders emptySlot instead of children.
   * Defaults to () => false (never empty while data is present).
   */
  isEmpty?: (data: T) => boolean;
  /**
   * Slot rendered when isEmpty(data) returns true.
   * Defaults to a generic honest "Nothing here yet" panel.
   */
  emptySlot?: ReactNode;
  /**
   * Slot rendered while first loading (no data yet).
   * Defaults to three skeleton rows.
   */
  loadingSlot?: ReactNode;
  /**
   * Optional manual retry callback. When provided and error is set (with no
   * data), a "Retry" button is rendered alongside the unavailable state.
   */
  onRetry?: () => void;
  /** Extra class forwarded to the wrapper div. */
  className?: string;
  /**
   * Label used in aria-label on the wrapper when loading.
   * Defaults to "Loading data".
   */
  loadingLabel?: string;
}

// ---------------------------------------------------------------------------
// Internal sub-components (kept inline, <=300 LOC total budget)
// ---------------------------------------------------------------------------

/** Three skeleton rows -- the default first-load placeholder. */
function DefaultSkeleton() {
  return (
    <div className="flex flex-col gap-2 p-1" aria-hidden="true">
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}

/** Neutral amber unavailable panel -- never red, never green. */
function UnavailablePanel({
  error,
  onRetry,
}: {
  error: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      data-honest-state="unavailable"
      className="flex flex-col gap-2 rounded-lg border border-amber-900/40 bg-amber-950/20 px-3 py-3 text-sm"
    >
      <span className="font-mono text-xs uppercase tracking-wide text-amber-400">
        unavailable
      </span>
      <span className="text-xs text-muted-foreground">{error}</span>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className={cn(
            "mt-1 self-start rounded border border-amber-800/50 bg-amber-950/30",
            "px-2 py-0.5 font-mono text-xs text-amber-400",
            "hover:bg-amber-900/30 transition-colors",
          )}
          aria-label="Retry loading data"
        >
          retry
        </button>
      ) : null}
    </div>
  );
}

/** Honest empty slot -- data arrived but is genuinely empty. */
function DefaultEmpty() {
  return (
    <div
      role="status"
      data-honest-state="empty"
      className="rounded-lg border border-slate-800 bg-surface-1/40 px-3 py-3 text-sm text-muted-foreground"
    >
      Nothing here yet.
    </div>
  );
}

/** Amber stale badge -- shown when data is present but stale (never green). */
function StaleBadge({ ageSec }: { ageSec: number | null }) {
  const label =
    ageSec !== null ? `stale (${humanizeAge(ageSec)} old)` : "stale";
  return (
    <span
      role="status"
      aria-live="polite"
      data-honest-state="stale"
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-amber-800/50",
        "bg-amber-950/40 px-2 py-0.5 font-mono text-[10px] text-amber-400",
      )}
    >
      <span
        className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500"
        aria-hidden="true"
      />
      {label}
    </span>
  );
}

function humanizeAge(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h`;
}

// ---------------------------------------------------------------------------
// DataSurface
// ---------------------------------------------------------------------------

/**
 * DataSurface<T> -- honest state machine wrapper for any data panel.
 *
 * Usage:
 *   const live = useLiveDataUrl<MyData>("/api/my-endpoint");
 *   return (
 *     <DataSurface live={live} isEmpty={(d) => d.items.length === 0}>
 *       {(data) => <MyTable rows={data.items} />}
 *     </DataSurface>
 *   );
 */
export function DataSurface<T>({
  live,
  children,
  isEmpty,
  emptySlot,
  loadingSlot,
  onRetry,
  className,
  loadingLabel = "Loading data",
}: DataSurfaceProps<T>) {
  const { data, ageSec, isStale, error, isLoading } = live;

  // ------------------------------------------------------------------
  // State priority (evaluated top -> bottom; first match wins)
  // ------------------------------------------------------------------

  // 1. First load: no data, currently loading -> show skeleton
  if (isLoading && data === null) {
    return (
      <div
        className={cn("relative", className)}
        aria-busy="true"
        aria-label={loadingLabel}
        data-surface-state="loading"
      >
        {loadingSlot ?? <DefaultSkeleton />}
      </div>
    );
  }

  // 2. Error without any data -> unavailable (amber, neutral, never red)
  if (error !== null && data === null) {
    return (
      <div className={cn("relative", className)} data-surface-state="error-no-data">
        <UnavailablePanel error={error} onRetry={onRetry} />
      </div>
    );
  }

  // 3. Data present (may be stale) -- render children or empty slot
  if (data !== null) {
    const empty = isEmpty ? isEmpty(data) : false;

    return (
      <div className={cn("relative flex flex-col gap-2", className)} data-surface-state={isStale ? "stale" : "fresh"}>
        {/* Stale badge -- amber only, NEVER green */}
        {isStale && (
          <div className="flex items-center justify-end">
            <StaleBadge ageSec={ageSec} />
          </div>
        )}

        {/* Content */}
        {empty ? (emptySlot ?? <DefaultEmpty />) : children(data)}
      </div>
    );
  }

  // 4. Fallback: no data, not loading, no error (e.g. disabled hook).
  //    Show an honest "checking" state rather than blank or crash.
  return (
    <div
      className={cn("relative", className)}
      aria-busy="true"
      aria-label="checking..."
      data-surface-state="checking"
    >
      {loadingSlot ?? <DefaultSkeleton />}
    </div>
  );
}
