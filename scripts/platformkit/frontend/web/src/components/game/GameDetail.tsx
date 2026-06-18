import { useEffect, useState } from "react";
import { Activity, Radio } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { CollapsibleSection } from "@/components/ui/collapsible";
import { getGame, type GameBoard, type GameLiveParams } from "@/lib/api";
import { BestBetCard } from "./BestBetCard";
import { BetRowsTable } from "./BetRowsTable";

export interface GameRef {
  sport: string;
  home: string;
  away: string;
  live?: GameLiveParams;
}

/**
 * Rich game detail view: the FULL ranked bet board for one game.
 * Opens as a modal dialog when a game row is clicked. Codes to GET /api/game.
 */
export function GameDetail({
  game,
  open,
  onOpenChange,
}: {
  game: GameRef | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [board, setBoard] = useState<GameBoard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !game) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setBoard(null);
    getGame(game.sport, game.home, game.away, game.live)
      .then((b) => {
        if (!cancelled) setBoard(b);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, game]);

  const title = game ? `${game.home} vs ${game.away}` : "Game";
  const live = board?.live ?? null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <div className="flex items-center gap-2 pr-8">
            <Activity className="h-4 w-4 text-primary" />
            <DialogTitle>{title}</DialogTitle>
            {board ? (
              <Badge variant="muted" className="uppercase">
                {board.sport}
              </Badge>
            ) : null}
            {live ? (
              <Badge variant="warning" className="gap-1">
                <Radio className="h-3 w-3" /> LIVE
              </Badge>
            ) : null}
          </div>
          {live ? (
            <DialogDescription className="font-mono">
              {board?.home} {live.home_score} - {live.away_score} {board?.away} · {live.state}
              {live.clock ? ` · ${live.clock}` : ""}
            </DialogDescription>
          ) : board ? (
            <DialogDescription>
              {board.status === "ok"
                ? `As of ${board.as_of}`
                : `Status: ${board.status}`}
            </DialogDescription>
          ) : null}
        </DialogHeader>

        <div className="overflow-y-auto px-6 py-4">
          {board?.honest_note ? (
            <div className="mb-4 rounded-md border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              {board.honest_note}
            </div>
          ) : null}

          {loading ? (
            <div className="py-10 text-center text-muted-foreground">Loading bet board...</div>
          ) : error ? (
            <div className="py-10 text-center text-destructive">
              Could not load this game: {error}
              <p className="mt-2 text-xs text-muted-foreground">
                The /api/game endpoint may not be wired yet. No numbers are fabricated.
              </p>
            </div>
          ) : !board ? (
            <div className="py-10 text-center text-muted-foreground">No data.</div>
          ) : board.status !== "ok" ? (
            <div className="py-10 text-center text-muted-foreground">
              This game is {board.status} -- the predictor returned no priced board (no fabricated
              numbers).
            </div>
          ) : (
            <div className="space-y-5">
              {board.best_bets.length > 0 ? (
                <section>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Best bets
                  </h3>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {board.best_bets.map((row, i) => (
                      <BestBetCard key={`best-${i}`} game={board} row={row} />
                    ))}
                  </div>
                </section>
              ) : (
                <section className="rounded-md border border-border/60 px-3 py-3 text-xs text-muted-foreground">
                  No standout best bets on this game -- the model does not diverge enough from the
                  available prices to flag one.
                </section>
              )}

              <section className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  All markets
                </h3>
                {board.groups.length === 0 ? (
                  <div className="rounded-md border border-border/60 px-3 py-3 text-xs text-muted-foreground">
                    No market groups returned for this game.
                  </div>
                ) : (
                  board.groups.map((g, i) => (
                    <CollapsibleSection
                      key={`${g.name}-${i}`}
                      defaultOpen={i === 0}
                      title={g.name}
                      badge={
                        <Badge variant="muted" className="ml-1">
                          {g.bets.length}
                        </Badge>
                      }
                    >
                      <BetRowsTable game={board} rows={g.bets} />
                    </CollapsibleSection>
                  ))
                )}
              </section>
            </div>
          )}
        </div>

        <div className="border-t border-border/60 px-6 py-2 text-[11px] text-muted-foreground">
          Decision-support only. No bet is placed and there is no sportsbook connection -- you
          execute manually. EV is shown only where a real price exists, and is vs the best available
          price (not the close). No money edge is claimed.
        </div>
      </DialogContent>
    </Dialog>
  );
}
