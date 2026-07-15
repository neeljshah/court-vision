"use client";
// BestBetsStates.tsx -- Presentational state components extracted from
// BestBetsBoard.tsx to keep that file under the 300-LOC rail.
// Exports: UnavailableReasonBanner, EmptySection.

import type { BetStatus } from "./StatusTabs";

// UnavailableReasonBanner -- per-sport honest "unavailable" panel shown when a
// sport returned a status='unavailable' response. Surfaces the real reason from
// the produce service rather than a blank panel (edge_claimed=false always shown).
export function UnavailableReasonBanner({ sport, reason }: { sport: string; reason: string }) {
  return (
    <div
      role="status"
      aria-label={`${sport} unavailable: ${reason}`}
      data-testid={`unavailable-banner-${sport}`}
      className="border border-border bg-surface-2 px-3 py-2"
    >
      <span className="font-data text-[10px] font-semibold text-stale uppercase tracking-wide">
        {sport.toUpperCase()} -- no tradable cards
      </span>
      <p className="mt-0.5 font-data text-[10px] text-muted-foreground">
        {reason}
      </p>
      <p className="mt-0.5 font-data text-[10px] text-faint">
        edge_claimed=false -- calibration only
      </p>
    </div>
  );
}

export function EmptySection({ status, label }: { status: BetStatus; label: string }) {
  const msgs: Record<BetStatus, string> = {
    live: "No live in-play games with qualifying bets right now.",
    pregame: "No qualifying pregame bets for today's slate.",
    done: "No settled bets graded yet.",
  };
  return (
    <div className="border border-border bg-surface-2 px-4 py-8 text-center">
      <span className="font-data text-xs text-muted-foreground">{msgs[status]}</span>
      <p className="mt-1 text-[11px] text-faint">{label}</p>
    </div>
  );
}
