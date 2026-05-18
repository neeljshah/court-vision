"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { GamePrediction } from "@/lib/types/api";
import Link from "next/link";

interface Props {
  game: GamePrediction;
}

function WinBar({ prob, home, away }: { prob: number; home: string; away: string }) {
  const homePct = Math.round(prob * 100);
  const awayPct = 100 - homePct;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs font-mono text-[#9ca3af]">
        <span>{home}</span>
        <span>{away}</span>
      </div>
      <div className="h-2 rounded-full bg-[#1e2028] flex overflow-hidden">
        <div
          className="h-full bg-[#f97316] rounded-l-full transition-all"
          style={{ width: `${homePct}%` }}
        />
        <div
          className="h-full bg-[#3b82f6] rounded-r-full transition-all"
          style={{ width: `${awayPct}%` }}
        />
      </div>
      <div className="flex justify-between text-xs font-mono">
        <span className="text-[#f97316]">{homePct}%</span>
        <span className="text-[#3b82f6]">{awayPct}%</span>
      </div>
    </div>
  );
}

export function GameCard({ game }: Props) {
  const home = game.home_team ?? "HOME";
  const away = game.away_team ?? "AWAY";
  const winProb = (game.home_win_prob ?? game.win_prob ?? 0.5) as number;
  const gameId = `${home}-${away}`.toLowerCase();
  const edges = (game.kelly_edges as unknown[])?.length ?? 0;

  return (
    <Link href={`/game/${gameId}?home=${home}&away=${away}`}>
      <Card className="bg-[#12141a] border-[#1e2028] card-glow cursor-pointer hover:border-[#f97316]/30 transition-all">
        <CardHeader className="pb-2 pt-3 px-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 font-mono text-sm font-bold">
              <span>{home}</span>
              <span className="text-[#4b5563]">vs</span>
              <span>{away}</span>
            </div>
            {edges > 0 && (
              <Badge className="bg-[#f97316]/20 text-[#f97316] text-[10px]">
                {edges} edge{edges !== 1 ? "s" : ""}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-3">
          <WinBar prob={winProb} home={home} away={away} />
        </CardContent>
      </Card>
    </Link>
  );
}

export function GameCardSkeleton() {
  return (
    <Card className="bg-[#12141a] border-[#1e2028]">
      <CardHeader className="pb-2 pt-3 px-4">
        <Skeleton className="h-4 w-32 bg-[#1e2028]" />
      </CardHeader>
      <CardContent className="px-4 pb-3 space-y-2">
        <Skeleton className="h-2 w-full bg-[#1e2028]" />
        <Skeleton className="h-3 w-20 bg-[#1e2028]" />
      </CardContent>
    </Card>
  );
}
