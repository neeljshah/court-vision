/** WinProbCell -- renders home/away (and draw for soccer) win probabilities as
 * labeled mini-bar rows. Post-game: dims block and highlights the winner side.
 * Draw is never marked as a winner. Bars are aria-hidden; text carries the info.
 */
import type { BoardRow } from "@/types/board";
import { pct, winnerSide } from "@/lib/format";
import { cn } from "@/lib/utils";

interface WinProbCellProps {
  row: BoardRow;
}

interface BarRowProps {
  label: string;
  value: number | null;
  isWinner: boolean;
  isPost: boolean;
}

function BarRow({ label, value, isWinner, isPost }: BarRowProps) {
  const displayVal = value !== null ? `${pct(value)}%` : "--";
  const fillWidth = value !== null ? `${Math.round(value * 100)}%` : "0%";
  const hasValue = value !== null;

  return (
    <div className="flex flex-col gap-[2px]">
      <div className="flex items-center justify-between">
        <span
          className={cn(
            "text-[11px] leading-none",
            isWinner && isPost ? "text-win font-medium" : "text-muted"
          )}
        >
          {label}
        </span>
        <span
          className={cn(
            "text-[11px] leading-none font-semibold tabular-nums",
            isWinner && isPost ? "text-win" : "text-txt"
          )}
        >
          {displayVal}
        </span>
      </div>
      <div
        className="h-[4px] w-full rounded-full bg-line overflow-hidden"
        aria-hidden="true"
      >
        {hasValue && (
          <div
            className={cn(
              "h-full rounded-full transition-none",
              isWinner && isPost ? "bg-win" : "bg-accent"
            )}
            style={{ width: fillWidth }}
          />
        )}
      </div>
    </div>
  );
}

export function WinProbCell({ row }: WinProbCellProps) {
  const wh = row.win_home !== null ? row.win_home : null;
  const wa = row.win_away !== null ? row.win_away : null;
  const dr =
    row.sport === "soccer" && row.draw !== null ? row.draw : null;

  const allNull = wh === null && wa === null && dr === null;

  if (allNull) {
    return (
      <div
        role="group"
        aria-label="Win probability"
        className="text-[11px] text-muted tabular-nums"
      >
        --
      </div>
    );
  }

  const isPost = row.state === "post";
  const winner = isPost ? winnerSide(row) : null;

  return (
    <div
      role="group"
      aria-label="Win probability"
      className={cn(
        "flex flex-col gap-[6px] min-w-[80px]",
        isPost && "opacity-60"
      )}
    >
      <BarRow
        label="Home"
        value={wh}
        isWinner={winner === "home"}
        isPost={isPost}
      />
      <BarRow
        label="Away"
        value={wa}
        isWinner={winner === "away"}
        isPost={isPost}
      />
      {dr !== null && (
        <BarRow
          label="Draw"
          value={dr}
          isWinner={false}
          isPost={isPost}
        />
      )}
    </div>
  );
}
