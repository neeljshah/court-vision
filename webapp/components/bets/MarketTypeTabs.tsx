"use client";

// MarketTypeTabs.tsx -- market-type filter for the Best Bets board so every
// market (Moneyline / Totals / Spreads / Props) is shown as its own bet without
// becoming an undifferentiated wall. "All" shows everything.
//
// market_type values from the board: moneyline | total | spread | prop.
// UNITS only; no $ mention. Controlled (value + onChange). ASCII only.

import * as React from "react";
import { cn } from "@/lib/utils";

export type MarketFilter = "all" | "moneyline" | "total" | "spread" | "prop";

export interface MarketTypeTabsProps {
  value: MarketFilter;
  onChange: (v: MarketFilter) => void;
  counts?: Partial<Record<MarketFilter, number>>;
  /** id of the tabpanel these tabs control (for aria-controls). */
  panelId?: string;
}

const TABS: { key: MarketFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "moneyline", label: "Moneyline" },
  { key: "total", label: "Totals" },
  { key: "spread", label: "Spreads" },
  { key: "prop", label: "Props" },
];

// Normalize a card's market_type into one filter bucket. Anything starting with
// "prop" (e.g. "prop:pts") maps to "prop".
export function marketBucket(marketType: string | null | undefined): MarketFilter {
  const m = (marketType ?? "").toLowerCase();
  if (m.startsWith("prop")) return "prop";
  if (m === "moneyline" || m === "ml") return "moneyline";
  if (m === "total" || m === "totals" || m === "ou" || m === "over_under") return "total";
  if (m === "spread" || m === "spreads" || m === "ats") return "spread";
  // Unknown markets fall under "all" only.
  return "all";
}

export function MarketTypeTabs({ value, onChange, counts, panelId }: MarketTypeTabsProps) {
  return (
    <nav
      role="tablist"
      aria-label="Market type filter"
      className="flex flex-wrap gap-1.5"
      data-testid="market-type-tabs"
    >
      {TABS.map((tab) => {
        const isActive = value === tab.key;
        const count = counts?.[tab.key];
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls={panelId}
            aria-label={`Show ${tab.label} bets`}
            onClick={() => onChange(tab.key)}
            data-testid={`market-tab-${tab.key}`}
            className={cn(
              "inline-flex items-center gap-1.5 border px-2.5 py-1",
              "font-data text-[11px] uppercase tracking-wide transition-colors",
              "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
              isActive
                ? "border-primary text-foreground"
                : "border-border bg-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
            {count != null && count > 0 ? (
              <span
                className={cn(
                  "inline-flex h-4 min-w-[1rem] items-center justify-center px-1",
                  "font-data text-[9px] tabular-nums",
                  isActive ? "text-primary" : "text-faint",
                )}
              >
                {count}
              </span>
            ) : null}
          </button>
        );
      })}
    </nav>
  );
}
