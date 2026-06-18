import { useState } from "react";
import { Check, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { bookSearchUrl, postIntent, type SlateRow } from "@/lib/api";

/** External "place on my book" link + a non-binding "I placed this" intent logger. */
export function RowActions({ sport, row }: { sport: string; row: SlateRow }) {
  const [logged, setLogged] = useState(false);
  const [busy, setBusy] = useState(false);

  function logIntent() {
    setBusy(true);
    postIntent({
      sport,
      matchup: row.matchup,
      model: row.model,
      market: row.market,
      edge: row.edge,
      verdict: row.verdict,
      book: row.best_home_book,
      price: row.best_home_price,
    })
      .then(() => setLogged(true))
      .catch(() => setLogged(false))
      .finally(() => setBusy(false));
  }

  return (
    <div className="flex items-center gap-1.5">
      <Button asChild variant="ghost" size="sm" className="text-primary">
        <a href={bookSearchUrl(sport, row.matchup)} target="_blank" rel="noopener noreferrer">
          Place on my book
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </Button>
      <Button
        variant={logged ? "secondary" : "outline"}
        size="sm"
        onClick={logIntent}
        disabled={busy || logged}
        title="Log a non-binding 'I placed this' record (paper only -- no bet is placed)"
      >
        {logged ? <Check className="h-3.5 w-3.5" /> : null}
        {logged ? "Logged" : "I placed this"}
      </Button>
    </div>
  );
}
