/** MatchupCell -- displays away @ home matchup with optional winner badge, note, and league chip. */
import { Check } from "lucide-react";
import type { BoardRow } from "@/types/board";
import { cn } from "@/lib/utils";
import { winnerSide } from "@/lib/format";

interface MatchupCellProps {
  row: BoardRow;
  showLeague?: boolean;
}

interface TeamNameProps {
  name: string;
  isWinner: boolean;
  isBold: boolean;
}

function TeamName({ name, isWinner, isBold }: TeamNameProps) {
  return (
    <span className="inline-flex items-center gap-0.5 min-w-0">
      <span
        title={name}
        className={cn(
          "truncate text-sm leading-tight text-txt",
          "max-w-[90px] sm:max-w-[130px] lg:max-w-[190px]",
          isBold && "font-semibold",
        )}
      >
        {name}
      </span>
      {isWinner && (
        <Check
          className="shrink-0 text-model"
          width={14}
          height={14}
          aria-label="winner"
        />
      )}
    </span>
  );
}

export function MatchupCell({ row, showLeague = false }: MatchupCellProps) {
  const winner = winnerSide(row);

  const awayWon = winner === "away";
  const homeWon = winner === "home";

  const hasNote = Boolean(row.note);
  const hasMeta = showLeague || hasNote;

  return (
    <div className="flex flex-col gap-0.5 min-w-0">
      {/* Team names row: min-w-0 ensures truncation works inside flex parents */}
      <div className="flex items-center min-w-0 gap-x-0.5">
        <TeamName name={row.away} isWinner={awayWon} isBold={false} />

        <span
          className="text-muted text-[11px] px-1 shrink-0 select-none"
          aria-hidden="true"
        >
          @
        </span>

        <TeamName name={row.home} isWinner={homeWon} isBold={true} />
      </div>

      {/* Meta row: league chip + note */}
      {hasMeta && (
        <div className="flex items-start gap-1.5 min-w-0 leading-snug">
          {showLeague && row.league && (
            <span className="text-[10px] text-muted uppercase tracking-wide shrink-0">
              {row.league}
            </span>
          )}
          {hasNote && (
            <span className="text-[11px] text-muted leading-snug line-clamp-2 min-w-0">
              {row.note}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
