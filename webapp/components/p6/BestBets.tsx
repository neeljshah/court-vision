"use client";

import { useState } from "react";
import type { BestBet, GameEdge } from "@/lib/p5api";
import { Panel, Unavailable, Badge } from "./Primitives";
import { PaperBetDialog } from "./PaperBetDialog";
import { cn, fmtPct, tierClass } from "@/lib/utils";
import { Button } from "@/components/ui/button";

// BestBets -- renders best_bets in UNITS ONLY. There is deliberately NO dollar
// column anywhere. Below-floor candidates (decision='no_bet') are shown muted.
// Each "bet" row carries a "Place paper bet" action that POSTs to
// /api/paper/place (PAPER ONLY, executed always false; stake sized server-side
// in UNITS). On success the row reflects an open paper trade.
export function BestBets({
  game,
  sport,
}: {
  game: GameEdge | null;
  sport?: string;
}) {
  // A confirmed placement keyed by row signature so the open-trade reflection
  // survives across the 8s poll re-renders (parent passes a fresh GameEdge).
  const [placed, setPlaced] = useState<Record<string, true>>({});
  const [dialogBet, setDialogBet] = useState<BestBet | null>(null);

  if (!game || game.status === "unavailable") {
    return (
      <Panel title="Best bets (paper)">
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
      right={<Badge tone="slate">units only &middot; no $</Badge>}
    >
      {bets.length === 0 ? (
        <p className="text-sm text-slate-500">
          No candidate clears the tier floor right now.
        </p>
      ) : (
        <table className="w-full text-sm" role="table" aria-label="Best bet candidates">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wide text-slate-500">
              <th className="pb-2 font-medium">Market</th>
              <th className="pb-2 font-medium">Tier</th>
              <th className="pb-2 font-medium text-right">EV</th>
              <th className="pb-2 font-medium text-right">Stake (u)</th>
              <th className="pb-2 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {bets.map((b, i) => (
              <BetRow
                key={`${b.market_type}-${b.side}-${i}`}
                b={b}
                isPlaced={!!placed[betKey(b)]}
                onPlace={() => setDialogBet(b)}
              />
            ))}
          </tbody>
        </table>
      )}

      {noBets.length > 0 ? (
        <details className="mt-3 text-xs text-slate-500">
          <summary className="cursor-pointer select-none">
            {noBets.length} below-floor candidate(s) -- no bet
          </summary>
          <ul className="mt-2 space-y-1">
            {noBets.map((c, i) => (
              <li key={i} className="flex justify-between font-mono">
                <span>
                  {c.market_type} {c.side}
                </span>
                <span className="text-slate-600">
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

function BetRow({
  b,
  isPlaced,
  onPlace,
}: {
  b: BestBet;
  isPlaced: boolean;
  onPlace: () => void;
}) {
  const isBet = b.decision === "bet";
  return (
    <tr className="text-slate-200">
      <td className="py-2">
        <div className="font-medium">
          {b.market_type} <span className="text-slate-400">{b.side}</span>
        </div>
        <div className="font-mono text-[10px] text-slate-500">
          {b.best_book} @ {b.best_odds.toFixed(2)}
          {b.line != null ? ` | ${b.line}` : ""}
        </div>
      </td>
      <td className="py-2">
        <span
          className={cn(
            "inline-flex rounded border px-1.5 py-0.5 text-[10px] font-mono",
            tierClass(b.tier || undefined),
          )}
          aria-label={`Tier ${b.tier || "none"}`}
        >
          {b.tier || "--"}
        </span>
      </td>
      <td className="py-2 text-right font-mono tabular-nums">{fmtPct(b.ev)}</td>
      <td className="py-2 text-right font-mono tabular-nums">
        {b.stake_units.toFixed(2)}u
      </td>
      <td className="py-2 text-right">
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
      </td>
    </tr>
  );
}

