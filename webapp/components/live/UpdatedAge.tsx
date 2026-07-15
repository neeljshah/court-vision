/**
 * UpdatedAge -- pure presentational: humanizes an age-in-seconds into
 * "Ns ago" / "Nm ago" / "Nh ago" text. Renders nothing when ageSec is null.
 *
 * Honesty rails:
 *   - No non-ASCII characters emitted.
 *   - No dollar figures.
 *   - No color or status implication -- callers decide styling.
 */

import * as React from "react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UpdatedAgeProps {
  /** Age of the data in whole seconds. null = no data yet (renders nothing). */
  ageSec: number | null;
  /** Optional additional class names for the wrapper span. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * humanizeAge -- converts seconds to a human-readable age string.
 * Returns ASCII only. Always non-empty for a valid number.
 *
 * Examples:
 *   5   -> "5s ago"
 *   90  -> "1m ago"
 *   3700 -> "1h ago"
 */
export function humanizeAge(ageSec: number): string {
  const s = Math.max(0, Math.round(ageSec));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * UpdatedAge -- renders the humanized age string, or nothing when ageSec
 * is null (no data available yet). Stateless / pure presentational.
 */
export function UpdatedAge({ ageSec, className }: UpdatedAgeProps) {
  if (ageSec === null) return null;

  return (
    <span
      className={cn("font-data text-[11px] tabular", className)}
      aria-label={`Data updated ${humanizeAge(ageSec)}`}
    >
      {`updated ${humanizeAge(ageSec)}`}
    </span>
  );
}
