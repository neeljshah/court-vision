"use client";

import { use } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { predictGame, getWinProb, getEdge } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useBetSlipStore } from "@/lib/stores/betSlip";
import { usePortfolioStore } from "@/lib/stores/portfolio";
import { StarBadge } from "@/components/betting/StarBadge";
import { BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

function WinProbBar({ homeProb, home, away }: { homeProb: number; home: string; away: string }) {
  const homePct = Math.round(homeProb * 100);
  const awayPct = 100 - homePct;
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm font-mono font-bold">
        <span className="text-[#f97316]">{home} {homePct}%</span>
        <span className="text-[#3b82f6]">{away} {awayPct}%</span>
      </div>
      <div className="h-4 rounded-full bg-[#1e2028] flex overflow-hidden">
        <div className="h-full bg-[#f97316]" style={{ width: `${homePct}%` }} />
        <div className="h-full bg-[#3b82f6]" style={{ width: `${awayPct}%` }} />
      </div>
    </div>
  );
}

function ScoreDistChart({ distribution }: { distribution?: { a: number[]; b: number[] } }) {
  if (!distribution) return <div className="text-[#6b7280] text-xs text-center py-8">No simulation data</div>;
  const combined = distribution.a.map((_, i) => ({
    margin: i,
    freq: distribution.a[i] - (distribution.b[i] ?? 0),
  })).slice(0, 40);

  return (
    <ResponsiveContainer width="100%" height={120}>
      <BarChart data={combined} margin={{ left: -20 }}>
        <XAxis dataKey="margin" tick={{ fontSize: 9, fill: "#6b7280" }} />
        <YAxis tick={{ fontSize: 9, fill: "#6b7280" }} />
        <Tooltip
          contentStyle={{ background: "#12141a", border: "1px solid #1e2028", fontSize: 11 }}
          labelStyle={{ color: "#9ca3af" }}
        />
        <Bar dataKey="freq" radius={[2, 2, 0, 0]}>
          {combined.map((entry, i) => (
            <Cell key={i} fill={entry.freq >= 0 ? "#f97316" : "#3b82f6"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

interface Prop {
  player: string;
  stat: string;
  line: number;
  projection?: number;
  edge?: number;
  confidence?: number;
  stars?: number;
}

function PropRow({ p, bankroll }: { p: Prop; bankroll: number }) {
  const addEdge = useBetSlipStore((s) => s.addEdge);
  const stars = p.stars ?? (p.edge ? (p.edge >= 0.12 ? 3 : p.edge >= 0.08 ? 2 : p.edge >= 0.05 ? 1 : 0) : 0);
  return (
    <tr className="border-b border-[#1e2028] hover:bg-[#12141a]/50 text-xs">
      <td className="py-1.5 px-3 font-medium text-[#e5e7eb]">{p.player}</td>
      <td className="py-1.5 px-3 font-mono text-[#9ca3af]">{p.stat.toUpperCase()}</td>
      <td className="py-1.5 px-3 font-mono">{p.line}</td>
      <td className="py-1.5 px-3 font-mono text-[#3b82f6]">{p.projection?.toFixed(1) ?? "—"}</td>
      <td className="py-1.5 px-3 font-mono text-[#10b981]">
        {p.edge !== undefined ? `+${(p.edge * 100).toFixed(1)}%` : "—"}
      </td>
      <td className="py-1.5 px-3"><StarBadge stars={stars} /></td>
      <td className="py-1.5 px-3">
        <button
          onClick={() => addEdge(p as unknown as Parameters<typeof addEdge>[0], bankroll)}
          className="text-[10px] px-2 py-0.5 rounded bg-[#1e2028] text-[#f97316] hover:bg-[#f97316]/20 transition-colors"
        >
          + slip
        </button>
      </td>
    </tr>
  );
}

export default function GameDeepDive({ params }: { params: Promise<{ gameId: string }> }) {
  const { gameId } = use(params);
  const search = useSearchParams();
  const home = search.get("home") ?? "";
  const away = search.get("away") ?? "";
  const bankroll = usePortfolioStore((s) => s.bankroll);

  const { data: pred, isLoading: predLoading, error: predErr } = useQuery({
    queryKey: ["game-prediction", home, away],
    queryFn: () => predictGame({ home_team: home, away_team: away, bankroll }),
    enabled: !!(home && away),
    staleTime: 300_000,
  });

  const { data: wp } = useQuery({
    queryKey: ["win-prob", gameId, home, away],
    queryFn: () => getWinProb(gameId, { home, away }),
    enabled: !!(home && away),
    staleTime: 60_000,
  });

  const { data: edgeData } = useQuery({
    queryKey: ["edge", gameId, home, away],
    queryFn: () => getEdge(gameId, { home, away }),
    enabled: !!(home && away),
    staleTime: 60_000,
  });

  const homeProb = wp?.home_win_prob ?? (pred?.home_win_prob as number) ?? 0.5;
  const props = (pred?.props as Prop[]) ?? [];
  const kellyEdges = (pred?.kelly_edges as Prop[]) ?? [];
  const distribution = (pred as { score_distribution?: { a: number[]; b: number[] } })?.score_distribution;

  return (
    <div className="flex flex-col gap-4 h-full overflow-auto">
      {/* Header */}
      <div className="flex items-center gap-3 shrink-0">
        <h1 className="font-mono font-bold text-[#e5e7eb]">
          {home || "—"} vs {away || "—"}
        </h1>
        {wp?.source && (
          <Badge className="bg-[#1e2028] text-[#6b7280] text-[10px] font-mono">
            {wp.source}
          </Badge>
        )}
      </div>

      {/* Top row: win prob + sim distribution */}
      <div className="grid grid-cols-2 gap-4 shrink-0">
        <Card className="bg-[#12141a] border-[#1e2028]">
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-mono text-[#6b7280]">Win Probability</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            {predLoading ? (
              <Skeleton className="h-12 w-full bg-[#1e2028]" />
            ) : (
              <div className="space-y-3">
                <WinProbBar homeProb={homeProb} home={home} away={away} />
                {wp?.confidence_interval && (
                  <div className="text-[10px] font-mono text-[#4b5563]">
                    CI: [{wp.confidence_interval[0].toFixed(3)}, {wp.confidence_interval[1].toFixed(3)}]
                    {wp.inference_ms ? ` · ${wp.inference_ms.toFixed(0)}ms` : ""}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-[#12141a] border-[#1e2028]">
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-mono text-[#6b7280]">Score Distribution (10K sims)</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            {predLoading ? (
              <Skeleton className="h-28 w-full bg-[#1e2028]" />
            ) : (
              <ScoreDistChart distribution={distribution} />
            )}
          </CardContent>
        </Card>
      </div>

      {predErr && (
        <div className="text-[#ef4444] text-xs font-mono">{(predErr as Error).message}</div>
      )}

      {/* Tabs */}
      <Tabs defaultValue="props" className="flex-1">
        <TabsList className="bg-[#12141a] border border-[#1e2028]">
          <TabsTrigger value="props" className="text-xs font-mono">Props</TabsTrigger>
          <TabsTrigger value="edges" className="text-xs font-mono">Kelly Edges</TabsTrigger>
          <TabsTrigger value="signals" className="text-xs font-mono">Signals</TabsTrigger>
        </TabsList>

        <TabsContent value="props">
          <Card className="bg-[#12141a] border-[#1e2028]">
            <CardContent className="p-0">
              <table className="w-full">
                <thead>
                  <tr>
                    {["Player", "Stat", "Line", "Proj", "Edge", "Stars", ""].map((h) => (
                      <th key={h} className="py-2 px-3 text-left text-[10px] font-mono uppercase tracking-widest text-[#4b5563]">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {predLoading && (
                    <tr><td colSpan={7} className="py-8 text-center">
                      <Skeleton className="h-24 w-full bg-[#1e2028] mx-4" />
                    </td></tr>
                  )}
                  {props.map((p, i) => <PropRow key={i} p={p} bankroll={bankroll} />)}
                  {!predLoading && props.length === 0 && (
                    <tr><td colSpan={7} className="py-8 text-center text-[#6b7280] text-xs font-mono">
                      No prop data
                    </td></tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="edges">
          <Card className="bg-[#12141a] border-[#1e2028]">
            <CardContent className="p-4">
              {edgeData?.edges.length ? (
                <div className="space-y-2">
                  {edgeData.edges.map((e, i) => (
                    <div key={i} className="flex items-center gap-3 text-xs font-mono">
                      <span className="text-[#e5e7eb] font-medium">{e.team}</span>
                      <span className="text-[#10b981]">+{(e.edge * 100).toFixed(1)}%</span>
                      <span className="text-[#6b7280]">Kelly: ${((e.kelly ?? 0) * bankroll * 0.25).toFixed(0)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-[#6b7280] text-xs text-center py-8">No moneyline edges detected</div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="signals">
          <Card className="bg-[#12141a] border-[#1e2028]">
            <CardContent className="p-4">
              {pred ? (
                <pre className="text-[10px] font-mono text-[#9ca3af] overflow-auto max-h-64">
                  {JSON.stringify(pred, null, 2)}
                </pre>
              ) : (
                <div className="text-[#6b7280] text-xs text-center py-8">
                  {predLoading ? "Loading prediction..." : "No data"}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
