/** Thin status bar: game counts, last-updated timestamp, and a manual refresh button.
 * Only the changing "updated <time>" is in a polite live region, so screen readers
 * are not spammed by the full count string on every 25s poll.
 * Status-chip priority (at most ONE): connectionIssue -> "reconnecting" chip;
 * else stale -> "delayed" chip; else no chip. Wording is neutral freshness-only --
 * no money/edge/value language. Timestamp tinted amber when connectionIssue || stale. */

import { RefreshCw, AlertTriangle, WifiOff } from "lucide-react";
import { localClock } from "@/lib/format";
import { useRelativeTime } from "@/hooks/useRelativeTime";

interface StampBarProps {
  generatedAt: string | null;
  liveCount: number;
  upcomingCount: number;
  finishedCount: number;
  refreshing: boolean;
  onRefresh: () => void;
  stale?: boolean;
  /** True when the most recent background refresh failed but prior data is still shown. */
  connectionIssue?: boolean;
}

export function StampBar({
  generatedAt,
  liveCount,
  upcomingCount,
  finishedCount,
  refreshing,
  onRefresh,
  stale = false,
  connectionIssue = false,
}: StampBarProps) {
  const parts: string[] = [];
  if (upcomingCount > 0) parts.push(`${upcomingCount} upcoming`);
  if (finishedCount > 0) parts.push(`${finishedCount} final`);
  const tailStr = parts.join(" / ");

  const rel = useRelativeTime(generatedAt);
  const displayTime = rel !== "" ? rel : (localClock(generatedAt) ?? "");

  const isAmber = connectionIssue || stale;

  // Persistent polite live region so screen readers hear freshness transitions.
  // Distinct wording from the visible chips ("reconnecting"/"delayed") keeps the
  // chip-text queries unambiguous while still announcing the state change.
  const announce = connectionIssue
    ? "Live updates interrupted; retrying."
    : stale
      ? "Live data may be lagging."
      : "";

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px] text-muted tabular-nums select-none">
      <span role="status" aria-live="polite" className="sr-only">
        {announce}
      </span>
      <span className="flex items-center gap-1">
        {liveCount > 0 && (
          <span className="text-live font-semibold">{liveCount} live</span>
        )}
        {liveCount > 0 && tailStr && <span aria-hidden="true">/</span>}
        {tailStr && <span>{tailStr}</span>}
        {liveCount === 0 && !tailStr && <span>0 games</span>}
      </span>

      <span className="text-muted/60" aria-hidden="true">
        &mdash;
      </span>

      {/* Only the timestamp is a live region (atomic), so polls stay quiet. */}
      <span
        aria-live="polite"
        aria-atomic="true"
        title={generatedAt ? localClock(generatedAt) : undefined}
        className={isAmber ? "text-draw" : "text-muted"}
      >
        updated {displayTime}
      </span>
      <span aria-hidden="true">- auto 25s</span>

      {/* Status chip -- at most one, priority: connectionIssue > stale > none */}
      {/* Visible chips are decorative (aria-hidden); the role=status region above
          carries the spoken announcement so the state is not read twice. */}
      {connectionIssue ? (
        <span
          aria-hidden="true"
          className="inline-flex items-center gap-1 text-draw bg-draw/15 border border-draw/40 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase"
          title="Last refresh failed; retrying."
        >
          <WifiOff className="w-3 h-3" aria-hidden="true" />
          reconnecting
        </span>
      ) : stale ? (
        <span
          aria-hidden="true"
          className="inline-flex items-center gap-1 text-draw bg-draw/15 border border-draw/40 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase"
          title="Data may be delayed; trying to refresh."
        >
          <AlertTriangle className="w-3 h-3" aria-hidden="true" />
          delayed
        </span>
      ) : null}

      <button
        type="button"
        onClick={onRefresh}
        disabled={refreshing}
        aria-label="Refresh now"
        className="ml-1 rounded-md p-1 text-muted transition-colors hover:bg-surface2 hover:text-txt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
      >
        <RefreshCw
          className={refreshing ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"}
          aria-hidden="true"
        />
      </button>
    </div>
  );
}
