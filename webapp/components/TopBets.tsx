"use client";

import { useState } from "react";
import { useBets, useEVHistory } from "@/lib/store";
import type { Bet } from "@/lib/types";
import { cn, evClass, fmtOdds, fmtPct, tierClass } from "@/lib/utils";
import { Sparkline } from "./Sparkline";
import { WhyDrawer } from "./WhyDrawer";

export function TopBets() {
  const bets = useBets();
  const [active, setActive] = useState<Bet | null>(null);

  if (!bets.length) {
    return (
      <section className="rounded-xl border border-slate-800 bg-bg-panel p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Top bets
        </h2>
        <p className="mt-4 text-sm text-slate-500">
          No qualifying bets yet — waiting for first projection + line refresh.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-bg-panel">
      <header className="border-b border-slate-800 px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Top bets · live
        </h2>
      </header>
      <ul className="divide-y divide-slate-800">
        {bets.slice(0, 8).map((b) => (
          <BetRow
            key={`${b.player_id}|${b.stat}|${b.side}`}
            bet={b}
            onClick={() => setActive(b)}
          />
        ))}
      </ul>
      <WhyDrawer bet={active} onClose={() => setActive(null)} />
    </section>
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
      className="flex cursor-pointer items-center gap-4 px-5 py-3 transition hover:bg-bg-subtle"
    >
      <span
        className={cn(
          "rounded-md border px-2 py-0.5 text-xs font-mono",
          tierClass(tier),
        )}
      >
        {tier}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-slate-100">
          <span className="font-medium">{bet.name}</span>
          <span className="text-slate-400">
            {" "}
            · {bet.stat.toUpperCase()} {bet.side.toUpperCase()} {bet.line}
          </span>
          <span className="text-slate-500">
            {" "}
            · {bet.book} {fmtOdds(bet.odds)}
          </span>
        </div>
        <div className="mt-0.5 text-xs text-slate-500 tabular">
          proj {bet.projected_final?.toFixed(1)} · cur {(bet.current ?? 0).toFixed(0)}
          {typeof bet.delta === "number" && bet.delta !== 0 ? (
            <span className={bet.delta > 0 ? " text-tier-a" : " text-red-400"}>
              {" "}({bet.delta > 0 ? "+" : ""}{bet.delta.toFixed(1)})
            </span>
          ) : null}
        </div>
      </div>
      <div className={cn("w-16 text-right text-sm tabular", evClass(bet.ev))}>
        {fmtPct(bet.ev)}
      </div>
      <div className="w-12 text-right text-xs text-slate-400 tabular">
        K {(bet.kelly * 100).toFixed(1)}%
      </div>
      <Sparkline data={evs} positive={bet.ev >= 0} />
    </li>
  );
}
