"use client";

// Published market references for a game, with per-row source and capture time.
// devigged_prob belongs to the market source, not the pregame model forecast.
//
// HONESTY RAILS: probability only -- NO $. Empty surface -> honest empty state.

import * as React from "react";
import type { Report } from "@/lib/api";
import { MarketSurfaceTable, Legend, InfoTip } from "@/components/depth";
import { Panel, PanelHead } from "@/components/ui/terminal";

export interface GameMarketSurfaceProps {
  report: Report | null;
  sport: string;
  className?: string;
}

/** The published market-reference surface for a game. */
export function GameMarketSurface({
  report,
  className,
}: GameMarketSurfaceProps) {
  const markets = report?.markets ?? [];
  const n = markets.length;

  return (
    <Panel className={className}>
      <PanelHead
        title={`full market surface (${n})`}
        right={
          <InfoTip
            text={
              "Devigged probabilities from each market source, with capture time " +
              "and proxy status. The model forecast is shown separately above."
            }
            ariaLabel="what is the market surface?"
          />
        }
      />

      <div className="p-3">
        <MarketSurfaceTable
          markets={markets}
          caption="Published market references. Source probabilities are separate from the model forecast."
        />

        <Legend
          className="mt-3"
          title="terms"
          terms={["probability", "devig", "provenance", "vs_close"]}
        />
      </div>
    </Panel>
  );
}
