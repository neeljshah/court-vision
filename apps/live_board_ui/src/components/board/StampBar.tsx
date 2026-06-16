/** Thin status bar: game counts, last-updated timestamp, and a manual refresh button.
 * Only the changing "updated <time>" is in a polite live region, so screen readers
 * are not spammed by the full count string on every 25s poll.
 * When stale=true, shows an amber "delayed" pill and tints the timestamp; wording is
 * neutral freshness-only ("data may be delayed") -- no money/edge/value language. */

import { RefreshCw, AlertTriangle } from "lucide-react";
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
}

export function StampBar({
  generatedAt,
  liveCount,
  upcomingCount,
  finishedCount,
  refreshing,
  onRefresh,
  stale = false,
}: StampBarProps) {
  const parts: string[] = [];
  if (upcomingCount > 0) parts.push(`${upcomingCount} upcoming`);
  if (finishedCount > 0) parts.push(`${finishedCount} final`);
  const tailStr = parts.join(" / ");

  const rel = useRelativeTime(generatedAt);
  const displayTime = rel !== "" ? rel : (localClock(generatedAt) ?? "");

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px] text-muted tabular-nums select-none">
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
        className={stale ? "text-draw" : undefined}
      >
        updated {displayTime}
      </span>
      <span aria-hidden="true">- auto 25s</span>

      {stale && (
        <span
          className="inline-flex items-center gap-1 text-draw bg-draw/15 border border-draw/40 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase"
          title="Data may be delayed; trying to refresh."
          aria-label="Data may be delayed; trying to refresh."
        >
          <AlertTriangle className="w-3 h-3" aria-hidden="true" />
          delayed
        </span>
      )}

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
