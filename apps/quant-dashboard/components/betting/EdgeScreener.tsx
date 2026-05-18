"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StarBadge } from "@/components/betting/StarBadge";
import { useBetSlipStore } from "@/lib/stores/betSlip";
import { usePortfolioStore } from "@/lib/stores/portfolio";
import { useEdgesToday } from "@/lib/hooks/useEdges";
import { edgeStars } from "@/lib/utils";
import type { EdgeDetectorEdge } from "@/lib/types/api";

function EdgeRow({ e }: { e: EdgeDetectorEdge }) {
  const bankroll = usePortfolioStore((s) => s.bankroll);
  const addEdge = useBetSlipStore((s) => s.addEdge);
  const isAtLimit = useBetSlipStore((s) => s.isAtLimit);
  const stars = edgeStars(e.edge);

  return (
    <div className="flex items-center gap-2 py-2 border-b border-[#1e2028] last:border-0 text-xs">
      <StarBadge stars={stars} />
      <div className="flex-1 min-w-0">
        <div className="font-medium text-[#e5e7eb] truncate">
          {e.player ?? e.team ?? "—"} {e.stat ? `(${e.stat.toUpperCase()})` : ""}
        </div>
        <div className="text-[#6b7280] font-mono">
          line {e.line ?? "—"} · proj {e.projection?.toFixed(1) ?? "—"}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className={`font-mono font-bold ${stars >= 2 ? "text-[#10b981]" : "text-[#3b82f6]"}`}>
          +{((e.edge ?? 0) * 100).toFixed(1)}%
        </div>
        <div className="text-[#6b7280] font-mono text-[10px]">
          ${((e.kelly ?? 0) * bankroll * 0.25).toFixed(0)}
        </div>
      </div>
      <button
        disabled={isAtLimit}
        onClick={() => addEdge(e, bankroll)}
        className="text-[10px] px-2 py-1 rounded bg-[#1e2028] text-[#f97316] hover:bg-[#f97316]/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
      >
        + slip
      </button>
    </div>
  );
}

export function EdgeScreener() {
  const { data, isLoading, error } = useEdgesToday(0.03);

  return (
    <Card className="bg-[#12141a] border-[#1e2028] h-full flex flex-col">
      <CardHeader className="pb-2 pt-3 px-4">
        <CardTitle className="text-sm font-mono text-[#e5e7eb] flex items-center justify-between">
          <span>Edge Screener</span>
          {data && (
            <Badge className="bg-[#1e2028] text-[#6b7280] text-[10px]">
              {data.count}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3 flex-1 overflow-auto">
        {isLoading && (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-10 w-full bg-[#1e2028]" />
            ))}
          </div>
        )}
        {error && (
          <div className="text-[#ef4444] text-xs font-mono">{error.message}</div>
        )}
        {data?.edges.map((e, i) => (
          <EdgeRow key={i} e={e} />
        ))}
        {data?.count === 0 && (
          <div className="text-[#6b7280] text-xs text-center py-8">
            No edges above threshold
          </div>
        )}
      </CardContent>
    </Card>
  );
}
