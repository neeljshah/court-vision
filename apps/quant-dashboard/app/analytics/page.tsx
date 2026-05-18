"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getModelPerformance, backtest, getCorrMatrix } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

const STATS = ["pts", "reb", "ast", "fg3m", "blk", "tov", "stl"];

function ModelPerfPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["model-performance"],
    queryFn: getModelPerformance,
    staleTime: 300_000,
  });

  if (isLoading) return <Skeleton className="h-40 w-full bg-[#1e2028]" />;
  if (error) return <div className="text-[#ef4444] text-xs font-mono">{(error as Error).message}</div>;
  if (!data) return null;

  const chartData = [
    { name: "Win Prob", accuracy: data.win_probability.accuracy, brier: data.win_probability.brier_score },
    { name: "xFG", brier: data.xfG_model.brier_score },
    { name: "Matchup", r2: data.matchup_model.r_squared },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Win Prob Acc", value: `${data.win_probability.accuracy}%` },
          { label: "Win Prob Brier", value: data.win_probability.brier_score.toFixed(3) },
          { label: "xFG Brier", value: data.xfG_model.brier_score.toFixed(3) },
          { label: "Matchup R²", value: data.matchup_model.r_squared.toFixed(3) },
        ].map((m) => (
          <Card key={m.label} className="bg-[#0d0f14] border-[#1e2028]">
            <CardContent className="pt-3 pb-3 px-4">
              <div className="text-[10px] font-mono text-[#6b7280] uppercase tracking-widest">{m.label}</div>
              <div className="text-lg font-mono font-bold text-[#e5e7eb] mt-1">{m.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>
      <div>
        <div className="text-xs font-mono text-[#6b7280] mb-3">Props R² by stat (CLAUDE.md reference)</div>
        <div className="grid grid-cols-7 gap-2">
          {[
            { s: "pts", r2: 0.47 }, { s: "reb", r2: 0.40 }, { s: "ast", r2: 0.46 },
            { s: "fg3m", r2: 0.28 }, { s: "blk", r2: 0.18 }, { s: "tov", r2: 0.25 }, { s: "stl", r2: 0.09 },
          ].map(({ s, r2 }) => (
            <div key={s} className="text-center">
              <div className="text-[10px] font-mono text-[#6b7280] uppercase">{s}</div>
              <div className={`text-sm font-mono font-bold ${r2 >= 0.4 ? "text-[#22c55e]" : r2 >= 0.25 ? "text-[#f97316]" : "text-[#ef4444]"}`}>
                {r2.toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function BacktestPanel() {
  const [stat, setStat] = useState("pts");
  const { data, isLoading, error } = useQuery({
    queryKey: ["backtest", stat],
    queryFn: () => backtest(stat),
    staleTime: 86_400_000,
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-xs font-mono text-[#6b7280]">Stat:</span>
        <select
          value={stat}
          onChange={(e) => setStat(e.target.value)}
          className="h-7 px-2 text-xs bg-[#12141a] border border-[#1e2028] rounded text-[#9ca3af] font-mono"
        >
          {STATS.map((s) => <option key={s} value={s}>{s.toUpperCase()}</option>)}
        </select>
      </div>
      {isLoading && <Skeleton className="h-32 w-full bg-[#1e2028]" />}
      {error && <div className="text-[#ef4444] text-xs font-mono">{(error as Error).message}</div>}
      {data && (
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: "N predictions", value: data.n.toLocaleString() },
            { label: "MAE", value: data.mae.toFixed(4) },
            { label: "Hit Rate Over", value: `${(data.hit_rate_over * 100).toFixed(1)}%` },
            { label: "ROI @ BEO", value: `${(data.roi_at_break_even_odds * 100).toFixed(2)}%` },
          ].map((m) => (
            <Card key={m.label} className="bg-[#0d0f14] border-[#1e2028]">
              <CardContent className="pt-3 pb-3 px-4">
                <div className="text-[10px] font-mono text-[#6b7280] uppercase tracking-widest">{m.label}</div>
                <div className="text-lg font-mono font-bold text-[#e5e7eb] mt-1">{m.value}</div>
              </CardContent>
            </Card>
          ))}
          {!data.passed_gate && (
            <div className="col-span-4 text-xs font-mono text-[#f97316] p-2 border border-[#f97316]/30 rounded">
              ⚠ Model did not pass quality gate for {stat.toUpperCase()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CorrHeatmap() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["corr-matrix"],
    queryFn: getCorrMatrix,
    staleTime: 3_600_000,
  });

  if (isLoading) return <Skeleton className="h-48 w-full bg-[#1e2028]" />;
  if (error) return <div className="text-[#ef4444] text-xs font-mono">{(error as Error).message}</div>;
  if (!data) return <div className="text-[#6b7280] text-xs">No correlation data available</div>;

  const { stats, matrix } = data;

  function cellColor(v: number): string {
    if (v >= 0.7) return "#dc2626";
    if (v >= 0.4) return "#f97316";
    if (v >= 0.2) return "#854d0e";
    if (v <= -0.4) return "#1d4ed8";
    return "#1e2028";
  }

  return (
    <div className="overflow-auto">
      <table className="text-[10px] font-mono border-collapse">
        <thead>
          <tr>
            <th className="p-2 text-[#4b5563]" />
            {stats.map((s) => <th key={s} className="p-2 text-[#6b7280] uppercase">{s}</th>)}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={stats[i]}>
              <td className="p-2 text-[#6b7280] uppercase font-bold">{stats[i]}</td>
              {row.map((v, j) => (
                <td
                  key={j}
                  className="p-2 text-center rounded"
                  style={{ background: cellColor(v), color: Math.abs(v) > 0.3 ? "#e5e7eb" : "#6b7280" }}
                >
                  {v.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AnalyticsLab() {
  return (
    <div className="flex flex-col gap-4 h-full overflow-auto">
      <h1 className="text-sm font-mono font-bold text-[#e5e7eb] shrink-0">Analytics Lab</h1>

      <Tabs defaultValue="performance" className="flex-1">
        <TabsList className="bg-[#12141a] border border-[#1e2028]">
          <TabsTrigger value="performance" className="text-xs font-mono">Model Performance</TabsTrigger>
          <TabsTrigger value="backtest" className="text-xs font-mono">Backtest</TabsTrigger>
          <TabsTrigger value="correlation" className="text-xs font-mono">Correlation</TabsTrigger>
          <TabsTrigger value="shotchart" className="text-xs font-mono">Shot Chart</TabsTrigger>
        </TabsList>

        <TabsContent value="performance">
          <Card className="bg-[#12141a] border-[#1e2028]">
            <CardHeader className="pb-2 pt-3 px-4">
              <CardTitle className="text-xs font-mono text-[#6b7280]">Model Performance</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <ModelPerfPanel />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="backtest">
          <Card className="bg-[#12141a] border-[#1e2028]">
            <CardHeader className="pb-2 pt-3 px-4">
              <CardTitle className="text-xs font-mono text-[#6b7280]">Prop Backtester</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <BacktestPanel />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="correlation">
          <Card className="bg-[#12141a] border-[#1e2028]">
            <CardHeader className="pb-2 pt-3 px-4">
              <CardTitle className="text-xs font-mono text-[#6b7280]">Prop Correlation Matrix</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <CorrHeatmap />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="shotchart">
          <Card className="bg-[#12141a] border-[#1e2028]">
            <CardContent className="p-8 text-center">
              <div className="text-[#6b7280] text-xs font-mono">
                D3 hexbin shot chart — requires game_id + shot_logs data
              </div>
              <div className="text-[#4b5563] text-[10px] font-mono mt-2">
                Use GET /analytics/shot-chart?game_id=X to fetch shot data
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
