"use client";

import type { ClvScoreboard } from "@/lib/p5api";
import { Unavailable } from "@/components/p6/Primitives";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";
import { StatTile, EMPTY_CELL, type TallySummary } from "./paperTradingHelpers";

// clv stays in the props for the page's feed wiring; no CLV figure renders
// (no closing-line-value reading exists -- lib/clvUnavailable.ts).
export function PaperTradingTally({ tally, loading }: {
  tally: TallySummary | null;
  clv?: ClvScoreboard | null;
  loading: boolean;
}) {
  return (
      <div
        aria-label="Running paper tally"
        data-testid="running-tally"
        className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5"
      >
        <StatTile label="Open" testId="tally-open" loading={loading}
          value={loading || !tally ? EMPTY_CELL : String(tally.nOpen)} />
        <StatTile label="Settled" testId="tally-settled" loading={loading}
          value={loading || !tally ? EMPTY_CELL : String(tally.nSettled)} />
        <StatTile label="Push" testId="tally-push" loading={loading}
          value={loading || !tally ? EMPTY_CELL : String(tally.nPush)} />
        <StatTile label="Units staked" testId="tally-units-staked" loading={loading}
          value={loading || !tally ? EMPTY_CELL : tally.unitsStaked.toFixed(2)} />
        <div className="col-span-2 sm:col-span-4 lg:col-span-5" data-testid="clv-mean-clv">
          <Unavailable reason={CLV_UNAVAILABLE} />
        </div>
      </div>
  );
}
