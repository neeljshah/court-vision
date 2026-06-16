/** One board row. Renders a responsive grid on desktop (md+) and a stacked card on mobile. */
import type { CSSProperties } from "react";
import type { BoardRow } from "@/types/board";
import { cn } from "@/lib/utils";
import { fmtTotal, localClock } from "@/lib/format";
import { StatusCell } from "@/components/board/StatusCell";
import { MatchupCell } from "@/components/board/MatchupCell";
import { ScoreCell } from "@/components/board/ScoreCell";
import { WinProbCell } from "@/components/board/WinProbCell";
import { OddsCell } from "@/components/board/OddsCell";
import { SourceBadge } from "@/components/board/SourceBadge";

interface BoardRowItemProps {
  row: BoardRow;
  generatedAt: string | null;
  style?: CSSProperties;
}

export function BoardRowItem({ row, generatedAt, style }: BoardRowItemProps) {
  const isLive = row.state === "in";
  const updatedLabel = localClock(generatedAt);

  const liveClasses = isLive
    ? "border-l-2 border-live bg-live/5"
    : "border-l-2 border-transparent";

  // Shared outer wrapper
  return (
    <div
      style={style}
      className={cn(
        "border-b border-line transition-colors",
        liveClasses
      )}
    >
      {/* ---- MOBILE: stacked card (hidden at md+) ---- */}
      <div className="md:hidden px-3 py-2.5 space-y-1.5">
        {/* Top line: status + source badge */}
        <div className="flex items-center justify-between gap-2 min-w-0">
          <div className="min-w-0 truncate">
            <StatusCell row={row} />
          </div>
          <div className="shrink-0">
            <SourceBadge row={row} />
          </div>
        </div>

        {/* Matchup */}
        <MatchupCell row={row} />

        {/* Score + WinProb side by side */}
        <div className="flex items-center gap-3">
          <ScoreCell row={row} />
          <WinProbCell row={row} />
        </div>
      </div>

      {/* ---- DESKTOP: grid row (hidden below md) ---- */}
      <div
        className={cn(
          "hidden md:grid items-center gap-2 px-3 py-2.5",
          "md:grid-cols-[110px_minmax(180px,1fr)_90px_150px_110px_70px_110px_90px]"
        )}
      >
        {/* 1: Status */}
        <StatusCell row={row} />

        {/* 2: Matchup */}
        <MatchupCell row={row} />

        {/* 3: Score */}
        <ScoreCell row={row} />

        {/* 4: WinProb */}
        <WinProbCell row={row} />

        {/* 5: Odds -- hidden below lg */}
        <div className="hidden lg:block">
          <OddsCell row={row} />
        </div>

        {/* 6: Total -- hidden below lg */}
        <div className="hidden lg:block tabular-nums text-sm text-muted text-right">
          {fmtTotal(row.total)}
        </div>

        {/* 7: Source */}
        <SourceBadge row={row} />

        {/* 8: Updated -- hidden below lg */}
        <div
          className="hidden lg:block tabular-nums text-xs text-muted text-right truncate"
          aria-label={`Last updated ${updatedLabel}`}
        >
          {updatedLabel}
        </div>
      </div>
    </div>
  );
}
