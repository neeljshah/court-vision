"use client";

import { useState } from "react";
import { useBets, useEVHistory, useLastEventTs } from "@/lib/store";
import type { Bet } from "@/lib/types";
import { cn, evClass, fmtOdds, fmtPct, tierClass } from "@/lib/utils";
import { Panel, PanelHead, Num, Delta } from "@/components/ui/terminal";
import { Sparkline } from "./Sparkline";
import { WhyDrawer } from "./WhyDrawer";

// Feed considered stale if the last bus event is older than this.
const STALE_AFTER_MS = 30_000;

function fmtClock(ms: number | null): string | null {
  if (ms == null) return null;
  return new Date(ms).toLocaleTimeString("en-US", { hour12: false });
}

export function TopBets() {
  const bets = useBets();
  const lastEventTs = useLastEventTs();
  const [active, setActive] = useState<Bet | null>(null);
  const stale = lastEventTs != null && Date.now() - lastEventTs > STALE_AFTER_MS;

  if (!bets.length) {
    return (
      <Panel>
        <PanelHead title="Top bets" asOf={fmtClock(lastEventTs)} stale={stale} />
        <p className="p-4 text-sm text-faint">
          No qualifying bets yet -- waiting for first projection + line refresh.
        </p>
      </Panel>
    );
  }

  return (
    <Panel>
      <PanelHead title="Top bets - live" asOf={fmtClock(lastEventTs)} stale={stale} />
      <ul className="divide-y divide-border">
        {bets.slice(0, 8).map((b) => (
          <BetRow
            key={`${b.player_id}|${b.stat}|${b.side}`}
            bet={b}
            onClick={() => setActive(b)}
          />
        ))}
      </ul>
      <WhyDrawer bet={active} onClose={() => setActive(null)} />
    </Panel>
  );
}

function BetRow({ bet, onClick }: { bet: Bet; onClick: () => void }) {
  const evKey = `${bet.player_id}|${bet.stat}|${bet.side}`;
  const history = useEVHistory(evKey);
  const evs = history.map((p) => p.ev);
  const tier = bet.tier || "C";

  return (
    <li
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()}
      className="flex cursor-pointer items-center gap-4 px-3 py-2 transition hover:bg-surface-2"
    >
      <span
        className={cn(
          "border px-2 py-0.5 font-data text-xs",
          tierClass(tier),
        )}
      >
        {tier}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-foreground">
          <span className="font-medium">{bet.name}</span>
          <span className="text-muted-foreground">
            {" "}
            &middot; {bet.stat.toUpperCase()} {bet.side.toUpperCase()} {bet.line}
          </span>
          <span className="text-faint">
            {" "}
            &middot; {bet.book} {fmtOdds(bet.odds)}
          </span>
        </div>
        <div className="mt-0.5 text-xs text-faint">
          <Num>
            proj {bet.projected_final?.toFixed(1)} &middot; cur {(bet.current ?? 0).toFixed(0)}
          </Num>
          {typeof bet.delta === "number" && bet.delta !== 0 ? (
            <span className="ml-1">
              (<Delta value={bet.delta} digits={1} />)
            </span>
          ) : null}
        </div>
      </div>
      <Num className={cn("w-16 text-right text-sm", evClass(bet.ev))}>
        {fmtPct(bet.ev)}
      </Num>
      <Num className="w-12 text-right text-xs text-muted-foreground">
        K {(bet.kelly * 100).toFixed(1)}%
      </Num>
      <Sparkline data={evs} positive={bet.ev >= 0} />
    </li>
  );
}
