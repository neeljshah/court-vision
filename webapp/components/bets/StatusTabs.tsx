"use client";

// StatusTabs.tsx -- Live / Pregame / Done tab switcher for the Bets board.
//
// A simple tab row that filters the board by bet status. Three fixed tabs:
//   Live     = in-play games with active bets
//   Pregame  = today's future tip-offs
//   Done     = settled games (outcome graded)
//
// ARIA tab pattern (WCAG 3.5 / APG):
//   - role=tablist wrapping role=tab buttons
//   - Roving tabindex: active tab tabIndex=0, inactive tabIndex=-1
//   - ArrowRight/ArrowLeft/Home/End move selection AND focus
//   - aria-controls on each tab references the panel region (panelId prop)
//   - aria-selected reflects the current selection
//
// Renders in a consistent amber/green/slate tonal system matching the existing
// app design. UNITS only; no $ mention. Controlled externally (value+onChange).

import * as React from "react";
import { useRef, useCallback } from "react";
import { cn } from "@/lib/utils";

export type BetStatus = "live" | "pregame" | "done";

export interface StatusTabsProps {
  value: BetStatus;
  onChange: (v: BetStatus) => void;
  counts?: { live?: number; pregame?: number; done?: number };
  /** id of the panel region this tablist controls (aria-controls target). */
  panelId?: string;
}

const TABS: { key: BetStatus; label: string }[] = [
  { key: "live", label: "Live" },
  { key: "pregame", label: "Pregame" },
  { key: "done", label: "Done" },
];

const DEFAULT_PANEL_ID = "bets-board-panel";

export function StatusTabs({
  value,
  onChange,
  counts,
  panelId = DEFAULT_PANEL_ID,
}: StatusTabsProps) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  // Roving-focus key handler: ArrowRight/Left/Home/End move selection + focus.
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>, currentIndex: number) => {
      let nextIndex: number | null = null;

      if (e.key === "ArrowRight") {
        nextIndex = (currentIndex + 1) % TABS.length;
      } else if (e.key === "ArrowLeft") {
        nextIndex = (currentIndex - 1 + TABS.length) % TABS.length;
      } else if (e.key === "Home") {
        nextIndex = 0;
      } else if (e.key === "End") {
        nextIndex = TABS.length - 1;
      }

      if (nextIndex !== null) {
        e.preventDefault();
        onChange(TABS[nextIndex].key);
        // Move DOM focus to the new active tab immediately.
        tabRefs.current[nextIndex]?.focus();
      }
    },
    [onChange],
  );

  return (
    <nav
      role="tablist"
      aria-label="Bet status filter"
      className="flex gap-4 border-b border-border"
    >
      {TABS.map((tab, index) => {
        const isActive = value === tab.key;
        const count = counts?.[tab.key];
        return (
          <button
            key={tab.key}
            ref={(el) => { tabRefs.current[index] = el; }}
            id={`status-tab-${tab.key}`}
            role="tab"
            aria-selected={isActive}
            aria-controls={panelId}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onChange(tab.key)}
            onKeyDown={(e) => handleKeyDown(e, index)}
            className={cn(
              "inline-flex items-center gap-1.5 border-b-2 px-1 py-2",
              "font-data text-[11px] uppercase tracking-wide",
              "transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
              isActive
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
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
