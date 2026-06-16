/** Compact filter row: text search, live-only toggle, result count. */
import { Search, X } from "lucide-react"
import { cn } from "@/lib/utils"

interface FilterBarProps {
  query: string
  onQuery: (v: string) => void
  liveOnly: boolean
  onLiveOnly: (v: boolean) => void
  shown: number
  total: number
  liveCount: number
}

export function FilterBar({
  query,
  onQuery,
  liveOnly,
  onLiveOnly,
  shown,
  total,
  liveCount,
}: FilterBarProps) {
  const disableLive = liveCount === 0

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      onQuery("")
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Search input */}
      <div className="relative w-full sm:w-64">
        <Search
          className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted pointer-events-none"
          aria-hidden="true"
        />
        <input
          type="search"
          aria-label="Search teams"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search teams..."
          className={cn(
            "rounded-md border border-line bg-surface px-2.5 py-1.5 pl-8 text-sm text-txt",
            "placeholder:text-muted w-full",
            "focus:outline-none focus:ring-2 focus:ring-accent/40",
            query ? "pr-8" : ""
          )}
        />
        {query && (
          <button
            type="button"
            aria-label="Clear search"
            onClick={() => onQuery("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-txt transition-colors"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Live-only toggle */}
      <button
        type="button"
        role="switch"
        aria-checked={liveOnly}
        aria-disabled={disableLive}
        disabled={disableLive}
        onClick={() => !disableLive && onLiveOnly(!liveOnly)}
        className={cn(
          "flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm transition-colors",
          "focus:outline-none focus:ring-2 focus:ring-accent/40",
          disableLive && "opacity-50 cursor-not-allowed",
          liveOnly && !disableLive
            ? "bg-live/15 text-live border-live/40"
            : "border-line text-muted hover:text-txt"
        )}
      >
        <span
          className={cn(
            "inline-block h-2 w-2 rounded-full",
            liveOnly && !disableLive ? "bg-live animate-live-pulse" : "bg-muted"
          )}
          aria-hidden="true"
        />
        <span>Live only</span>
        {liveCount > 0 && (
          <span className="tabular-nums">({liveCount})</span>
        )}
      </button>

      {/* Result count */}
      <span
        className="text-[11px] text-muted ml-auto tabular-nums"
        aria-live="polite"
      >
        showing {shown} of {total}
      </span>
    </div>
  )
}
