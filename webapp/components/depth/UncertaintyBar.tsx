"use client";

// UncertaintyBar.tsx -- a probability with its held-out-residual uncertainty band.
//
// Renders a horizontal 0..100% track with the point probability marked and a
// shaded interval [low, high] around it (the held-out residual band). All values
// are PROBABILITIES (0..1), shown as percents -- there is NO $ field and no
// price. A missing/invalid prob renders an honest empty state, never a fake 0.
//
// Accessible: implemented as role="meter" with aria-valuenow / min / max so the
// point estimate is announced; the band is described in aria-label.

import * as React from "react";
import { cn } from "@/lib/utils";
import { InfoTip } from "./InfoTip";
import { Num } from "@/components/ui/terminal";
import { EMPTY_CELL } from "@/lib/tokens";

export interface UncertaintyBarProps {
  /** Point probability in [0, 1]. null/NaN -> honest empty state. */
  prob: number | null | undefined;
  /** Lower bound of the held-out residual band in [0, 1] (optional). */
  low?: number | null;
  /** Upper bound of the held-out residual band in [0, 1] (optional). */
  high?: number | null;
  /** Optional caption (e.g. "P(home win)"). */
  label?: string;
  className?: string;
}

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const pct = (x: number) => `${(clamp01(x) * 100).toFixed(1)}%`;

const isProb = (x: unknown): x is number =>
  typeof x === "number" && Number.isFinite(x) && x >= 0 && x <= 1;

/** Probability + uncertainty band, probability-only (no $). */
export function UncertaintyBar({
  prob,
  low,
  high,
  label,
  className,
}: UncertaintyBarProps) {
  if (!isProb(prob)) {
    return (
      <div className={cn("text-xs text-faint", className)}>
        {label && <span className="mr-1">{label}</span>}
        <Num>
          <span title="no probability available">{EMPTY_CELL}</span>
        </Num>
      </div>
    );
  }

  const lo = isProb(low) ? clamp01(Math.min(low, prob)) : prob;
  const hi = isProb(high) ? clamp01(Math.max(high, prob)) : prob;
  const hasBand = hi > lo;
  const aria = hasBand
    ? `${label ?? "probability"} ${pct(prob)}, band ${pct(lo)} to ${pct(hi)}`
    : `${label ?? "probability"} ${pct(prob)}`;

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1 microlabel">
          {label ?? "probability"}
          <InfoTip term="uncertainty" />
        </span>
        <Num className="text-foreground">
          {pct(prob)}
          {hasBand && (
            <span className="ml-1 text-faint">
              [{pct(lo)}, {pct(hi)}]
            </span>
          )}
        </Num>
      </div>
      <div
        role="meter"
        aria-label={aria}
        aria-valuenow={Number((prob * 100).toFixed(1))}
        aria-valuemin={0}
        aria-valuemax={100}
        className="relative h-2 w-full border border-border bg-surface-2"
      >
        {hasBand && (
          <span
            aria-hidden
            className="absolute top-0 h-full bg-muted-foreground/30"
            style={{ left: pct(lo), width: pct(hi - lo) }}
          />
        )}
        <span
          aria-hidden
          className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2 bg-foreground"
          style={{ left: pct(prob) }}
        />
      </div>
    </div>
  );
}
