"use client";

// RealizedIngameClvPanel.tsx -- per-sport, per-horizon (30s/2m/5m) realized
// in-game price-move summary (probability points; NOT closing-line value --
// see ingame_realized_clv.py's module docstring). Honest empty/small-n state
// derived from the data itself, never a hardcoded count.
//
// HONESTY RAILS: UNITS/probability only, no $. n==0 -> "--", never fabricated.
// ASCII only. <=300 LOC.

import type { ExecutionBlock, RealizedIngameHorizon } from "@/lib/paperToday";
import { EMPTY_CELL } from "@/lib/tokens";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";

const HORIZON_LABELS: Record<string, string> = {
  "30s": "30s",
  "120s": "2m",
  "300s": "5m",
};

function fmtPp(v: number | null): string {
  if (v == null) return EMPTY_CELL;
  const s = v.toFixed(2);
  return v >= 0 ? `+${s}pp` : `${s}pp`;
}

function ppClass(v: number | null): string {
  if (v == null) return "text-faint";
  if (v > 0) return "text-up";
  if (v < 0) return "text-down";
  return "text-muted-foreground";
}

export function RealizedIngameClvPanel({
  execution,
  asOf,
  stale,
}: {
  execution: ExecutionBlock;
  asOf?: string | null;
  stale?: boolean;
}) {
  const bySport = execution?.realized_ingame ?? null;
  const sports = bySport ? Object.keys(bySport) : [];
  const totalGraded = sports.reduce((sum, sport) => {
    const horizons = bySport![sport];
    return sum + Object.values(horizons).reduce((s, h) => s + h.n, 0);
  }, 0);

  return (
    <div data-testid="realized-ingame-clv-panel">
      <Panel>
        <PanelHead
          title="Realized in-game price move"
          asOf={asOf}
          stale={stale}
          right={
            <span className="font-data text-[9px] text-faint">
              probability points; not closing-line value
            </span>
          }
        />
        {sports.length === 0 || totalGraded === 0 ? (
          <p className="px-4 py-3 text-[11px] text-faint">
            No in-game placements gradeable yet -- this measures the market
            move a fixed horizon after placement, separate from CLV.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table
              className="w-full min-w-[420px] text-left"
              data-testid="realized-ingame-clv-table"
            >
              <thead>
                <tr className="border-b border-border">
                  {["Sport", "Horizon", "Median move", "% favorable", "n"].map(
                    (h) => (
                      <th
                        key={h}
                        className="py-1.5 px-3 font-data text-[9px] uppercase tracking-wider text-faint"
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {sports.flatMap((sport) => {
                  const horizons = bySport![sport];
                  return Object.keys(horizons).map((h) => {
                    const stat: RealizedIngameHorizon = horizons[h];
                    if (stat.n === 0) return null;
                    return (
                      <tr
                        key={`${sport}-${h}`}
                        className="border-b border-border last:border-0 hover:bg-surface-2"
                      >
                        <td className="py-1.5 px-3 font-data text-[11px] text-foreground">
                          {sport}
                        </td>
                        <td className="py-1.5 px-3 font-data text-[11px] text-muted-foreground">
                          {HORIZON_LABELS[h] ?? h}
                        </td>
                        <td className="py-1.5 px-3">
                          <Num className={`text-[11px] ${ppClass(stat.median_pp)}`}>
                            {fmtPp(stat.median_pp)}
                          </Num>
                        </td>
                        <td className="py-1.5 px-3">
                          <Num className="text-[11px] text-muted-foreground">
                            {stat.pct_favorable != null
                              ? `${stat.pct_favorable.toFixed(0)}%`
                              : EMPTY_CELL}
                          </Num>
                        </td>
                        <td className="py-1.5 px-3">
                          <Num className="text-[11px] text-faint">{stat.n}</Num>
                        </td>
                      </tr>
                    );
                  });
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
