/** MatchupCell -- displays away @ home matchup with optional winner badge, note, and league chip.
 *  When onSelect is provided, wraps the team-names row in an accessible button. */
import { Check } from "lucide-react";
import type { BoardRow } from "@/types/board";
import { cn } from "@/lib/utils";
import { winnerSide } from "@/lib/format";

interface MatchupCellProps {
  row: BoardRow;
  showLeague?: boolean;
  onSelect?: () => void;
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

/** Inner team-names row -- rendered as-is or wrapped in a button depending on onSelect. */
function NamesRow({
  row,
  awayWon,
  homeWon,
  onSelect,
}: {
  row: BoardRow;
  awayWon: boolean;
  homeWon: boolean;
  onSelect?: () => void;
}) {
  const inner = (
    <>
      <TeamName name={row.away} isWinner={awayWon} isBold={false} />
      <span
        className="text-muted text-[11px] px-1 shrink-0 select-none"
        aria-hidden="true"
      >
        @
      </span>
      <TeamName name={row.home} isWinner={homeWon} isBold={true} />
    </>
  );

  if (onSelect) {
    return (
      <button
        type="button"
        onClick={onSelect}
        aria-label={`View details: ${row.away} at ${row.home}`}
        className={cn(
          "flex items-center min-w-0 gap-x-0.5",
          "text-left hover:underline underline-offset-2 rounded",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        )}
      >
        {inner}
      </button>
    );
  }

  return (
    <div className="flex items-center min-w-0 gap-x-0.5">{inner}</div>
  );
}

export function MatchupCell({ row, showLeague = false, onSelect }: MatchupCellProps) {
  const winner = winnerSide(row);

  const awayWon = winner === "away";
  const homeWon = winner === "home";

  const hasNote = Boolean(row.note);
  const hasMeta = showLeague || hasNote;

  return (
    <div className="flex flex-col gap-0.5 min-w-0">
      <NamesRow row={row} awayWon={awayWon} homeWon={homeWon} onSelect={onSelect} />

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
