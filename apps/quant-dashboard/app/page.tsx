"use client";

import { useQuery } from "@tanstack/react-query";
import { getDashboardOverview } from "@/lib/api";
import { usePortfolioStore } from "@/lib/stores/portfolio";
import { Card, CardContent } from "@/components/ui/card";
import { GameCard, GameCardSkeleton } from "@/components/game/GameCard";
import { EdgeScreener } from "@/components/betting/EdgeScreener";
import type { GamePrediction } from "@/lib/types/api";

function KPICard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="bg-[#12141a] border-[#1e2028]">
      <CardContent className="pt-4 pb-3 px-4">
        <div className="text-[10px] text-[#6b7280] font-mono uppercase tracking-widest mb-1">{label}</div>
        <div className="text-xl font-mono font-bold text-[#e5e7eb]">{value}</div>
        {sub && <div className="text-[10px] text-[#4b5563] font-mono mt-0.5">{sub}</div>}
      </CardContent>
    </Card>
  );
}

export default function CommandCenter() {
  const summary = usePortfolioStore((s) => s.summary);
  const bankroll = usePortfolioStore((s) => s.bankroll);

  const { data: overview, isLoading: ovLoading, error: ovErr } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: getDashboardOverview,
    staleTime: 120_000,
    refetchInterval: 120_000,
  });

  const games: GamePrediction[] = (overview?.today_games as GamePrediction[]) ?? [];

  return (
    <div className="flex gap-4 h-full max-h-[calc(100vh-11rem)]">
      {/* Portfolio KPIs */}
      <div className="w-48 shrink-0 flex flex-col gap-3">
        <h2 className="text-xs font-mono text-[#6b7280] uppercase tracking-widest">Portfolio</h2>
        <KPICard label="Bankroll" value={`$${bankroll.toLocaleString()}`} />
        <KPICard
          label="P&L"
          value={`${(summary?.total_pnl ?? 0) >= 0 ? "+" : ""}$${Math.abs(summary?.total_pnl ?? 0).toFixed(0)}`}
        />
        <KPICard label="ROI" value={`${((summary?.roi ?? 0) * 100).toFixed(1)}%`} />
        <KPICard label="CLV Avg" value={`${((summary?.clv_avg ?? 0) * 100).toFixed(2)}%`} />
        <KPICard label="Open Bets" value={`${summary?.open_count ?? 0}`} sub="max 20" />
        <KPICard label="Drawdown" value={`${((summary?.drawdown_pct ?? 0) * 100).toFixed(1)}%`} sub="limit 15%" />
        {overview && (
          <div className="mt-auto">
            <h3 className="text-[10px] font-mono text-[#4b5563] uppercase tracking-widest mb-2">System</h3>
            <div className="space-y-1 text-[10px] font-mono text-[#6b7280]">
              <div>Win prob: {overview.performance.win_probability_accuracy}%</div>
              <div>Games: {overview.performance.games_processed.toLocaleString()}</div>
              <div>Models: {overview.performance.models_trained}</div>
            </div>
          </div>
        )}
      </div>

      {/* Tonight's Slate */}
      <div className="flex-1 flex flex-col gap-3 overflow-hidden">
        <h2 className="text-xs font-mono text-[#6b7280] uppercase tracking-widest shrink-0">
          Tonight&apos;s Slate
        </h2>
        <div className="flex-1 overflow-auto grid grid-cols-1 gap-3 content-start">
          {ovLoading && [...Array(4)].map((_, i) => <GameCardSkeleton key={i} />)}
          {ovErr && <div className="text-[#ef4444] text-xs font-mono p-4">{(ovErr as Error).message}</div>}
          {games.map((g, i) => <GameCard key={i} game={g} />)}
          {!ovLoading && games.length === 0 && !ovErr && (
            <div className="text-[#6b7280] text-xs font-mono text-center py-12">
              No games in tonight&apos;s slate
            </div>
          )}
        </div>
      </div>

      {/* Edge Screener */}
      <div className="w-72 shrink-0 flex flex-col overflow-hidden">
        <h2 className="text-xs font-mono text-[#6b7280] uppercase tracking-widest mb-3 shrink-0">
          Edge Screener
        </h2>
        <div className="flex-1 overflow-hidden">
          <EdgeScreener />
        </div>
      </div>
    </div>
  );
}
