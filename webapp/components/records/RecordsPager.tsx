"use client";

// RecordsPager.tsx -- W1-records-surface server-style pager (offset/limit).
// Prev / Next buttons; shows current page range and total count.
// No $ / ROI / P&L token. ASCII only. Under 300 LOC rail.

import { cn } from "@/lib/utils";

interface RecordsPagerProps {
  offset:    number;
  limit:     number;
  total:     number;
  onOffset:  (next: number) => void;
  disabled?: boolean;
}

const BTN_CLS = cn(
  "inline-flex items-center border px-2.5 py-1",
  "font-data text-[11px] uppercase tracking-wide transition-colors",
  "border-border bg-secondary text-muted-foreground",
  "hover:border-ring hover:text-foreground",
  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
  "disabled:cursor-not-allowed disabled:opacity-40",
);

export function RecordsPager({
  offset, limit, total, onOffset, disabled = false,
}: RecordsPagerProps) {
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd   = Math.min(offset + limit, total);

  return (
    <div
      role="navigation"
      aria-label="records pager"
      data-testid="records-pager"
      className="flex items-center gap-3"
    >
      <button
        type="button"
        data-testid="pager-prev"
        className={BTN_CLS}
        disabled={!hasPrev || disabled}
        onClick={() => onOffset(Math.max(0, offset - limit))}
        aria-label="previous page"
      >
        prev
      </button>

      <span
        data-testid="pager-range"
        className="font-data text-[11px] text-faint tabular"
        aria-live="polite"
      >
        {total === 0 ? "0 records" : `${rangeStart}-${rangeEnd} of ${total}`}
      </span>

      <button
        type="button"
        data-testid="pager-next"
        className={BTN_CLS}
        disabled={!hasNext || disabled}
        onClick={() => onOffset(offset + limit)}
        aria-label="next page"
      >
        next
      </button>
    </div>
  );
}
