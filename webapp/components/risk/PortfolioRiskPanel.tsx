"use client";

// PortfolioRiskPanel.tsx -- the descriptive UNIT-space PORTFOLIO risk view.
//
// Reads /api/quant/risk (via lib/api getRisk) over the OPEN paper book and shows:
// total exposure (naive sum of staked UNITS), max single leg, mean leg, variance
// (UNITS^2) and its square root (portfolio SD, a legitimate display transform of a
// returned value), plus the descriptive Risk-of-Ruin framing and the
// joint<naive-sum / correlation note. There is NO $ field; bankroll is in UNITS;
// RoR is a model-conditional DESCRIPTIVE stat, never a safety/profit guarantee.
// real_money_enabled is always false. An empty book renders an honest empty state.
//
// UNIT-CONVENTION NOTE (QA #3 / iter10-P2):
//   The bets board always displays stake_units = 1.0 (flat policy, one unit per bet).
//   This panel displays stake_units and total_exposure_units reflecting KELLY-STYLE
//   (quarter-Kelly) sizing, so values here can legitimately exceed 1.0. Both
//   conventions are UNITS, never currency. See the inline InfoTip + banner below.

import { useEffect, useState } from "react";
import { getRisk, type RiskView, type Sport } from "@/lib/api";
import { Panel, Unavailable, Badge } from "@/components/p6/Primitives";
import { InfoTip } from "@/components/depth";
import { RISK_TERMS } from "./riskTerms";

function units(x: number | null | undefined): string {
  return typeof x === "number" && Number.isFinite(x) ? `${x.toFixed(3)}u` : "--";
}

function Metric({
  label,
  value,
  term,
  sub,
}: {
  label: string;
  value: string;
  term?: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-bg-panel/40 p-3">
      <div className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
        {term ? <InfoTip text={RISK_TERMS[term]} ariaLabel={`what is ${label}?`} /> : null}
      </div>
      <div className="mt-1 font-mono tabular-nums text-lg text-foreground">{value}</div>
      {sub ? <div className="mt-0.5 text-[10px] text-faint">{sub}</div> : null}
    </div>
  );
}

export function PortfolioRiskPanel({ sport = "all" }: { sport?: Sport | "all" }) {
  const [risk, setRisk] = useState<RiskView | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    getRisk(sport, ac.signal).then((r) => setRisk(r));
    return () => ac.abort();
  }, [sport]);

  const ok = risk && risk.status !== "unavailable";
  const nOpen = risk?.n_open ?? 0;
  const variance = risk?.variance_units2 ?? 0;
  const sd = variance > 0 ? Math.sqrt(variance) : 0;

  return (
    <Panel
      title="portfolio risk (open paper book -- units only)"
      right={
        <span className="inline-flex items-center gap-1.5">
          <Badge tone="slate">{nOpen} open</Badge>
          <InfoTip
            text="Descriptive unit-space risk over the open paper book. Joint (correlation-adjusted) exposure is always <= the naive sum of stakes; Risk-of-Ruin is a model-conditional descriptive stat, never a safety/profit guarantee. NO money field anywhere."
            ariaLabel="what is portfolio risk?"
          />
        </span>
      }
    >
      {!risk ? (
        <p className="text-sm text-muted-foreground">loading...</p>
      ) : !ok ? (
        <Unavailable reason={risk.reason || "risk endpoint unavailable"} />
      ) : nOpen === 0 ? (
        <Unavailable reason="No open paper legs -- nothing is at risk. Exposure, variance, and Risk-of-Ruin are all zero by construction (never a fabricated number)." />
      ) : (
        <>
          {/* Unit-convention clarifier (QA #3 / iter10-P2): stake_units here are
              Kelly-style (quarter-Kelly) and can exceed 1.0 -- distinct from the
              bets board's flat 1.0-per-bet display convention. Both are UNITS, never currency. */}
          <div
            data-testid="unit-convention-note"
            className="mb-3 flex flex-wrap items-start gap-1.5 rounded-lg border border-slate-700/60 bg-slate-900/40 px-3 py-2 text-[11px] text-slate-400"
          >
            <span className="font-mono uppercase tracking-wide text-muted-foreground">unit convention</span>
            <span>
              Stake and exposure figures here use{" "}
              <span className="text-foreground font-medium">Kelly-style (quarter-Kelly) sizing</span>{" "}
              and can exceed 1.0 per bet. The bets board uses a separate{" "}
              <span className="text-foreground font-medium">flat 1.0-per-bet</span>{" "}
              display convention. Both are{" "}
              <span className="font-mono text-foreground">UNITS</span>, never currency.
            </span>
            <InfoTip
              text="The bets board always shows stake_units = 1.0 (flat policy per bet). This risk panel shows Kelly-style (quarter-Kelly) stake_units and total_exposure_units, which reflect model-sized fractions and can exceed 1.0 when multiple legs are open. Both are UNITS -- no currency figure anywhere."
              ariaLabel="what is the unit convention difference?"
            />
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric
              label="total exposure"
              value={units(risk.total_exposure_units)}
              term="exposure"
              sub="naive sum of stakes"
            />
            <Metric
              label="max single leg"
              value={units(risk.max_single_units)}
              sub="largest one-leg stake"
            />
            <Metric
              label="mean leg"
              value={units(risk.mean_units)}
              sub="avg stake per open leg"
            />
            <Metric
              label="portfolio SD"
              value={units(sd)}
              term="variance"
              sub={`var ${variance.toFixed(4)}u2`}
            />
          </div>

          {/* Joint < naive sum + correlation note (principle, not a fabricated number). */}
          <div className="mt-3 flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-800 bg-bg-panel/30 px-3 py-2 text-[11px] text-muted-foreground">
            <span className="font-mono uppercase tracking-wide text-faint">joint &lt; naive sum</span>
            <span>
              correlation-adjusted joint exposure is always{" "}
              <span className="font-mono text-foreground">&le;</span> the naive sum above:
              same-game legs are correlated (no diversification); cross-game legs combine in
              quadrature (they diversify).
            </span>
            <InfoTip term="joint" text={RISK_TERMS.joint} ariaLabel="what is joint exposure?" />
            <InfoTip term="correlation" text={RISK_TERMS.correlation} ariaLabel="what is the correlation note?" />
          </div>

          {/* Risk-of-Ruin -- DESCRIPTIVE, never a guarantee. */}
          <div className="mt-2 flex flex-wrap items-center gap-1.5 rounded-lg border border-amber-900/40 bg-amber-950/10 px-3 py-2 text-[11px] text-amber-300/90">
            <span className="font-mono uppercase tracking-wide text-amber-500/80">risk-of-ruin</span>
            <span className="text-muted-foreground">
              {risk.risk_note ||
                "a model-conditional descriptive stat under the model's own probabilities -- NOT a profit/safety guarantee; there is no realized-money path."}
            </span>
            <InfoTip term="ror" text={RISK_TERMS.ror} ariaLabel="what is Risk-of-Ruin?" />
          </div>

          <div className="mt-2 flex items-center justify-between font-mono text-[9px] uppercase tracking-wide text-faint">
            <span className="inline-flex items-center gap-1">
              bankroll in units
              <InfoTip term="bankroll_units" text={RISK_TERMS.bankroll_units} ariaLabel="what is the bankroll unit?" />
            </span>
            <span>real money: DENY (paper only)</span>
          </div>
        </>
      )}
    </Panel>
  );
}
