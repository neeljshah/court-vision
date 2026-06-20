"use client";

// GameMarketSurface.tsx -- the FULL coherent market surface for a game.
//
// Wraps the shared MarketSurfaceTable to render EVERY market | side | line |
// model probability | provenance off the one engine matrix (so tennis's full set
// of markets, soccer's full surface, NBA's spread/total/ML all show coherently).
// A Legend explains the terms. There is NO price / payout / $ column -- only the
// model (devigged) probability. Missing prob renders an honest "--".
//
// HONESTY RAILS: probability only -- NO $. Empty surface -> honest empty state.

import * as React from "react";
import type { Report } from "@/lib/api";
import { MarketSurfaceTable, Legend, InfoTip } from "@/components/depth";

export interface GameMarketSurfaceProps {
  report: Report | null;
  sport: string;
  className?: string;
}

// Descriptive per-sport engine label for the surface provenance column.
function engineLabel(sport: string): string {
  if (sport === "nba") return "possession MC";
  if (sport === "soccer" || sport === "soccer_intl") return "Dixon-Coles EW Poisson";
  if (sport === "mlb") return "MOV-Elo";
  if (sport === "tennis") return "Elo";
  return "rating-anchored";
}

/** The full coherent market surface for a game (no $ -- probability only). */
export function GameMarketSurface({
  report,
  sport,
  className,
}: GameMarketSurfaceProps) {
  const markets = report?.markets ?? [];
  const n = markets.length;

  return (
    <section
      aria-label="Full market surface"
      className={
        "rounded-lg border border-slate-800 bg-bg-panel p-3 " + (className ?? "")
      }
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h3 className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">
            full market surface ({n})
          </h3>
          <InfoTip
            text={
              "Every market on this game, read off ONE coherent engine matrix " +
              "spined by a single anchor. The marginals are coherent. We show the " +
              "model (devigged) probability only -- there is no price column."
            }
            ariaLabel="what is the market surface?"
          />
        </div>
      </div>

      <MarketSurfaceTable
        markets={markets}
        model={engineLabel(sport)}
        phase="pregame"
        caption="One coherent market surface, spined by a single anchor. Probability only -- no price."
      />

      <Legend
        className="mt-3"
        title="terms"
        terms={["probability", "devig", "provenance", "vs_close"]}
      />
    </section>
  );
}
