/** GameDetailDialog -- controlled detail view for one game row using the Dialog primitive. */
import type { BoardRow } from "@/types/board";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { WinProbCell } from "@/components/board/WinProbCell";
import { winnerSide, fmtTotal, localTime } from "@/lib/format";
import { cn } from "@/lib/utils";

interface GameDetailDialogProps {
  row: BoardRow | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Small section heading: uppercase, muted, tight. */
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted mb-1">
      {children}
    </p>
  );
}

/** Horizontal divider between sections. */
function Divider() {
  return <hr className="border-line my-3" />;
}

/** Status line: live dot for in-progress, clock text or scheduled time. */
function StatusSection({ row }: { row: BoardRow }) {
  const isLive = row.state === "in";
  const isPre = row.state === "pre";

  let statusText: string;
  if (isLive) {
    statusText = row.clock_text ?? "Live";
  } else if (row.state === "post") {
    statusText = "Final";
  } else {
    statusText = row.start_time ? localTime(row.start_time) : "Scheduled";
  }

  return (
    <div>
      <SectionLabel>Status</SectionLabel>
      <div className="flex items-center gap-2">
        {isLive && (
          <span
            aria-label="Live"
            className="inline-block h-2 w-2 rounded-full bg-live animate-pulse"
          />
        )}
        <span
          className={cn(
            "text-sm font-medium tabular-nums",
            isLive ? "text-live" : isPre ? "text-muted" : "text-txt"
          )}
        >
          {statusText}
        </span>
      </div>
    </div>
  );
}

/** Score block: away @ home with scores, bold the winner. */
function ScoreSection({ row }: { row: BoardRow }) {
  const winner = winnerSide(row);
  const hasScores = row.away_score !== null || row.home_score !== null;

  return (
    <div>
      <SectionLabel>Score</SectionLabel>
      <div className="flex items-center gap-3 text-sm tabular-nums">
        <span
          className={cn(
            "font-medium",
            winner === "away" ? "text-win font-bold" : "text-txt"
          )}
        >
          {row.away}
          {hasScores && (
            <span className="ml-1 text-base font-bold">
              {row.away_score ?? "--"}
            </span>
          )}
        </span>
        <span className="text-muted text-xs">@</span>
        <span
          className={cn(
            "font-medium",
            winner === "home" ? "text-win font-bold" : "text-txt"
          )}
        >
          {row.home}
          {hasScores && (
            <span className="ml-1 text-base font-bold">
              {row.home_score ?? "--"}
            </span>
          )}
        </span>
      </div>
    </div>
  );
}

/** Markets section: total and market line. */
function MarketsSection({ row }: { row: BoardRow }) {
  const hasTotal = row.total !== null;
  const hasMarket = !!row.market_odds;

  return (
    <div>
      <SectionLabel>Markets</SectionLabel>
      {hasTotal && (
        <p className="text-sm text-txt tabular-nums mb-0.5">
          Total: <span className="font-semibold">{fmtTotal(row.total)}</span>
        </p>
      )}
      {hasMarket && (
        <p className="text-sm text-txt tabular-nums mb-0.5">
          Market line:{" "}
          <span className="font-semibold">{row.market_odds}</span>
          {row.provider && (
            <span className="text-muted text-xs ml-1">({row.provider})</span>
          )}
        </p>
      )}
      {!hasTotal && !hasMarket && (
        <p className="text-sm text-muted">No market line available.</p>
      )}
    </div>
  );
}

/** Plain-language provenance sentence for source field. */
function sourceText(row: BoardRow): string {
  switch (row.source) {
    case "model":
      return "Our calibrated pregame win-prob (this matchup is in our data).";
    case "live-model":
      return "Our calibrated in-game win-prob, updating live.";
    case "market":
      return "Devigged market-implied probability (no in-corpus model).";
    case "live-market":
      return "Devigged market-implied probability, updating live.";
    case "unavailable":
      return row.market_odds
        ? "Raw market line shown; no model or devigged probability."
        : "No in-corpus model and no usable odds -> score and clock only.";
    default:
      return "";
  }
}

/** Source provenance block. */
function SourceSection({ row }: { row: BoardRow }) {
  return (
    <div>
      <SectionLabel>Source</SectionLabel>
      <p className="text-sm text-txt">{sourceText(row)}</p>
    </div>
  );
}

/** League + exact start time context. */
function ContextSection({ row }: { row: BoardRow }) {
  return (
    <div>
      <SectionLabel>Context</SectionLabel>
      <p className="text-sm text-txt">
        {row.league}
        {row.start_time && (
          <span className="text-muted"> &mdash; {localTime(row.start_time)}</span>
        )}
      </p>
    </div>
  );
}

export function GameDetailDialog({ row, open, onOpenChange }: GameDetailDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {row && (
        <DialogContent title={`${row.away} @ ${row.home}`}>
          <div className="flex flex-col">
            <StatusSection row={row} />
            <Divider />
            <ScoreSection row={row} />
            <Divider />

            {row.source !== "unavailable" && (
              <>
                <div>
                  <SectionLabel>Win Probability</SectionLabel>
                  <WinProbCell row={row} />
                </div>
                <Divider />
              </>
            )}

            <MarketsSection row={row} />
            <Divider />
            <SourceSection row={row} />
            <Divider />
            <ContextSection row={row} />

            {row.note && (
              <>
                <Divider />
                <div>
                  <SectionLabel>Note</SectionLabel>
                  <p className="text-sm text-txt whitespace-pre-wrap">{row.note}</p>
                </div>
              </>
            )}
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}
