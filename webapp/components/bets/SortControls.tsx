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
    <div className="flex items-center gap-2">
      <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
        Sort
      </span>
      {OPTIONS.map((opt) => {
        const isActive = value === opt.key;
        return (
          <button
            key={opt.key}
            title={opt.tip}
            onClick={() => onChange(opt.key)}
            className={cn(
              "rounded border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide",
              "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-500",
              isActive
                ? "border-slate-400 bg-slate-800 text-slate-100"
                : "border-slate-700 bg-transparent text-slate-500 hover:text-slate-300",
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
