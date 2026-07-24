// Risk (/risk) -- the honest UNIT-space RISK view.
//
// Answers ONE honest question: "what are we risking, descriptively, in UNITS?" --
// NEVER "how much money". Three surfaces: (1) a per-bet RISK card for every
// qualifying paper pick (units staked, tier, capped quarter-Kelly, model prob vs
// devigged close, or an honest no-bet-below-floor reason); (2) a PORTFOLIO RISK
// panel (total exposure in units, variance/SD, joint<naive-sum + correlation note,
// descriptive Risk-of-Ruin); (3) an EXPOSURE / LIMITS panel (tier-floor policy +
// per-sport / slate caps).
//
// HONESTY RAILS: UNITS / probability only -- NO $ field anywhere. Risk is
// DESCRIPTIVE, never prescriptive money advice; Risk-of-Ruin is a model-conditional
// stat, not a safety/profit guarantee. real money is default-DENY (paper only);
// edge_claimed is false; vs_close is UNPROVEN. An honest empty state when no pick
// qualifies -- matching the efficient close is a SUCCESS, never a fabricated bet.
// Local only.

import { BestBetsRisk } from "@/components/risk/BestBetsRisk";
import { PortfolioRiskPanel } from "@/components/risk/PortfolioRiskPanel";
import { ExposureLimitsPanel } from "@/components/risk/ExposureLimitsPanel";
import { Legend, InfoTip } from "@/components/depth";
import { RISK_TERMS } from "@/components/risk/riskTerms";
import { HONEST_DISCLAIMER } from "@/lib/api";

export const metadata = {
  title: "Risk",
};

export default function RiskPage() {
  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold tracking-tight">
          Risk{" "}
          <span className="font-mono text-sm text-muted-foreground">
            descriptive unit-space exposure -- not dollars
          </span>
        </h1>
        <span className="font-mono text-[11px] text-muted-foreground">
          reads the Auto-API -- paper only -- no $ claimed
        </span>
      </header>

      {/* Prominent honest banner: UNITS not dollars; descriptive; real money DENY. */}
      <section
        aria-label="risk honesty banner"
        className="flex flex-col gap-2 rounded-lg border border-amber-900/40 bg-amber-950/20 px-4 py-3 text-[12px] text-amber-200/90"
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono uppercase tracking-wide text-amber-400">units, not dollars</span>
          <span className="text-foreground">
            Everything here is <strong>descriptive unit-space risk</strong> -- there is{" "}
            <span className="font-mono">NO $</span> field anywhere. Risk-of-Ruin and variance are
            model-conditional <em>descriptive</em> stats, never a profit/safety guarantee and never
            money advice. Real money is{" "}
            <span className="font-mono uppercase text-amber-400">DENY</span> (paper only).
          </span>
          <InfoTip term="units" ariaLabel="what is a unit?" />
          <InfoTip text={RISK_TERMS.ror} ariaLabel="what is Risk-of-Ruin?" />
        </div>
        {/* Unit-convention note: per-bet stakes here are quarter-Kelly sized (can exceed
            1.0) and differ from the bets board's flat 1.0-per-bet display unit. */}
        <p
          data-testid="risk-unit-convention-note"
          className="text-[11px] text-amber-200/60"
        >
          Per-bet{" "}
          <span className="font-medium text-amber-200/80">units staked</span>{" "}
          reflect{" "}
          <span className="font-medium text-amber-200/80">
            Kelly-style (quarter-Kelly) sizing
          </span>{" "}
          and can exceed 1.0 -- distinct from the bets board&apos;s{" "}
          <span className="font-mono text-amber-200/80">flat 1.0-per-bet</span>{" "}
          display unit. All values are{" "}
          <span className="font-mono text-amber-200/80">UNITS</span>, never dollars.
        </p>
      </section>

      {/* Page-level key: the risk vocabulary a reader needs below. */}
      <Legend
        title="how to read this page"
        terms={["units", "tier", "probability", "devig"]}
        items={[
          { label: "Kelly", tip: RISK_TERMS.kelly },
          { label: "quarter-Kelly", tip: RISK_TERMS.quarter_kelly },
          { label: "RoR", tip: RISK_TERMS.ror },
          { label: "floor", tip: RISK_TERMS.floor },
          { label: "exposure", tip: RISK_TERMS.exposure },
          { label: "joint vs naive", tip: RISK_TERMS.joint },
        ]}
      />

      {/* (1) Per-bet risk cards across sports (honest empty when none qualify). */}
      <BestBetsRisk />

      {/* (2) Portfolio risk (joint<naive sum, RoR descriptive) | (3) exposure & limits. */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-6">
          <PortfolioRiskPanel sport="all" />
        </div>
        <div className="col-span-12 lg:col-span-6">
          <ExposureLimitsPanel />
        </div>
      </div>

      <footer className="mt-4 text-center text-[11px] text-muted-foreground">
        {HONEST_DISCLAIMER} Risk is DESCRIPTIVE, in UNITS only -- no $ field anywhere, no money
        advice. Risk-of-Ruin is a model-conditional stat, not a safety/profit guarantee. Real
        money is default-DENY (paper only); vs-close is UNPROVEN where no in-play odds exist.
      </footer>
    </main>
  );
}
