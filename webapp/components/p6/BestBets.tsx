"use client";

import { useState } from "react";
import type { BestBet, GameEdge } from "@/lib/p5api";
import { Panel, Unavailable, Badge } from "./Primitives";
import { PaperBetDialog } from "./PaperBetDialog";
import { cn, fmtPct, tierClass } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Num } from "@/components/ui/terminal";
import { describeBet } from "@/lib/betdesc";

// BestBets -- renders best_bets in UNITS ONLY. There is deliberately NO dollar
// column anywhere. Below-floor candidates (decision='no_bet') are shown muted.
// Each "bet" row carries a "Place paper bet" action that POSTs to
// /api/paper/place (PAPER ONLY, executed always false; stake sized server-side
// in UNITS). On success the row reflects an open paper trade.
//
// This is the STAR panel on the game-detail page (rendered directly under the
// header by GameView) -- every row shows the honest bet description
// (describeBet), a model-vs-market paired bar (amber vs blue), and the tier.
export function BestBets({
  game,
  sport,
  asOf,
  stale,
}: {
  game: GameEdge | null;
  sport?: string;
  asOf?: string | null;
  stale?: boolean;
}) {
  // A confirmed placement keyed by row signature so the open-trade reflection
  // survives across the 8s poll re-renders (parent passes a fresh GameEdge).
  const [placed, setPlaced] = useState<Record<string, true>>({});
  const [dialogBet, setDialogBet] = useState<BestBet | null>(null);

  if (!game || game.status === "unavailable") {
    return (
      <Panel title="Best bets (paper)" asOf={asOf} stale={stale}>
        <Unavailable reason={game?.reason || "no edge view for this game"} />
      </Panel>
    );
  }
  const gameId = game.game_id;
  const bets = game.best_bets || [];
  const noBets = (game.candidates || []).filter((c) => c.decision === "no_bet");

  const markPlaced = (b: BestBet) => {
    setPlaced((prev) => ({ ...prev, [betKey(b)]: true }));
  };

  return (
    <Panel
      title="Best bets (paper)"
      asOf={asOf}
      stale={stale}
      right={<Badge tone="slate">units only &middot; no $</Badge>}
    >
      {bets.length === 0 ? (
        <p className="text-sm text-faint">
          No candidate clears the tier floor right now.
        </p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Best bet candidates">
          {bets.map((b, i) => (
            <BetCard
              key={`${b.market_type}-${b.side}-${i}`}
              b={b}
              matchup={game.home && game.away ? `${game.away} @ ${game.home}` : null}
              isPlaced={!!placed[betKey(b)]}
              onPlace={() => setDialogBet(b)}
            />
          ))}
        </ul>
      )}

      {noBets.length > 0 ? (
        <details className="mt-3 text-xs text-faint">
          <summary className="cursor-pointer select-none">
            {noBets.length} below-floor candidate(s) -- no bet
          </summary>
          <ul className="mt-2 space-y-1">
            {noBets.map((c, i) => (
              <li key={i} className="flex justify-between font-data">
                <span>
                  {c.market_type} {c.side}
                </span>
                <span className="text-faint">
                  EV {fmtPct(c.ev)} &middot; {c.reason || "below floor"}
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <PaperBetDialog
        bet={dialogBet}
        sport={sport}
        gameId={gameId}
        onClose={() => setDialogBet(null)}
        onPlaced={(b) => {
          markPlaced(b);
          setDialogBet(null);
        }}
      />
    </Panel>
  );
}

function betKey(b: BestBet): string {
  return `${b.market_type}|${b.side}|${b.best_book}`;
}

// Thin paired model(amber)/market(blue) probability bar per DESIGN.md rule 4/7.
function ModelMarketBar({ modelProb, marketProb }: { modelProb: number; marketProb: number }) {
  const m = Math.round(Math.max(0, Math.min(1, modelProb)) * 100);
  const k = Math.round(Math.max(0, Math.min(1, marketProb)) * 100);
  return (
    <div className="flex flex-col gap-0.5" aria-hidden>
      <div className="flex h-1.5 overflow-hidden bg-surface-2">
        <div className="h-full bg-s-model" style={{ width: `${m}%` }} />
        <div className="h-full bg-surface-3" style={{ width: `${100 - m}%` }} />
      </div>
      <div className="flex h-1.5 overflow-hidden bg-surface-2">
        <div className="h-full bg-s-market" style={{ width: `${k}%` }} />
        <div className="h-full bg-surface-3" style={{ width: `${100 - k}%` }} />
      </div>
    </div>
  );
}

function BetCard({
  b,
  matchup,
  isPlaced,
  onPlace,
}: {
  b: BestBet;
  matchup: string | null;
  isPlaced: boolean;
  onPlace: () => void;
}) {
  const isBet = b.decision === "bet";
  return (
    <li
      className={cn(
        "flex flex-col gap-2 border border-border px-3 py-2.5",
        isBet ? "bg-surface-1" : "bg-surface-2 opacity-80",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-medium leading-snug">
            {describeBet({ ...b, matchup })}
          </div>
          <div className="mt-0.5 font-data text-[10px] text-faint">
            {b.best_book} @ {b.best_odds.toFixed(2)}
          </div>
        </div>
        <span
          className={cn(
            "shrink-0 border px-1.5 py-0.5 text-[10px] font-data",
            tierClass(b.tier || undefined),
          )}
          aria-label={`Tier ${b.tier || "none"}`}
        >
          {b.tier || "--"}
        </span>
      </div>

      <ModelMarketBar modelProb={b.model_prob} marketProb={b.market_prob} />
      <div className="flex justify-between font-data text-[10px] tabular text-faint">
        <span>
          <span className="text-s-model">model {fmtPct(b.model_prob, false)}</span>
          {" / "}
          <span className="text-s-market">market {fmtPct(b.market_prob, false)}</span>
        </span>
        <span>
          EV <Num>{fmtPct(b.ev)}</Num> &middot; <Num>{b.stake_units.toFixed(2)}u</Num>
        </span>
      </div>

      <div className="flex justify-end">
        {isPlaced ? (
          <Badge tone="green">open paper</Badge>
        ) : isBet ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={onPlace}
          >
            Place paper bet
          </Button>
        ) : (
          <Badge tone="slate">{b.decision}</Badge>
        )}
      </div>
    </li>
  );
}
