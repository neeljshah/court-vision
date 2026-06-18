import { useState } from "react";
import { Check } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { postIntent, type BetRow, type GameBoard } from "@/lib/api";
import {
  fmtModelProb,
  fmtDec,
  fmtLine,
  fmtEvPct,
  evTone,
  hasPrice,
  verdictVariant,
} from "./betFormat";

const TONE: Record<string, string> = {
  pos: "text-[hsl(var(--success))]",
  neg: "text-destructive",
  neutral: "text-muted-foreground",
};

/** Per-row "Log to paper" -- non-binding intent record (paper only, no bet placed). */
function LogToPaper({ game, row }: { game: GameBoard; row: BetRow }) {
  const [logged, setLogged] = useState(false);
  const [busy, setBusy] = useState(false);
  function log() {
    setBusy(true);
    postIntent({
      sport: game.sport,
      matchup: `${game.home} vs ${game.away}`,
      model: row.model_prob !== null ? `${row.selection} P=${fmtModelProb(row.model_prob)}` : row.selection,
      market: row.line !== null ? `${row.group} ${fmtLine(row.line)}` : row.group,
      edge: row.ev_pct !== null ? row.ev_pct / 100 : null,
      verdict: row.verdict,
      side: row.selection,
      book: row.best_book,
      price: row.best_price,
    })
      .then(() => setLogged(true))
      .catch(() => setLogged(false))
      .finally(() => setBusy(false));
  }
  return (
    <Button
      variant={logged ? "secondary" : "outline"}
      size="sm"
      onClick={log}
      disabled={busy || logged}
      title="Log a non-binding 'I placed this' record (paper only -- no bet is placed)"
    >
      {logged ? <Check className="h-3.5 w-3.5" /> : null}
      {logged ? "Logged" : "Log to paper"}
    </Button>
  );
}

function priceCell(row: BetRow) {
  if (!hasPrice(row)) {
    return <span className="text-muted-foreground">model view only</span>;
  }
  return (
    <span>
      <span className="font-medium">{fmtDec(row.best_price)}</span>{" "}
      <span className="text-[11px] text-muted-foreground">{row.best_book}</span>
    </span>
  );
}

/** Dense, honest table of every bet row in a group. */
export function BetRowsTable({ game, rows }: { game: GameBoard; rows: BetRow[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Selection</TableHead>
          <TableHead className="text-right">Model</TableHead>
          <TableHead className="text-right">Fair</TableHead>
          <TableHead className="text-right">Best book@price</TableHead>
          <TableHead className="text-right">EV %</TableHead>
          <TableHead>Verdict</TableHead>
          <TableHead className="text-right">Action</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={7} className="py-6 text-center text-muted-foreground">
              No bets in this group.
            </TableCell>
          </TableRow>
        ) : (
          rows.map((row, i) => (
            <TableRow key={`${row.selection}-${i}`}>
              <TableCell className="font-medium">
                {row.selection}
                {row.line !== null ? (
                  <span className="ml-1 font-mono text-xs text-muted-foreground">
                    {fmtLine(row.line)}
                  </span>
                ) : null}
                {row.note ? (
                  <div className="text-[11px] text-muted-foreground">{row.note}</div>
                ) : null}
              </TableCell>
              <TableCell className="text-right font-mono text-xs">
                {fmtModelProb(row.model_prob)}
              </TableCell>
              <TableCell className="text-right font-mono text-xs">{fmtDec(row.fair_odds)}</TableCell>
              <TableCell className="text-right font-mono text-xs">{priceCell(row)}</TableCell>
              <TableCell
                className={cn("text-right font-mono text-xs", TONE[evTone(row.ev_pct)])}
                title={hasPrice(row) ? "vs best available price, not the close" : undefined}
              >
                {hasPrice(row) ? fmtEvPct(row.ev_pct) : <span className="text-muted-foreground">n/a</span>}
              </TableCell>
              <TableCell>
                <Badge variant={verdictVariant(row.verdict)}>{row.verdict}</Badge>
              </TableCell>
              <TableCell className="text-right">
                <LogToPaper game={game} row={row} />
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}
