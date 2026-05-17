"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getOpenBets, getPortfolioSummary, logBet, getCLVSummary } from "@/lib/api";
import { useBetSlipStore } from "@/lib/stores/betSlip";
import { usePortfolioStore } from "@/lib/stores/portfolio";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { OpenBet } from "@/lib/types/api";

const MAX_BETS = 20;
const MAX_DRAWDOWN = 0.15;

function PortfolioGuards() {
  const summary = usePortfolioStore((s) => s.summary);
  const drawdown = summary?.drawdown_pct ?? 0;
  const openCount = summary?.open_count ?? 0;
  const atMaxBets = openCount >= MAX_BETS;
  const atMaxDrawdown = drawdown >= MAX_DRAWDOWN;

  if (!atMaxBets && !atMaxDrawdown) return null;

  return (
    <div className="space-y-2 shrink-0">
      {atMaxDrawdown && (
        <div className="flex items-center gap-2 p-3 rounded border border-[#ef4444]/30 bg-[#ef4444]/10 text-xs font-mono text-[#ef4444]">
          ⚠ Drawdown {(drawdown * 100).toFixed(1)}% — at or above 15% limit. Execution disabled.
        </div>
      )}
      {atMaxBets && (
        <div className="flex items-center gap-2 p-3 rounded border border-[#f97316]/30 bg-[#f97316]/10 text-xs font-mono text-[#f97316]">
          ⚠ Max open bets reached ({MAX_BETS}). Close positions before adding new ones.
        </div>
      )}
    </div>
  );
}

function BetSlipBuilder() {
  const entries = useBetSlipStore((s) => s.entries);
  const removeEdge = useBetSlipStore((s) => s.removeEdge);
  const updateStake = useBetSlipStore((s) => s.updateStake);
  const clear = useBetSlipStore((s) => s.clear);
  const bankroll = usePortfolioStore((s) => s.bankroll);
  const summary = usePortfolioStore((s) => s.summary);
  const qc = useQueryClient();

  const atMaxDrawdown = (summary?.drawdown_pct ?? 0) >= MAX_DRAWDOWN;
  const totalStake = entries.reduce((acc, e) => acc + e.stake, 0);
  const totalPct = totalStake / bankroll;

  const { mutate: executePaper, isPending } = useMutation({
    mutationFn: async () => {
      for (const e of entries) {
        await logBet({
          player: e.edge.player ?? "",
          stat: e.edge.stat ?? "",
          direction: (e.edge.direction as "over" | "under") ?? "over",
          line: e.edge.line ?? 0,
          stake: e.stake,
          odds: -110,
          game_id: e.edge.game_id,
        });
      }
    },
    onSuccess: () => {
      clear();
      qc.invalidateQueries({ queryKey: ["open-bets"] });
      qc.invalidateQueries({ queryKey: ["portfolio-summary"] });
    },
  });

  if (!entries.length) {
    return (
      <div className="text-[#6b7280] text-xs font-mono text-center py-12">
        No bets in slip — click &quot;+ slip&quot; on any edge
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-[10px] font-mono text-[#6b7280] uppercase tracking-widest">
        Bet Slip ({entries.length}/{MAX_BETS})
      </div>

      {entries.map((e, i) => (
        <div key={i} className="flex items-center gap-3 p-3 rounded bg-[#12141a] border border-[#1e2028] text-xs">
          <div className="flex-1 min-w-0">
            <div className="font-medium text-[#e5e7eb] truncate">
              {e.edge.player ?? e.edge.team} {e.edge.direction?.toUpperCase()} {e.edge.line} {e.edge.stat?.toUpperCase()}
            </div>
            <div className="text-[#6b7280] font-mono text-[10px]">
              edge {((e.edge.edge ?? 0) * 100).toFixed(1)}% · {(e.kellyFraction * 100).toFixed(0)}% Kelly
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[#6b7280] font-mono text-[10px]">$</span>
            <input
              type="number"
              value={e.stake.toFixed(0)}
              onChange={(ev) => updateStake(i, Number(ev.target.value))}
              className="w-20 h-7 px-2 text-xs bg-[#0a0b0f] border border-[#1e2028] rounded font-mono text-[#e5e7eb]"
            />
            <button
              onClick={() => removeEdge(i)}
              className="text-[#4b5563] hover:text-[#ef4444] transition-colors"
            >
              ✕
            </button>
          </div>
        </div>
      ))}

      <div className="flex items-center justify-between text-xs font-mono border-t border-[#1e2028] pt-3">
        <div className="text-[#6b7280]">
          Total: <span className="text-[#e5e7eb]">${totalStake.toFixed(0)}</span>
          <span className="text-[#4b5563]"> ({(totalPct * 100).toFixed(1)}% bankroll)</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => clear()}
            className="px-3 py-1.5 rounded border border-[#1e2028] text-[#6b7280] hover:text-[#e5e7eb] transition-colors"
          >
            Clear
          </button>
          <button
            disabled={atMaxDrawdown || isPending}
            onClick={() => executePaper()}
            className="px-3 py-1.5 rounded bg-[#f97316] text-black font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#ea6c0a] transition-colors"
          >
            {isPending ? "Logging..." : "Execute Paper"}
          </button>
        </div>
      </div>
    </div>
  );
}

function OpenPositionsTable() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["open-bets"],
    queryFn: getOpenBets,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const bets: OpenBet[] = data?.bets ?? [];

  return (
    <div className="overflow-auto rounded border border-[#1e2028]">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-[#0d0f14]">
          <tr>
            {["Player", "Stat", "Dir", "Line", "Stake", "Entry", "Est P&L", "CLV", "Status"].map((h) => (
              <th key={h} className="py-2 px-3 text-left text-[10px] font-mono uppercase tracking-widest text-[#4b5563]">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {isLoading && (
            <tr><td colSpan={9} className="py-8 px-4">
              <Skeleton className="h-24 w-full bg-[#1e2028]" />
            </td></tr>
          )}
          {error && (
            <tr><td colSpan={9} className="py-6 text-center text-[#ef4444] font-mono text-xs">
              {(error as Error).message}
            </td></tr>
          )}
          {bets.map((bet) => (
            <tr key={bet.id} className="border-b border-[#1e2028] hover:bg-[#12141a]/50">
              <td className="py-2 px-3 font-medium text-[#e5e7eb]">{bet.player}</td>
              <td className="py-2 px-3 font-mono text-[#9ca3af]">{bet.stat?.toUpperCase()}</td>
              <td className="py-2 px-3 font-mono">{bet.direction === "over" ? "↑" : "↓"}</td>
              <td className="py-2 px-3 font-mono">{bet.line}</td>
              <td className="py-2 px-3 font-mono">${bet.stake?.toFixed(0)}</td>
              <td className="py-2 px-3 font-mono text-[#6b7280]">{bet.odds > 0 ? "+" : ""}{bet.odds}</td>
              <td className={`py-2 px-3 font-mono ${(bet.est_pnl ?? 0) >= 0 ? "text-[#22c55e]" : "text-[#ef4444]"}`}>
                {bet.est_pnl !== undefined ? `${bet.est_pnl >= 0 ? "+" : ""}$${bet.est_pnl.toFixed(0)}` : "—"}
              </td>
              <td className={`py-2 px-3 font-mono ${(bet.clv ?? 0) >= 0 ? "text-[#22c55e]" : "text-[#ef4444]"}`}>
                {bet.clv !== undefined ? `${bet.clv >= 0 ? "+" : ""}${(bet.clv * 100).toFixed(2)}%` : "—"}
              </td>
              <td className="py-2 px-3">
                <Badge className="bg-[#1e2028] text-[#6b7280] text-[10px]">{bet.status}</Badge>
              </td>
            </tr>
          ))}
          {!isLoading && bets.length === 0 && !error && (
            <tr><td colSpan={9} className="py-10 text-center text-[#6b7280] font-mono text-xs">
              No open positions
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// Mock equity curve for structure — replace with real CLV data when endpoint returns history
function EquityCurve() {
  const { data } = useQuery({
    queryKey: ["clv-summary"],
    queryFn: getCLVSummary,
    staleTime: 300_000,
  });

  // Scaffold — real implementation populates from CLV history
  const mockData = [...Array(30)].map((_, i) => ({
    day: i + 1,
    equity: 10000 + Math.random() * 500 - 200 + i * 15,
  }));

  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={mockData} margin={{ left: -20, top: 5 }}>
        <defs>
          <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#f97316" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="day" tick={{ fontSize: 9, fill: "#6b7280" }} />
        <YAxis tick={{ fontSize: 9, fill: "#6b7280" }} />
        <Tooltip
          contentStyle={{ background: "#12141a", border: "1px solid #1e2028", fontSize: 11 }}
          formatter={(v) => [`$${Number(v).toFixed(0)}`, "Equity"]}
        />
        <Area type="monotone" dataKey="equity" stroke="#f97316" fill="url(#eq)" strokeWidth={1.5} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export default function PositionManager() {
  return (
    <div className="flex flex-col gap-4 h-full overflow-auto">
      <h1 className="text-sm font-mono font-bold text-[#e5e7eb] shrink-0">Position Manager</h1>

      <PortfolioGuards />

      <div className="grid grid-cols-3 gap-4 shrink-0">
        <div className="col-span-2">
          <Card className="bg-[#12141a] border-[#1e2028]">
            <CardHeader className="pb-2 pt-3 px-4">
              <CardTitle className="text-xs font-mono text-[#6b7280]">Equity Curve</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <EquityCurve />
            </CardContent>
          </Card>
        </div>
        <Card className="bg-[#12141a] border-[#1e2028]">
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-mono text-[#6b7280]">Bet Slip</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <BetSlipBuilder />
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="open" className="flex-1">
        <TabsList className="bg-[#12141a] border border-[#1e2028]">
          <TabsTrigger value="open" className="text-xs font-mono">Open</TabsTrigger>
          <TabsTrigger value="history" className="text-xs font-mono">History</TabsTrigger>
        </TabsList>
        <TabsContent value="open">
          <OpenPositionsTable />
        </TabsContent>
        <TabsContent value="history">
          <Card className="bg-[#12141a] border-[#1e2028]">
            <CardContent className="p-8 text-center text-[#6b7280] text-xs font-mono">
              Closed position history loads from bet_log.json via /api/portfolio/close
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
