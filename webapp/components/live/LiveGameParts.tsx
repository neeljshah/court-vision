/**
 * LiveGameParts.tsx -- small presentational pieces shared by the /live game
 * row (LiveGamesView.tsx). Split out to keep LiveGamesView.tsx <=300 LOC.
 *
 * LiveChip: amber "in progress" chip (never success/green -- stale-never-green).
 * ModelMarketBar: paired thin horizontal bars (bg-s-model amber vs bg-s-market
 * blue) for a real priced candidate. Renders nothing when no market price
 * exists on the game edge -- never fabricates a market number.
 * BestBetLine: one-line "top best bet" summary off the same edgeProb.
 * Renders nothing when the game has no priced candidate.
 */

import { Num } from "@/components/ui/terminal";
import type { LiveGameEntry } from "@/app/(terminal)/live/liveSections";

export function LiveChip() {
  return (
    <span
      className="inline-flex items-center gap-1 border border-warning/60 px-1.5 py-px font-data text-[10px] font-bold uppercase tracking-wider text-stale"
      data-testid="live-chip"
      aria-label="live"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-warning animate-pulse" aria-hidden />
      LIVE
    </span>
  );
}

export function ModelMarketBar({ entry }: { entry: LiveGameEntry }) {
  const eb = entry.edgeProb;
  if (!eb) return null;
  const modelPct = Math.round(eb.modelProb * 100);
  const marketPct = Math.round(eb.marketProb * 100);
  return (
    <div className="flex w-full max-w-[220px] flex-col gap-0.5" data-testid="model-market-bar">
      <div className="flex items-center gap-1.5">
        <span className="w-11 shrink-0 font-data text-[10px] text-s-model">model</span>
        <div className="h-1.5 flex-1 bg-surface-2">
          <div className="h-full bg-s-model" style={{ width: `${modelPct}%` }} />
        </div>
        <Num className="w-9 shrink-0 text-[10px] text-s-model">{`${modelPct}%`}</Num>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="w-11 shrink-0 font-data text-[10px] text-s-market">market</span>
        <div className="h-1.5 flex-1 bg-surface-2">
          <div className="h-full bg-s-market" style={{ width: `${marketPct}%` }} />
        </div>
        <Num className="w-9 shrink-0 text-[10px] text-s-market">{`${marketPct}%`}</Num>
      </div>
    </div>
  );
}

/** One-line "top best bet" summary off the game's leading priced candidate. */
export function BestBetLine({ entry }: { entry: LiveGameEntry }) {
  const eb = entry.edgeProb;
  if (!eb) return null;
  return (
    <span className="font-data text-[11px] text-muted-foreground" data-testid="best-bet-line">
      top bet: {eb.marketType} {eb.side}
    </span>
  );
}
