"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealth, getModelPerformance } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${ok ? "bg-[#22c55e]" : "bg-[#ef4444]"}`}
    />
  );
}

export default function SystemStatus() {
  const { data: health, isLoading: healthLoading, error: healthErr } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const { data: perf, isLoading: perfLoading } = useQuery({
    queryKey: ["model-performance"],
    queryFn: getModelPerformance,
    staleTime: 300_000,
  });

  const overall = !healthLoading && !healthErr && health?.status === "ok";

  return (
    <div className="flex flex-col gap-4 h-full overflow-auto">
      <div className="flex items-center gap-3 shrink-0">
        <h1 className="text-sm font-mono font-bold text-[#e5e7eb]">System Status</h1>
        <Badge className={overall ? "bg-[#22c55e]/20 text-[#22c55e]" : "bg-[#ef4444]/20 text-[#ef4444]"}>
          {overall ? "HEALTHY" : "DEGRADED"}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* API Health */}
        <Card className="bg-[#12141a] border-[#1e2028]">
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-mono text-[#6b7280]">API Health</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            {healthLoading && <Skeleton className="h-24 w-full bg-[#1e2028]" />}
            {healthErr && (
              <div className="text-[#ef4444] text-xs font-mono">
                Cannot reach API: {(healthErr as Error).message}
              </div>
            )}
            {health && (
              <div className="space-y-2">
                {Object.entries(health.model_status).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2 text-xs font-mono">
                    <StatusDot ok={v !== "unavailable"} />
                    <span className="text-[#9ca3af]">{k}</span>
                    <span className="text-[#4b5563] ml-auto">{v}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Model Freshness */}
        <Card className="bg-[#12141a] border-[#1e2028]">
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-mono text-[#6b7280]">Model Freshness</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            {perfLoading && <Skeleton className="h-24 w-full bg-[#1e2028]" />}
            {perf && (
              <div className="space-y-2">
                {[
                  { name: "Win Probability", ts: perf.win_probability, metric: `Acc: ${perf.win_probability.accuracy}%` },
                  { name: "Player Props", ts: perf.player_props, metric: `R²: ${perf.player_props.r_squared}` },
                  { name: "xFG Model", ts: perf.xfG_model, metric: `Brier: ${perf.xfG_model.brier_score}` },
                  { name: "Matchup", ts: perf.matchup_model, metric: `R²: ${perf.matchup_model.r_squared}` },
                ].map(({ name, metric }) => (
                  <div key={name} className="flex items-center gap-2 text-xs font-mono">
                    <StatusDot ok />
                    <span className="text-[#9ca3af]">{name}</span>
                    <span className="text-[#4b5563] ml-auto">{metric}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Pipeline Config */}
        <Card className="bg-[#12141a] border-[#1e2028]">
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-mono text-[#6b7280]">Pipeline Config</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <div className="space-y-2 text-xs font-mono">
              {[
                { k: "CV Games (local)", v: "29 usable (9 CLEAN + 20 PARTIAL of 75)" },
                { k: "Target", v: "80 CLEAN games" },
                { k: "Models", v: "75 .pkl/.json" },
                { k: "Props tracked", v: "7 (pts/reb/ast/fg3m/blk/tov/stl)" },
                { k: "VRAM flush interval", v: "3000 frames" },
                { k: "Phase", v: "13.5 complete" },
                { k: "NBA_OFFLINE", v: process.env.NEXT_PUBLIC_NBA_OFFLINE ?? "1" },
              ].map(({ k, v }) => (
                <div key={k} className="flex justify-between">
                  <span className="text-[#6b7280]">{k}</span>
                  <span className="text-[#9ca3af]">{v}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* API Endpoint Inventory */}
        <Card className="bg-[#12141a] border-[#1e2028]">
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-mono text-[#6b7280]">API Endpoints</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 max-h-48 overflow-auto">
            <div className="space-y-1 text-[10px] font-mono">
              {[
                "GET /health",
                "POST /simulate_game",
                "POST /over_prob",
                "POST /simulate",
                "GET /props/{player_id}",
                "GET /edge/{game_id}",
                "GET /win-prob/{game_id}",
                "GET /lineup/{team}",
                "POST /backtest/{stat}",
                "GET /predictions/shot",
                "GET /predictions/win",
                "GET /predictions/player-impact",
                "POST /predictions/injury-risk",
                "POST /predictions/breakout",
                "POST /predictions/game",
                "GET /predictions/today",
                "GET /predictions/props/{player_id}",
                "GET /analytics/shot-chart",
                "GET /analytics/tracking",
                "POST /chat",
                "GET /analytics/clv-summary",
                "GET /analytics/edges/today",
                "GET /stitch/dashboard/overview",
                "GET /stitch/models/performance",
              ].map((ep) => (
                <div key={ep} className="flex items-center gap-2">
                  <StatusDot ok />
                  <span className="text-[#6b7280]">{ep}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
