"use client";

// SortControls.tsx -- sort selector for the best-bets card board.
//
// Supports two sort axes that surface the honest ranking:
//   confidence -- highest-confidence calibrated divergence cards first
//   tier        -- S > A > B > C (tier-quality ordering)
// "edge" framing is intentionally absent; this is CALIBRATION not a profit claim.
// Controlled externally (value + onChange).

import * as React from "react";
import { cn } from "@/lib/utils";

export type SortKey = "confidence" | "tier";

export interface SortControlsProps {
  value: SortKey;
  onChange: (v: SortKey) => void;
}

const OPTIONS: { key: SortKey; label: string; tip: string }[] = [
  {
    key: "confidence",
    label: "Confidence",
    tip: "Highest-confidence model-vs-market divergence first",
  },
  {
    key: "tier",
    label: "Tier",
    tip: "S > A > B > C quality tier ordering",
  },
];

export function SortControls({ value, onChange }: SortControlsProps) {
  return (
    <div className="flex items-center gap-2" role="group" aria-label="Sort best bets">
      <span className="microlabel">Sort</span>
      {OPTIONS.map((opt) => {
        const isActive = value === opt.key;
        return (
          <button
            key={opt.key}
            type="button"
            title={opt.tip}
            aria-label={`Sort by ${opt.label}`}
            onClick={() => onChange(opt.key)}
            className={cn(
              "border px-2.5 py-1 font-data text-[10px] uppercase tracking-wide",
              "transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
              isActive
                ? "border-primary text-foreground"
                : "border-border bg-transparent text-muted-foreground hover:text-foreground",
            )}
            aria-pressed={isActive}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
