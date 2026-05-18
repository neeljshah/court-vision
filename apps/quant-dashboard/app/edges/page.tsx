"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getEdgesToday, getAltLadder } from "@/lib/api";
import { usePortfolioStore } from "@/lib/stores/portfolio";
import { useBetSlipStore } from "@/lib/stores/betSlip";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { StarBadge } from "@/components/betting/StarBadge";
import { edgeStars } from "@/lib/utils";
import type { EdgeDetectorEdge, AltLineLadderRow } from "@/lib/types/api";

const STATS = ["pts", "reb", "ast", "fg3m", "blk", "tov", "stl"];

function confColor(c?: number): string {
  if (!c) return "text-[#6b7280]";
  if (c >= 0.75) return "text-[#10b981]";
  if (c >= 0.6) return "text-[#3b82f6]";
  return "text-[#9ca3af]";
}

function AltLadder({ player, stat }: { player: string; stat: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["alt-ladder", player, stat],
    queryFn: () => getAltLadder(player, stat),
    staleTime: 300_000,
  });

  if (isLoading) return <div className="p-2"><Skeleton className="h-20 w-full bg-[#1e2028]" /></div>;
  if (error) return <div className="p-2 text-[#ef4444] text-xs font-mono">{(error as Error).message}</div>;
  if (!data?.rows.length) return <div className="p-2 text-[#6b7280] text-xs">No alt lines available</div>;

  return (
    <div className="px-4 py-2 bg-[#0d0f14] border-t border-[#1e2028]">
      <div className="text-[10px] font-mono text-[#6b7280] mb-2 uppercase tracking-widest">Alt Line Ladder</div>
      <div className="grid grid-cols-5 gap-1 text-[10px] font-mono text-[#4b5563] mb-1">
        <span>Line</span><span>O%</span><span>Fair</span><span>EV</span><span>Kelly $</span>
      </div>
      {data.rows.slice(0, 10).map((row: AltLineLadderRow, i: number) => (
        <div key={i} className="grid grid-cols-5 gap-1 text-[10px] font-mono py-0.5 border-b border-[#1e2028]/50">
          <span className="text-[#e5e7eb]">{row.line}</span>
          <span className={row.over_prob > 0.55 ? "text-[#22c55e]" : "text-[#9ca3af]"}>
            {(row.over_prob * 100).toFixed(0)}%
          </span>
          <span className="text-[#9ca3af]">{row.fair_odds > 0 ? "+" : ""}{row.fair_odds}</span>
          <span className={row.ev > 0 ? "text-[#22c55e]" : "text-[#ef4444]"}>
            {row.ev > 0 ? "+" : ""}{(row.ev * 100).toFixed(1)}%
          </span>
          <span className="text-[#6b7280]">${row.stake?.toFixed(0) ?? "—"}</span>
        </div>
      ))}
    </div>
  );
}

type SortKey = "edge" | "ev" | "kelly" | "confidence";

function EdgeRow({ e, bankroll }: { e: EdgeDetectorEdge; bankroll: number }) {
  const [expanded, setExpanded] = useState(false);
  const addEdge = useBetSlipStore((s) => s.addEdge);
  const isAtLimit = useBetSlipStore((s) => s.isAtLimit);
  const stars = edgeStars(e.edge);
  const player = e.player ?? e.team ?? "";
  const stat = e.stat ?? "";

  return (
    <>
      <tr
        className="border-b border-[#1e2028] hover:bg-[#12141a]/50 cursor-pointer text-xs"
        onClick={() => setExpanded((x) => !x)}
      >
        <td className="py-2 px-3"><StarBadge stars={stars} /></td>
        <td className="py-2 px-3 font-medium text-[#e5e7eb]">{player || "—"}</td>
        <td className="py-2 px-3 font-mono text-[#9ca3af]">{stat.toUpperCase()}</td>
        <td className="py-2 px-3 font-mono text-[#9ca3af]">
          {e.direction === "over" ? "↑" : e.direction === "under" ? "↓" : "—"}
        </td>
        <td className="py-2 px-3 font-mono">{e.line ?? "—"}</td>
        <td className="py-2 px-3 font-mono text-[#3b82f6]">{e.projection?.toFixed(1) ?? "—"}</td>
        <td className="py-2 px-3 font-mono font-bold text-[#10b981]">
          {e.edge !== undefined ? `+${(e.edge * 100).toFixed(1)}%` : "—"}
        </td>
        <td className="py-2 px-3 font-mono">
          {e.ev !== undefined ? `${e.ev > 0 ? "+" : ""}${(e.ev * 100).toFixed(1)}%` : "—"}
        </td>
        <td className="py-2 px-3 font-mono">
          ${((e.kelly ?? 0) * bankroll * 0.25).toFixed(0)}
        </td>
        <td className={`py-2 px-3 font-mono ${confColor(e.confidence as number)}`}>
          {e.confidence !== undefined ? `${((e.confidence as number) * 100).toFixed(0)}%` : "—"}
        </td>
        <td className="py-2 px-3 font-mono text-[#6b7280] text-[10px]">
          {e.ci_low !== undefined && e.ci_high !== undefined
            ? `${e.ci_low?.toFixed(1)}–${e.ci_high?.toFixed(1)}`
            : "—"}
        </td>
        <td className="py-2 px-3">
          <button
            disabled={isAtLimit}
            onClick={(ev) => { ev.stopPropagation(); addEdge(e, bankroll); }}
            className="text-[10px] px-2 py-1 rounded bg-[#1e2028] text-[#f97316] hover:bg-[#f97316]/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            + slip
          </button>
        </td>
      </tr>
      {expanded && player && stat && (
        <tr>
          <td colSpan={12} className="p-0">
            <AltLadder player={player} stat={stat} />
          </td>
        </tr>
      )}
    </>
  );
}

export default function EdgeScanner() {
  const bankroll = usePortfolioStore((s) => s.bankroll);
  const [filterStat, setFilterStat] = useState("");
  const [filterPlayer, setFilterPlayer] = useState("");
  const [minEdge, setMinEdge] = useState(0.03);
  const [sortKey, setSortKey] = useState<SortKey>("edge");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["edges-today-full", minEdge],
    queryFn: () => getEdgesToday(minEdge),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

  const edges = useMemo(() => {
    let rows = data?.edges ?? [];
    if (filterStat) rows = rows.filter((e) => e.stat?.toLowerCase() === filterStat.toLowerCase());
    if (filterPlayer) rows = rows.filter((e) => e.player?.toLowerCase().includes(filterPlayer.toLowerCase()));
    rows = [...rows].sort((a, b) => ((b[sortKey] as number) ?? 0) - ((a[sortKey] as number) ?? 0));
    return rows;
  }, [data, filterStat, filterPlayer, sortKey]);

  function SortTh({ k, label }: { k: SortKey; label: string }) {
    return (
      <th
        className={`py-2 px-3 text-left text-[10px] font-mono uppercase tracking-widest cursor-pointer select-none ${
          sortKey === k ? "text-[#f97316]" : "text-[#4b5563] hover:text-[#9ca3af]"
        }`}
        onClick={() => setSortKey(k)}
      >
        {label}{sortKey === k ? " ▾" : ""}
      </th>
    );
  }

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Filters */}
      <div className="flex items-center gap-3 shrink-0">
        <h1 className="text-sm font-mono font-bold text-[#e5e7eb]">Edge Scanner</h1>
        {data && (
          <Badge className="bg-[#1e2028] text-[#6b7280]">{edges.length} edges</Badge>
        )}
        <div className="flex-1" />
        <Input
          placeholder="Player..."
          value={filterPlayer}
          onChange={(e) => setFilterPlayer(e.target.value)}
          className="w-36 h-7 text-xs bg-[#12141a] border-[#1e2028] font-mono"
        />
        <select
          value={filterStat}
          onChange={(e) => setFilterStat(e.target.value)}
          className="h-7 px-2 text-xs bg-[#12141a] border border-[#1e2028] rounded text-[#9ca3af] font-mono"
        >
          <option value="">All stats</option>
          {STATS.map((s) => <option key={s} value={s}>{s.toUpperCase()}</option>)}
        </select>
        <select
          value={minEdge}
          onChange={(e) => setMinEdge(Number(e.target.value))}
          className="h-7 px-2 text-xs bg-[#12141a] border border-[#1e2028] rounded text-[#9ca3af] font-mono"
        >
          <option value={0.03}>Edge ≥ 3%</option>
          <option value={0.05}>Edge ≥ 5%</option>
          <option value={0.08}>Edge ≥ 8%</option>
          <option value={0.12}>Edge ≥ 12%</option>
        </select>
        <button
          onClick={() => refetch()}
          className="h-7 px-3 text-xs bg-[#12141a] border border-[#1e2028] rounded text-[#6b7280] hover:text-[#e5e7eb] font-mono transition-colors"
        >
          ↻
        </button>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto rounded border border-[#1e2028]">
        <table className="w-full text-xs border-collapse">
          <thead className="sticky top-0 bg-[#0d0f14] z-10">
            <tr>
              <th className="py-2 px-3 text-left text-[10px] font-mono uppercase tracking-widest text-[#4b5563]">Stars</th>
              <th className="py-2 px-3 text-left text-[10px] font-mono uppercase tracking-widest text-[#4b5563]">Player</th>
              <th className="py-2 px-3 text-left text-[10px] font-mono uppercase tracking-widest text-[#4b5563]">Stat</th>
              <th className="py-2 px-3 text-left text-[10px] font-mono uppercase tracking-widest text-[#4b5563]">Dir</th>
              <th className="py-2 px-3 text-left text-[10px] font-mono uppercase tracking-widest text-[#4b5563]">Line</th>
              <th className="py-2 px-3 text-left text-[10px] font-mono uppercase tracking-widest text-[#4b5563]">Proj</th>
              <SortTh k="edge" label="Edge%" />
              <SortTh k="ev" label="EV" />
              <SortTh k="kelly" label="Kelly$" />
              <SortTh k="confidence" label="Conf" />
              <th className="py-2 px-3 text-left text-[10px] font-mono uppercase tracking-widest text-[#4b5563]">CI 80%</th>
              <th className="py-2 px-3" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={12} className="py-8 text-center">
                  <div className="space-y-2 px-4">
                    {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-8 w-full bg-[#1e2028]" />)}
                  </div>
                </td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={12} className="py-8 text-center text-[#ef4444] font-mono text-xs">
                  {(error as Error).message}
                </td>
              </tr>
            )}
            {edges.map((e, i) => (
              <EdgeRow key={i} e={e} bankroll={bankroll} />
            ))}
            {!isLoading && edges.length === 0 && !error && (
              <tr>
                <td colSpan={12} className="py-12 text-center text-[#6b7280] font-mono text-xs">
                  No edges above threshold
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
