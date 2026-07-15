"use client";

// ExposureLimitsPanel.tsx -- the descriptive EXPOSURE / LIMITS + tier-floor policy.
//
// Explains the unit-space risk-control rails a desk could read: the tier EV-floor
// policy (A>=0.08 / B>=0.04 / C>=0.02, +0.01 when the close is a proxy; below the C
// floor = NO BET = the model matches the efficient close = a SUCCESS) and the
// descriptive per-sport / slate exposure caps. These are CONTROL LIMITS, not
// prescriptive money advice and never a $ amount. Nothing here sizes or places a
// real-money bet (real money is default-DENY).

import { InfoTip } from "@/components/depth";
import { Panel } from "@/components/p6/Primitives";
import { tierBadgeClass } from "@/lib/tokens";
import { RISK_TERMS } from "./riskTerms";
import { TIER_FLOORS, PROXY_FLOOR_BUMP } from "./riskUtils";

// Descriptive exposure caps (unit-space control limits, NOT money, NOT advice).
const EXPOSURE_CAPS: Array<{ scope: string; cap: string; note: string }> = [
  { scope: "per single leg", cap: "capped 1/4-Kelly", note: "no leg exceeds the capped quarter-Kelly unit size" },
  { scope: "per game", cap: "correlated", note: "same-game legs do not diversify -- counted at full correlation" },
  { scope: "per sport", cap: "descriptive cap", note: "a ceiling on open units within one sport" },
  { scope: "per slate", cap: "descriptive cap", note: "a ceiling on total open units across today's slate" },
];

export function ExposureLimitsPanel() {
  return (
    <Panel
      title="exposure & limits (descriptive control policy)"
      right={
        <InfoTip
          text="The unit-space risk-control rails: the tier EV-floor policy and the per-sport / slate exposure caps. These are descriptive control limits a desk could read, never prescriptive money advice and never a $ amount."
          ariaLabel="what is the limits policy?"
        />
      }
    >
      {/* Tier-floor policy. */}
      <div className="mb-2 flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
        tier EV-floor policy
        <InfoTip term="floor" text={RISK_TERMS.floor} ariaLabel="what is the tier floor?" />
      </div>
      <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-3">
        {TIER_FLOORS.map((t) => (
          <li
            key={t.tier}
            className="flex items-center gap-2 rounded-lg border border-slate-800 bg-bg-panel/40 px-3 py-2"
          >
            <span
              className={
                "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide " +
                tierBadgeClass(t.tier)
              }
            >
              {t.tier}
            </span>
            <div className="min-w-0">
              <div className="font-mono tabular-nums text-[12px] text-foreground">
                EV &ge; {t.floor.toFixed(2)}
              </div>
              <div className="text-[10px] text-faint">{t.note}</div>
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
        Floors are raised <span className="font-mono text-foreground">+{PROXY_FLOOR_BUMP.toFixed(2)}</span> when
        the close we settle against is a PROXY (not a true settled close). Below the C floor it is an
        honest <span className="font-mono uppercase text-foreground">NO BET</span> -- the model matches
        the efficient close, which is a SUCCESS, not a failure.
      </p>

      {/* Exposure caps. */}
      <div className="mb-2 mt-4 flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
        exposure caps
        <InfoTip term="exposure_cap" text={RISK_TERMS.exposure_cap} ariaLabel="what is an exposure cap?" />
      </div>
      <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        {EXPOSURE_CAPS.map((c) => (
          <li
            key={c.scope}
            className="rounded-lg border border-slate-800 bg-bg-panel/40 px-3 py-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[11px] text-foreground">{c.scope}</span>
              <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">{c.cap}</span>
            </div>
            <div className="mt-0.5 text-[10px] text-faint">{c.note}</div>
          </li>
        ))}
      </ul>

      <p className="mt-3 font-mono text-[9px] uppercase tracking-wide text-faint">
        descriptive limits in UNITS -- no money field -- no advice -- real money DENY (paper only)
      </p>
    </Panel>
  );
}
