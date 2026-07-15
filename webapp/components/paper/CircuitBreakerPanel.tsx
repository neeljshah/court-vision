"use client";

// CircuitBreakerPanel.tsx -- per-market LIVE/CAPPED/UNKNOWN volume-breaker chips.
// "Volume follows measured CLV" -- never confidence.
//
// HONESTY RAILS: color=meaning only (text-up=LIVE, text-stale=CAPPED,
// muted=UNKNOWN). No $ anywhere. ASCII only. <=300 LOC.

import type { ExecutionBlock } from "@/lib/paperToday";
import { EMPTY_CELL } from "@/lib/tokens";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";
import { cn } from "@/lib/utils";

function stateClass(state: string): string {
  if (state === "LIVE") return "border-success text-up";
  if (state === "CAPPED") return "border-warning text-stale";
  return "border-muted-foreground text-muted-foreground";
}

export function CircuitBreakerPanel({
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
    <div data-testid="circuit-breaker-panel">
      <Panel>
        <PanelHead
          title="Volume breaker"
          asOf={asOf}
          stale={stale}
          right={
            <span className="font-data text-[9px] text-faint">
              volume follows measured CLV
            </span>
          }
        />
        {marketTypes.length === 0 ? (
          <p className="px-4 py-3 text-[11px] text-faint">
            No markets to gate yet -- breaker state populates once bets are
            placed per market.
          </p>
        ) : (
          <ul className="flex flex-wrap gap-3 px-4 py-3" aria-label="breaker state per market">
            {marketTypes.map((mt) => {
              const e = byMarket![mt];
              return (
                <li
                  key={mt}
                  className={cn(
                    "flex flex-col gap-1 border px-3 py-2",
                    stateClass(e.state),
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-data text-[11px] text-foreground">{mt}</span>
                    <span
                      className={cn(
                        "border px-1.5 py-px text-[9px] font-bold tracking-wider",
                        stateClass(e.state),
                      )}
                    >
                      {e.state}
                    </span>
                  </div>
                  <div className="flex gap-3 font-data text-[10px] text-faint">
                    <span>
                      cap/day <Num>{e.cap_per_day ?? EMPTY_CELL}</Num>
                    </span>
                    <span>
                      placed today <Num>{e.placed_today ?? EMPTY_CELL}</Num>
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </div>
  );
}
