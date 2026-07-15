// Bets (/bets) -- the Best Bets card board: Live / Pregame / Done sections.
//
// Prop-focused calibrated divergence cards grouped by bet status. Each card shows:
//   confidence, model prob vs market prob, multi-book lines + best line,
//   edge-vs-market (calibrated divergence, NOT a profit claim), CLV, units, tier.
// Click-through to /bets/[sport]/[gameId] (W7 full detail view).
//
// HONESTY RAILS:
//   - UNITS only -- NO $ field anywhere on this page
//   - "Best bets" = ranked calibrated model-vs-market divergence + confidence + CLV,
//     NEVER a fabricated profit/edge claim; real money stays default-DENY
//   - In-game CLV may be INSUFFICIENT_DATA -> shown honestly, never greened
//   - Stale-never-green: freshness from envelope.generated_at
//   - Empty/offseason shows an honest unavailable state, never a fake card
//   - Paper mode only; local only

import { BestBetsBoard } from "@/components/bets/BestBetsBoard";
import { BetsMoneyHeadline } from "@/components/bets/BetsMoneyHeadline";
import { TodayPlacedBets } from "@/components/bets/TodayPlacedBets";
import { Panel } from "@/components/ui/terminal";
import { HONEST_DISCLAIMER } from "@/lib/api";

export const metadata = {
  title: "Best Bets",
};

export default function BetsPage() {
  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          Best Bets{" "}
          <span className="font-data text-sm text-muted-foreground">
            calibrated divergence -- units only, no edge claimed
          </span>
        </h1>
        <span className="font-data text-[11px] text-muted-foreground">
          paper only -- no $
        </span>
      </header>

      {/* Honest banner: calibration framing, no profit claim */}
      <Panel className="px-4 py-3 text-[12px] text-muted-foreground">
        <span className="microlabel mr-2">units only -- no dollars</span>
        <span>
          Cards are ranked by <strong className="text-foreground">calibrated model-vs-market divergence</strong> and
          confidence. This is{" "}
          <span className="font-data">CALIBRATION</span>, not a profit or edge claim.
          A no-bet result (model matches the efficient close) is a{" "}
          <strong className="text-foreground">calibration success</strong>. Real money is{" "}
          <span className="font-data uppercase text-foreground">DENY</span> (paper only).
          CLV may show{" "}
          <span className="font-data">INSUFFICIENT_DATA</span> when no live in-play prices
          exist -- shown honestly, never fabricated.
        </span>
      </Panel>

      {/* MONEY HEADLINE: paper equity curve -- frames the best bets below as the
          money-makers (how much you WOULD have made, units only). */}
      <BetsMoneyHeadline />

      {/* PLACED (staked) bets today -- distinct from the candidate board below. */}
      <TodayPlacedBets />

      {/* Divider note: candidate board = ALL divergence, not necessarily staked. */}
      <p className="mt-1 microlabel">
        candidate board -- all calibrated divergence (not necessarily staked)
      </p>

      {/* Main board: Live / Pregame / Done sections with bet cards */}
      <BestBetsBoard />

      <footer className="mt-4 text-center text-[11px] text-muted-foreground">
        {HONEST_DISCLAIMER} Best bets = ranked calibrated divergence + confidence + CLV,
        never a fabricated profit claim. Units only -- no $ anywhere. Real money is
        default-DENY. CLV is INSUFFICIENT_DATA without in-play closing prices.
      </footer>
    </main>
  );
}
