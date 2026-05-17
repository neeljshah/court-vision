"use client";

import { usePortfolioStore } from "@/lib/stores/portfolio";
import { useBetSlipStore } from "@/lib/stores/betSlip";
import { Badge } from "@/components/ui/badge";

function fmt(n: number, prefix = "$") {
  return `${prefix}${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function pctColor(n: number) {
  return n >= 0 ? "text-[#22c55e]" : "text-[#ef4444]";
}

export function TopBar() {
  const summary = usePortfolioStore((s) => s.summary);
  const slipCount = useBetSlipStore((s) => s.entries.length);

  const pnl = summary?.total_pnl ?? 0;
  const roi = summary?.roi ?? 0;
  const clv = summary?.clv_avg ?? 0;
  const drawdown = summary?.drawdown_pct ?? 0;

  return (
    <header className="h-11 border-b border-[#1e2028] bg-[#0d0f14] flex items-center px-4 gap-6 shrink-0">
      <div className="flex items-center gap-5 font-mono text-xs flex-1">
        <span className="text-[#6b7280]">P&L</span>
        <span className={pctColor(pnl)}>{pnl >= 0 ? "+" : "-"}{fmt(pnl)}</span>

        <span className="text-[#1e2028]">|</span>

        <span className="text-[#6b7280]">ROI</span>
        <span className={pctColor(roi)}>{roi >= 0 ? "+" : ""}{(roi * 100).toFixed(2)}%</span>

        <span className="text-[#1e2028]">|</span>

        <span className="text-[#6b7280]">CLV</span>
        <span className={pctColor(clv)}>{clv >= 0 ? "+" : ""}{(clv * 100).toFixed(2)}%</span>

        <span className="text-[#1e2028]">|</span>

        <span className="text-[#6b7280]">Drawdown</span>
        <span className={pctColor(-drawdown)}>{(drawdown * 100).toFixed(1)}%</span>
      </div>

      {slipCount > 0 && (
        <Badge className="bg-[#f97316] text-black text-xs font-mono">
          {slipCount} in slip
        </Badge>
      )}
    </header>
  );
}
