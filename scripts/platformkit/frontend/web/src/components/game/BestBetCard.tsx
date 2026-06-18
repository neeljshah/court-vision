import { useState } from "react";
import { Check } from "lucide-react";
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

function Stat({ label, value, className }: { label: string; value: React.ReactNode; className?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn("font-mono text-sm", className)}>{value}</div>
    </div>
  );
}

/** A prominent best-bet card. EV shown ONLY where a real price exists. */
export function BestBetCard({ game, row }: { game: GameBoard; row: BetRow }) {
  const [logged, setLogged] = useState(false);
  const [busy, setBusy] = useState(false);
  const priced = hasPrice(row);

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
    <div className="rounded-lg border border-border bg-background/60 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{row.group}</div>
          <div className="text-base font-semibold leading-tight">
            {row.selection}
            {row.line !== null ? (
              <span className="ml-1 font-mono text-sm text-muted-foreground">{fmtLine(row.line)}</span>
            ) : null}
          </div>
        </div>
        <Badge variant={verdictVariant(row.verdict)}>{row.verdict}</Badge>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Model" value={fmtModelProb(row.model_prob)} />
        <Stat label="Fair odds" value={fmtDec(row.fair_odds)} />
        <Stat
          label="Best book"
          value={priced ? `${fmtDec(row.best_price)} ${row.best_book}` : "--"}
        />
        <Stat
          label="EV"
          value={priced ? fmtEvPct(row.ev_pct) : "n/a"}
          className={priced ? TONE[evTone(row.ev_pct)] : "text-muted-foreground"}
        />
      </div>

      {priced ? (
        <div className="mt-2 text-[11px] text-muted-foreground">
          EV is vs the best available price, not the close.
        </div>
      ) : (
        <div className="mt-2 text-[11px] text-muted-foreground">
          No book line -- model view only. No EV is shown (we never fabricate a price).
        </div>
      )}
      {row.note ? <div className="mt-1 text-[11px] text-muted-foreground">{row.note}</div> : null}

      <div className="mt-3">
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
      </div>
    </div>
  );
}
