"use client";

import { usePortfolioStore } from "@/lib/stores/portfolio";
import type { OpenBet } from "@/lib/types/api";

function TickerItem({ bet }: { bet: OpenBet }) {
  const pnl = bet.est_pnl ?? 0;
  const color = pnl >= 0 ? "text-[#22c55e]" : "text-[#ef4444]";
  return (
    <span className="inline-flex items-center gap-1 px-3 border-r border-[#1e2028] shrink-0">
      <span className="text-[#9ca3af]">
        {bet.player} {bet.direction?.toUpperCase()} {bet.line} {bet.stat?.toUpperCase()}
      </span>
      {bet.est_pnl !== undefined && (
        <span className={`${color} font-mono`}>
          {pnl >= 0 ? "+" : ""}{(pnl * 100).toFixed(1)}%
        </span>
      )}
    </span>
  );
}

export function ActivePositionsTicker() {
  const bets = usePortfolioStore((s) => s.openBets);

  if (!bets.length) return null;

  return (
    <div className="h-8 bg-[#0d0f14] border-t border-[#1e2028] flex items-center overflow-hidden text-xs font-mono shrink-0">
      <div className="px-3 text-[#f97316] font-bold shrink-0 border-r border-[#1e2028]">
        LIVE
      </div>
      <div className="flex animate-marquee items-center">
        {bets.map((b) => (
          <TickerItem key={b.id} bet={b} />
        ))}
      </div>
    </div>
  );
}
