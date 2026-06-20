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
import { HONEST_DISCLAIMER } from "@/lib/api";

export const metadata = {
  title: "Best Bets",
};

export default function BetsPage() {
  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold tracking-tight">
          Best Bets{" "}
          <span className="font-mono text-sm text-muted-foreground">
            calibrated divergence -- units only, no edge claimed
          </span>
        </h1>
        <span className="font-mono text-[11px] text-muted-foreground">
          paper only -- no $
        </span>
      </header>

      {/* Honest banner: calibration framing, no profit claim */}
      <section
        aria-label="bets honesty banner"
        className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-900/40 bg-amber-950/20 px-4 py-3 text-[12px] text-amber-200/90"
      >
        <span className="font-mono uppercase tracking-wide text-amber-400">
          units only -- no dollars
        </span>
        <span className="text-slate-300">
          Cards are ranked by <strong>calibrated model-vs-market divergence</strong> and
          confidence. This is{" "}
          <span className="font-mono">CALIBRATION</span>, not a profit or edge claim.
          A no-bet result (model matches the efficient close) is a{" "}
          <strong>calibration success</strong>. Real money is{" "}
          <span className="font-mono uppercase text-amber-400">DENY</span> (paper only).
          CLV may show{" "}
          <span className="font-mono">INSUFFICIENT_DATA</span> when no live in-play prices
          exist -- shown honestly, never fabricated.
        </span>
      </section>

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
