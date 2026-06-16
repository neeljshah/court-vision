/** WinProbCell -- home/away/draw win-prob bars. Post-game: winner highlighted.
 * Pre/live: unique highest-probability side emphasized (readability cue only).
 * Ties -> neither emphasized. Bars aria-hidden. data-favorite on favorite row.
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
  isFavorite?: boolean;
}

function BarRow({ label, value, isWinner, isPost, isFavorite }: BarRowProps) {
  const displayVal = value !== null ? `${pct(value)}%` : "--";
  const fillWidth = value !== null ? `${Math.round(value * 100)}%` : "0%";
  const hasValue = value !== null;

  const labelClass = cn(
    "text-[11px] leading-none",
    isWinner && isPost
      ? "text-win font-medium"
      : isFavorite && !isPost
      ? "font-semibold text-txt"
      : "text-muted"
  );
  const valueClass = cn(
    "text-[11px] leading-none tabular-nums",
    isWinner && isPost
      ? "text-win font-semibold"
      : isFavorite && !isPost
      ? "font-semibold text-txt"
      : "text-txt"
  );

  return (
    <div
      className="flex flex-col gap-[2px]"
      data-favorite={isFavorite ? "true" : undefined}
    >
      <div className="flex items-center justify-between">
        <span className={labelClass}>{label}</span>
        <span className={valueClass}>{displayVal}</span>
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
  const wh = row.win_home;
  const wa = row.win_away;
  const dr = row.sport === "soccer" ? row.draw : null;

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

  // Unique max-probability side pre/live (readability cue only); null on tie.
  let favoriteKey: "home" | "away" | "draw" | null = null;
  if (!isPost) {
    const candidates: Array<{ key: "home" | "away" | "draw"; v: number }> = [];
    if (wh !== null) candidates.push({ key: "home", v: wh });
    if (wa !== null) candidates.push({ key: "away", v: wa });
    if (dr !== null) candidates.push({ key: "draw", v: dr });
    if (candidates.length > 0) {
      const max = Math.max(...candidates.map((c) => c.v));
      const tops = candidates.filter((c) => c.v === max);
      if (tops.length === 1) favoriteKey = tops[0].key;
    }
  }

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
        isFavorite={favoriteKey === "home"}
      />
      <BarRow
        label="Away"
        value={wa}
        isWinner={winner === "away"}
        isPost={isPost}
        isFavorite={favoriteKey === "away"}
      />
      {dr !== null && (
        <BarRow
          label="Draw"
          value={dr}
          isWinner={false}
          isPost={isPost}
          isFavorite={favoriteKey === "draw"}
        />
      )}
    </div>
  );
}
