/** One board row. Desktop grid driven by ColumnVis; mobile card unchanged. */
import type { CSSProperties } from "react";
import type { BoardRow } from "@/types/board";
import type { ColumnVis } from "@/components/board/columns";
import { rowGridClass } from "@/components/board/columns";
import { cn } from "@/lib/utils";
import { fmtTotal, localClock } from "@/lib/format";
import { StatusCell } from "@/components/board/StatusCell";
import { MatchupCell } from "@/components/board/MatchupCell";
import { ScoreCell } from "@/components/board/ScoreCell";
import { WinProbCell } from "@/components/board/WinProbCell";
import { OddsCell } from "@/components/board/OddsCell";
import { SourceBadge } from "@/components/board/SourceBadge";

const DEFAULT_COLUMNS: ColumnVis = { odds: true, total: true };

interface BoardRowItemProps {
  row: BoardRow;
  generatedAt: string | null;
  style?: CSSProperties;
  columns?: ColumnVis;
}

export function BoardRowItem({
  row,
  generatedAt,
  style,
  columns = DEFAULT_COLUMNS,
}: BoardRowItemProps) {
  const isLive = row.state === "in";
  const updatedLabel = localClock(generatedAt);

  const liveClasses = isLive
    ? "border-l-2 border-live bg-live/5"
    : "border-l-2 border-transparent";

  return (
    <div
      style={style}
      className={cn("border-b border-line transition-colors", liveClasses)}
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
          rowGridClass(columns)
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

        {/* 5: Odds -- conditional on columns.odds */}
        {columns.odds && (
          <div className="hidden lg:block">
            <OddsCell row={row} />
          </div>
        )}

        {/* 6: Total -- conditional on columns.total */}
        {columns.total && (
          <div className="hidden lg:block tabular-nums text-sm text-muted text-right">
            {fmtTotal(row.total)}
          </div>
        )}

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
