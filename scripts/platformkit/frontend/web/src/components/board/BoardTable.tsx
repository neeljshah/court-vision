import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { fmtPct, fmtPrice, edgeTone } from "@/lib/format";
import { parseMatchup, type SlateRow } from "@/lib/api";
import type { GameRef } from "@/components/game/GameDetail";
import { VerdictBadge } from "./VerdictBadge";
import { RowActions } from "./RowActions";
import { useSortedRows, type SortKey } from "./useSort";

const TONE: Record<string, string> = {
  pos: "text-[hsl(var(--success))]",
  neg: "text-destructive",
  neutral: "text-muted-foreground",
};

function SortHeader({
  label,
  sortable,
  active,
  dir,
  onClick,
  className,
}: {
  label: string;
  sortable?: SortKey;
  active: boolean;
  dir: "asc" | "desc";
  onClick?: () => void;
  className?: string;
}) {
  if (!sortable) return <TableHead className={className}>{label}</TableHead>;
  const Icon = !active ? ArrowUpDown : dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead className={className}>
      <button
        onClick={onClick}
        className={cn(
          "inline-flex items-center gap-1 uppercase tracking-wide hover:text-foreground",
          active && "text-foreground"
        )}
      >
        {label}
        <Icon className="h-3 w-3" />
      </button>
    </TableHead>
  );
}

function bestBookCell(book: string | null, price: number | null) {
  if (!book) return <span className="text-muted-foreground">n/a</span>;
  return (
    <span>
      <span className="font-medium">{fmtPrice(price)}</span>{" "}
      <span className="text-xs text-muted-foreground">{book}</span>
    </span>
  );
}

/** Dense, sortable, filterable odds grid consuming the honest slate. */
export function BoardTable({
  sport,
  rows,
  minEdge,
  onOpenGame,
}: {
  sport: string;
  rows: SlateRow[];
  minEdge: number;
  onOpenGame?: (game: GameRef) => void;
}) {
  const { view, sortKey, sortDir, toggle } = useSortedRows(rows, minEdge);

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortHeader label="Matchup" sortable="matchup" active={sortKey === "matchup"} dir={sortDir} onClick={() => toggle("matchup")} />
          <TableHead>Model</TableHead>
          <TableHead>Market</TableHead>
          <TableHead className="text-right">Best home</TableHead>
          <TableHead className="text-right">Best away</TableHead>
          <SortHeader label="Arb %" sortable="arb_pct" active={sortKey === "arb_pct"} dir={sortDir} onClick={() => toggle("arb_pct")} className="text-right" />
          <SortHeader label="Edge*" sortable="edge" active={sortKey === "edge"} dir={sortDir} onClick={() => toggle("edge")} className="text-right" />
          <SortHeader label="Model EV" sortable="model_ev_best" active={sortKey === "model_ev_best"} dir={sortDir} onClick={() => toggle("model_ev_best")} className="text-right" />
          <TableHead>Verdict</TableHead>
          <TableHead className="text-right">Action</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {view.length === 0 ? (
          <TableRow>
            <TableCell colSpan={10} className="py-8 text-center text-muted-foreground">
              No matchups match the current filter.
            </TableCell>
          </TableRow>
        ) : (
          view.map((row: SlateRow, i) => {
            const parsed = parseMatchup(row.matchup);
            const clickable = !!onOpenGame && !!parsed;
            const openThis = () => {
              if (parsed && onOpenGame)
                onOpenGame({ sport, home: parsed.home, away: parsed.away });
            };
            return (
            <TableRow
              key={`${row.matchup}-${i}`}
              className={cn(clickable && "cursor-pointer hover:bg-accent/40")}
              onClick={clickable ? openThis : undefined}
            >
              <TableCell className="font-medium">
                {clickable ? (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      openThis();
                    }}
                    className="text-left hover:text-primary hover:underline"
                    title="Open full bet board for this game"
                  >
                    {row.matchup}
                  </button>
                ) : (
                  row.matchup
                )}
              </TableCell>
              <TableCell className="font-mono text-xs">
                {row.model ?? <span className="text-muted-foreground">{row.status}</span>}
              </TableCell>
              <TableCell className="text-xs">
                {row.market ?? <span className="text-muted-foreground">unavailable</span>}
              </TableCell>
              <TableCell className="text-right font-mono text-xs">
                {bestBookCell(row.best_home_book, row.best_home_price)}
              </TableCell>
              <TableCell className="text-right font-mono text-xs">
                {bestBookCell(row.best_away_book, row.best_away_price)}
              </TableCell>
              <TableCell className="text-right font-mono text-xs">
                {row.arb_pct !== null && row.arb_pct > 0 ? (
                  <span className="text-[hsl(var(--success))]">{fmtPct(row.arb_pct)}</span>
                ) : (
                  <span className="text-muted-foreground">n/a</span>
                )}
              </TableCell>
              <TableCell className={cn("text-right font-mono text-xs", TONE[edgeTone(row.edge)])}>
                {fmtPct(row.edge, true)}
              </TableCell>
              <TableCell className={cn("text-right font-mono text-xs", TONE[edgeTone(row.model_ev_best)])}>
                {fmtPct(row.model_ev_best, true)}
              </TableCell>
              <TableCell>
                <VerdictBadge verdict={row.verdict} />
              </TableCell>
              <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                <RowActions sport={sport} row={row} />
              </TableCell>
            </TableRow>
            );
          })
        )}
      </TableBody>
    </Table>
  );
}
