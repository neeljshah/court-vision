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
      className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2"
    >
      <span className="font-mono text-[10px] font-semibold text-amber-400 uppercase tracking-wide">
        {sport.toUpperCase()} -- no tradable cards
      </span>
      <p className="mt-0.5 font-mono text-[10px] text-slate-400">
        {reason}
      </p>
      <p className="mt-0.5 font-mono text-[10px] text-slate-600">
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
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-8 text-center">
      <span className="font-mono text-xs text-slate-500">{msgs[status]}</span>
      <p className="mt-1 text-[11px] text-slate-600">{label}</p>
    </div>
  );
}
