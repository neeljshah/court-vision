/** ScoreCell: renders away/home scores for mlb, soccer, and tennis in a compact centered cell. */
import type { BoardRow } from "@/types/board";
import { cn } from "@/lib/utils";
import { winnerSide } from "@/lib/format";

interface ScoreCellProps {
  row: BoardRow;
}

function isTennisScore(v: unknown): boolean {
  return typeof v === "string";
}

export function ScoreCell({ row }: ScoreCellProps) {
  const { away_score, home_score, sport, state } = row;

  const bothNull =
    (away_score === null || away_score === undefined) &&
    (home_score === null || home_score === undefined);

  if (bothNull) {
    return (
      <div
        className="tabular-nums text-center text-muted text-sm"
        aria-label="Score unavailable"
      >
        --
      </div>
    );
  }

  const winner = winnerSide(row);

  // Tennis: one or both scores are strings (set scores like "6 4 7")
  if (sport === "tennis" && (isTennisScore(away_score) || isTennisScore(home_score))) {
    const awayStr =
      away_score !== null && away_score !== undefined ? String(away_score) : "--";
    const homeStr =
      home_score !== null && home_score !== undefined ? String(home_score) : "--";

    const awayWon = winner === "away";
    const homeWon = winner === "home";

    const srLabel =
      state === "post"
        ? winner === "away"
          ? `Away wins ${awayStr} to ${homeStr}`
          : winner === "home"
          ? `Home wins ${homeStr} to ${awayStr}`
          : `Match tied or undecided, Away ${awayStr}, Home ${homeStr}`
        : `Away sets ${awayStr}, Home sets ${homeStr}`;

    return (
      <div
        className="tabular-nums text-center leading-tight"
        role="cell"
      >
        <span className="sr-only">{srLabel}</span>
        <div aria-hidden="true" className="flex flex-col items-center gap-0.5">
          {/* Away on top */}
          <span
            className={cn(
              "text-sm tracking-widest font-semibold",
              awayWon || (!winner && away_score !== null && away_score !== undefined)
                ? "font-bold text-txt"
                : "text-muted font-normal",
              awayWon && "font-bold text-txt"
            )}
          >
            {awayStr}
          </span>
          {/* Home below */}
          <span
            className={cn(
              "text-sm tracking-widest font-semibold",
              homeWon || (!winner && home_score !== null && home_score !== undefined)
                ? "font-bold text-txt"
                : "text-muted font-normal",
              homeWon && "font-bold text-txt"
            )}
          >
            {homeStr}
          </span>
        </div>
      </div>
    );
  }

  // MLB / Soccer: "away - home" inline
  const awayDisplay =
    away_score !== null && away_score !== undefined ? String(away_score) : "--";
  const homeDisplay =
    home_score !== null && home_score !== undefined ? String(home_score) : "--";

  const awayWon = winner === "away";
  const homeWon = winner === "home";

  const isPost = state === "post";

  const srLabel = isPost
    ? winner === "away"
      ? `Away wins ${awayDisplay} to ${homeDisplay}`
      : winner === "home"
      ? `Home wins ${homeDisplay} to ${awayDisplay}`
      : `Final: Away ${awayDisplay}, Home ${homeDisplay}`
    : `Away ${awayDisplay}, Home ${homeDisplay}`;

  return (
    <div
      className="tabular-nums text-center text-sm"
      role="cell"
    >
      <span className="sr-only">{srLabel}</span>
      <span aria-hidden="true" className="inline-flex items-baseline gap-1">
        <span
          className={cn(
            isPost && awayWon ? "font-bold text-txt" : "text-txt"
          )}
        >
          {awayDisplay}
        </span>
        <span className="text-muted px-0.5">-</span>
        <span
          className={cn(
            isPost && homeWon ? "font-bold text-txt" : "text-txt"
          )}
        >
          {homeDisplay}
        </span>
      </span>
    </div>
  );
}
