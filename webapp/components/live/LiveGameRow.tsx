/**
 * LiveGameRow.tsx -- the clickable /live game card. Split out of
 * LiveGamesView.tsx to keep that file <=300 LOC.
 *
 * Whole row is a <Link> to the game detail route (/games/[sport]/[gameId] --
 * has best bets + in-game number). Matchup names are humanized (never a raw
 * KX ticker). SideProb gives winner clarity (leading side green, trailing
 * red). ModelMarketBar + BestBetLine surface the leading priced candidate.
 */

import Link from "next/link";
import { cn } from "@/lib/utils";
import { LiveChip, ModelMarketBar, BestBetLine } from "@/components/live/LiveGameParts";
import { SideProb } from "@/components/live/SideProb";
import { humanizeMatchup } from "@/lib/betdesc";
import type { LiveGameEntry, LiveState } from "@/app/live/liveSections";

export function gameStateLabel(liveState: LiveState | null): string {
  if (!liveState) return "";
  if (liveState.detail) return liveState.detail;
  if (liveState.status && liveState.status !== "live") return liveState.status;
  const parts: string[] = [];
  if (liveState.period != null) parts.push(`Q${liveState.period}`);
  if (liveState.clock) parts.push(liveState.clock);
  return parts.join(" ");
}

export function LiveGameRow({ entry }: { entry: LiveGameEntry }) {
  const isLive = entry.section === "LIVE";
  const isDone = entry.section === "DONE";
  const stateLabel = gameStateLabel(entry.liveState);
  const ls = entry.liveState;
  const fs = entry.finalScore;
  const mc = entry.modelCall;
  const awayLabel = humanizeMatchup(entry.away);
  const homeLabel = humanizeMatchup(entry.home);
  const awayProb = entry.homeWinProb != null ? 1 - entry.homeWinProb : null;
  const linkAriaLabel = `${awayLabel} at ${homeLabel}${entry.tipoff ? `, ${entry.tipoff}` : ""} -- open game detail`;

  return (
    <li className="border-b border-border last:border-b-0" data-testid="live-game-row">
      <Link
        href={`/games/${entry.sport}/${entry.game_id}?m=${encodeURIComponent(`${awayLabel} @ ${homeLabel}`)}`}
        aria-label={linkAriaLabel}
        className={cn(
          "flex cursor-pointer flex-col gap-1.5 px-3 py-2 transition-colors hover:bg-surface-2",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background",
        )}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-semibold text-foreground">
            {awayLabel}<span className="mx-1.5 font-normal text-faint">@</span>{homeLabel}
          </span>
          <span className="flex items-center gap-2">
            {isLive && <LiveChip />}
            {isDone && fs ? (
              <span className="font-data text-xs font-semibold tabular text-muted-foreground" data-testid="final-score">
                {awayLabel} {fs.away_score} - {fs.home_score} {homeLabel}
                <span className="ml-1.5 text-[10px] font-normal text-faint">{fs.label}</span>
              </span>
            ) : null}
            {!isLive && !isDone && entry.tipoff ? (
              <span className="font-data text-[10px] text-faint">{entry.tipoff}</span>
            ) : null}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-data text-[11px] text-faint">
            {entry.sport.toUpperCase()}
          </span>
          {!isDone ? (
            <SideProb
              isLive={isLive}
              away={{ label: awayLabel, prob: awayProb, score: ls?.away_score ?? null }}
              home={{ label: homeLabel, prob: entry.homeWinProb, score: ls?.home_score ?? null }}
            />
          ) : null}
          {entry.edgeProb ? <ModelMarketBar entry={entry} /> : null}
          {entry.edgeProb ? <BestBetLine entry={entry} /> : null}
          {isDone && mc ? (
            <span
              className={cn(
                "font-data text-[11px]",
                mc.correct === true
                  ? "text-up"
                  : mc.correct === false
                    ? "text-down"
                    : "text-faint",
              )}
              data-testid="model-call"
            >
              model: {mc.favoured} {mc.prob != null ? `(${(mc.prob * 100).toFixed(0)}%)` : ""}
              {mc.correct === true ? " -- correct" : mc.correct === false ? " -- wrong" : ""}
            </span>
          ) : null}
          {isLive && stateLabel ? <span className="font-data text-[11px] text-faint">{stateLabel}</span> : null}
          {isLive && ls?.home_score != null && ls?.away_score != null ? (
            <span className="font-data tabular text-[11px] font-semibold text-foreground">
              {ls.away_score} - {ls.home_score}
            </span>
          ) : null}
        </div>
      </Link>
    </li>
  );
}
