"use client";

// PerMarketClvStrips.tsx -- one row per market_type: 30d rolling MEDIAN CLV%
// (true-close preferred; the breaker's gating stat -- see circuit_breaker.py's
// 2026-07-15 decision, mean is a fat-tail-of-longshots artifact), sample size,
// and the honest true-close vs proxy-close split.
//
// HONESTY RAILS: UNITS/probability only, no $. median_clv_pct null (no graded
// rows yet) -> "--", NEVER a fabricated 0. ASCII only. <=300 LOC.

import type { ExecutionBlock } from "@/lib/paperToday";
import { EMPTY_CELL } from "@/lib/tokens";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";

function fmtClv(v: number | null): string {
  if (v == null) return EMPTY_CELL;
  const s = v.toFixed(2);
  return v >= 0 ? `+${s}%` : `${s}%`;
}

function clvClass(v: number | null): string {
  if (v == null) return "text-faint";
  if (v > 0) return "text-up";
  if (v < 0) return "text-down";
  return "text-muted-foreground";
}

export function PerMarketClvStrips({
  execution,
  asOf,
  stale,
}: {
  execution: ExecutionBlock;
  asOf?: string | null;
  stale?: boolean;
}) {
  const byMarket = execution?.by_market_type ?? null;
  const marketTypes = byMarket ? Object.keys(byMarket) : [];

  return (
    <div data-testid="per-market-clv-strips">
      <Panel>
        <PanelHead
          title="Median CLV by market (30d)"
          asOf={asOf}
          stale={stale}
          right={
            <span className="font-data text-[9px] text-faint">
              beat-the-close; calibration only
            </span>
          }
        />
        {marketTypes.length === 0 ? (
          <p className="px-4 py-3 text-[11px] text-faint">
            No placed bets yet -- rolling CLV populates per market as paper
            bets grade against the close.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] text-left" data-testid="per-market-clv-table">
              <thead>
                <tr className="border-b border-border">
                  {["Market", "Median CLV 30d", "n", "n proxy"].map((h) => (
                    <th
                      key={h}
                      className="py-1.5 px-3 font-data text-[9px] uppercase tracking-wider text-faint"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {marketTypes.map((mt) => {
                  const e = byMarket![mt];
                  return (
                    <tr key={mt} className="border-b border-border last:border-0 hover:bg-surface-2">
                      <td className="py-1.5 px-3 font-data text-[11px] text-foreground">{mt}</td>
                      <td className="py-1.5 px-3">
                        <Num className={`text-[11px] ${clvClass(e.median_clv_pct)}`}>
                          {fmtClv(e.median_clv_pct)}
                        </Num>
                      </td>
                      <td className="py-1.5 px-3">
                        <Num className="text-[11px] text-muted-foreground">{e.n}</Num>
                      </td>
                      <td className="py-1.5 px-3">
                        <Num className="text-[11px] text-faint">{e.n_proxy}</Num>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
