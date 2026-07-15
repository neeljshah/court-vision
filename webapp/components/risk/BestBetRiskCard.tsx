"use client";

// BestBetRiskCard.tsx -- one per-bet RISK card.
//
// Shows the DESCRIPTIVE unit-space risk of a single qualifying paper pick: units
// staked, tier (A/B/C), the capped quarter-Kelly fraction (in UNITS), and the
// model probability vs the devigged close. A no_bet row instead shows the honest
// "no-bet-below-floor" reason. There is no money / price field anywhere -- units
// and probabilities only.

import * as React from "react";
import { Badge } from "@/components/p6/Primitives";
import { InfoTip, ProvenanceBadge } from "@/components/depth";
import { tierBadgeClass } from "@/lib/tokens";
import { RISK_TERMS } from "./riskTerms";
import {
  type BetRiskRow,
  pctOrDash,
  unitsOrDash,
} from "./riskUtils";

function tierTone(tier: string | null): "gold" | "green" | "slate" {
  const t = (tier || "").toUpperCase();
  if (t === "S") return "gold";
  if (t === "A") return "green";
  return "slate";
}

function Stat({
  label,
  value,
  term,
  className,
}: {
  label: string;
  value: React.ReactNode;
  term?: string;
  className?: string;
}) {
  return (
    <div className={"flex flex-col gap-0.5 " + (className ?? "")}>
      <span className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
        {term ? <InfoTip text={RISK_TERMS[term]} ariaLabel={`what is ${label}?`} /> : null}
      </span>
      <span className="font-mono tabular-nums text-sm text-foreground">{value}</span>
    </div>
  );
}

/** A single per-bet risk card (units + tier + capped quarter-Kelly + model-vs-close). */
export function BestBetRiskCard({ row }: { row: BetRiskRow }) {
  const isBet = row.decision === "bet";
  return (
    <li className="rounded-lg border border-slate-800 bg-bg-panel/50 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-mono text-[12px] font-semibold text-foreground">
            {row.matchup}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">{row.market}</div>
        </div>
        {isBet ? (
          <span className={"inline-flex items-center gap-1"}>
            <span
              className={
                "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide " +
                tierBadgeClass(row.tier || "")
              }
            >
              tier {row.tier || "--"}
            </span>
            <InfoTip term="tier" ariaLabel="what is a tier?" />
          </span>
        ) : (
          <Badge tone="slate">NO BET</Badge>
        )}
      </div>

      {isBet ? (
        <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
          <Stat label="units staked" value={unitsOrDash(row.stakeUnits)} term="exposure" />
          <Stat label="1/4-Kelly" value={unitsOrDash(row.kellyUnits)} term="quarter_kelly" />
          <Stat label="model p" value={pctOrDash(row.modelProb)} term="probability" />
          <Stat label="devig close" value={pctOrDash(row.devigClose)} term="devig" />
        </div>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
          <span className="font-mono uppercase tracking-wide text-faint">below floor:</span>
          <span>{row.reason || "EV below the C floor -- the model matches the efficient close (a SUCCESS)."}</span>
          <InfoTip term="floor" text={RISK_TERMS.floor} ariaLabel="what is the tier floor?" />
        </div>
      )}

      <div className="mt-2 flex items-center justify-between">
        <ProvenanceBadge phase="exec_decision" model="capped quarter-Kelly" showTip={false} />
        <span className="font-mono text-[9px] uppercase tracking-wide text-faint">
          units only -- no money
        </span>
      </div>
    </li>
  );
}
