/** Skeleton placeholder rows shown while the board data is loading. */
import { cn } from "@/lib/utils";

function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-shimmer rounded bg-surface2",
        className
      )}
      aria-hidden="true"
    />
  );
}

interface LoadingStateProps {
  rows?: number;
}

export function LoadingState({ rows = 8 }: LoadingStateProps) {
  return (
    <div role="status" aria-label="Loading games" className="w-full">
      <span className="sr-only">Loading games...</span>
      <div className="flex flex-col divide-y divide-line">
        {Array.from({ length: rows }).map((_, i) => (
          <div
            key={i}
            className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-x-3 gap-y-2 px-3 py-3 sm:px-4 sm:py-4"
          >
            {/* Status badge column */}
            <Skeleton className="h-5 w-10 shrink-0" />

            {/* Matchup column */}
            <div className="flex min-w-0 flex-col gap-1.5">
              <Skeleton className="h-3.5 w-32 sm:w-40" />
              <Skeleton className="h-3.5 w-24 sm:w-32" />
            </div>

            {/* Score / clock column */}
            <div className="flex flex-col items-end gap-1.5">
              <Skeleton className="h-3.5 w-12" />
              <Skeleton className="h-3 w-10" />
            </div>

            {/* Win-prob column */}
            <div className="flex flex-col items-end gap-1.5">
              <Skeleton className="h-3.5 w-8" />
              <Skeleton className="h-3 w-6" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
