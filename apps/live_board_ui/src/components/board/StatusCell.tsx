/** Compact game-status cell: pulsing live indicator, final, or scheduled time. */

import type { BoardRow } from "@/types/board";
import { localTime } from "@/lib/format";

interface StatusCellProps {
  row: BoardRow;
}

export function StatusCell({ row }: StatusCellProps) {
  const { state, clock_text, start_time } = row;

  if (state === "in") {
    const label = clock_text || "Live";
    return (
      <span
        className="inline-flex items-center gap-1.5 text-xs whitespace-nowrap"
        aria-label={`Live: ${label}`}
      >
        <span
          className="w-2 h-2 rounded-full bg-live animate-live-pulse"
          aria-hidden="true"
        />
        <span className="text-live font-semibold tabular-nums">{label}</span>
      </span>
    );
  }

  if (state === "post") {
    const display = clock_text || "Final";
    return (
      <span className="text-xs whitespace-nowrap text-muted font-semibold">
        {display}
      </span>
    );
  }

  // state === "pre"
  const display =
    clock_text || (start_time ? localTime(start_time) : "Scheduled");
  return (
    <span className="text-xs whitespace-nowrap text-muted">
      {display || "Scheduled"}
    </span>
  );
}
