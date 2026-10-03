"use client";

import type { ClvScoreboard } from "@/lib/p5api";
import { fmtPct } from "@/lib/utils";
import { StatTile, meanClvClass, EMPTY_CELL, type TallySummary } from "./paperTradingHelpers";

export function PaperTradingTally({ tally, clv, loading }: {
  tally: TallySummary | null;
  clv: ClvScoreboard | null;
  loading: boolean;
}) {
  return (
      <div
        aria-label="Running paper tally"
        data-testid="running-tally"
        className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7"
      >
        <StatTile label="Open" testId="tally-open" loading={loading}
          value={loading || !tally ? EMPTY_CELL : String(tally.nOpen)} />
        <StatTile label="Settled" testId="tally-settled" loading={loading}
          value={loading || !tally ? EMPTY_CELL : String(tally.nSettled)} />
        <StatTile label="Win" testId="tally-win" loading={loading}
          value={loading || !tally ? EMPTY_CELL : String(tally.nWin)}
          valueClass={tally && tally.nWin > 0 ? "text-success" : "text-foreground"} />
        <StatTile label="Loss" testId="tally-loss" loading={loading}
          value={loading || !tally ? EMPTY_CELL : String(tally.nLoss)}
          valueClass={tally && tally.nLoss > 0 ? "text-danger" : "text-foreground"} />
        <StatTile label="Push" testId="tally-push" loading={loading}
          value={loading || !tally ? EMPTY_CELL : String(tally.nPush)} />
        <StatTile label="Units staked" testId="tally-units-staked" loading={loading}
          value={loading || !tally ? EMPTY_CELL : tally.unitsStaked.toFixed(2)} />
        <StatTile
          label="Mean CLV" testId="clv-mean-clv" loading={loading}
          valueClass={meanClvClass(clv)}
          value={
            loading ? EMPTY_CELL
            : clv?.mean_clv_pct != null ? fmtPct(clv.mean_clv_pct / 100)
            : EMPTY_CELL
          }
          note={
            !loading && clv?.clv_is_proxy
              ? `(proxy close${clv.n_proxy ? `, n=${clv.n_proxy}` : ""})`
              : undefined
          }
        />
      </div>
  );
}
