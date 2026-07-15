/**
 * SideProb.tsx -- winner-clarity primitive shared across /live and any game
 * card that needs "who's winning/favored" at a glance. Renders both teams
 * with abbrev + prob; the CURRENTLY LEADING side (by score when live, by
 * higher model prob when pregame) gets text-up (green), the trailing side
 * text-down (red). Tie or unknown data stays neutral -- never fabricated.
 *
 * This is distinct from model-amber/market-blue source coloring (see
 * ModelMarketBar) -- SideProb answers "who leads", not "which source".
 */

import { cn } from "@/lib/utils";
import { Num } from "@/components/ui/terminal";

export interface SideProbSide {
  label: string;
  prob: number | null; // 0-1 win prob, null = unknown
  score?: number | null; // live score, when available
}

function leadingSide(
  away: SideProbSide,
  home: SideProbSide,
  isLive: boolean,
): "away" | "home" | null {
  if (isLive && away.score != null && home.score != null) {
    if (away.score === home.score) return null;
    return away.score > home.score ? "away" : "home";
  }
  if (away.prob != null && home.prob != null) {
    if (away.prob === home.prob) return null;
    return away.prob > home.prob ? "away" : "home";
  }
  return null;
}

function SideCell({
  side,
  isLeading,
  isTrailing,
}: {
  side: SideProbSide;
  isLeading: boolean;
  isTrailing: boolean;
}) {
  return (
    <span
      className={cn(
        "flex items-center gap-1",
        isLeading ? "text-up" : isTrailing ? "text-down" : "text-muted-foreground",
      )}
    >
      <span className="font-semibold">{side.label}</span>
      <Num>{side.prob != null ? `${(side.prob * 100).toFixed(1)}%` : "--"}</Num>
    </span>
  );
}

export function SideProb({
  away,
  home,
  isLive = false,
}: {
  away: SideProbSide;
  home: SideProbSide;
  isLive?: boolean;
}) {
  const leading = leadingSide(away, home, isLive);
  return (
    <div
      className="flex items-center gap-2 font-data text-[11px] tabular"
      data-testid="side-prob"
    >
      <SideCell side={away} isLeading={leading === "away"} isTrailing={leading === "home"} />
      <span className="text-faint">@</span>
      <SideCell side={home} isLeading={leading === "home"} isTrailing={leading === "away"} />
    </div>
  );
}
