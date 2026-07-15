"use client";

// ValidatedSignalsStrip.tsx -- the per-sport "which signals feed this sport" strip.
//
// Renders each gate-tested signal for the sport as a SignalVerdictBadge with its
// deciding stat on hover. The ONLY SHIP across the four sports is soccer's
// corners-asof CALIBRATION prior (vs_close UNPROVEN); everything else is an
// honest REJECT / INSUFFICIENT_DATA / TIER3_BLOCKED. A REJECT is a SUCCESS, not a
// failure. Sports with no gated catalog show an honest empty line.
//
// HONESTY RAILS: no $ field; no edge implied. These are scouting verdicts, not a
// bet recommendation.

import * as React from "react";
import { SignalVerdictBadge, InfoTip } from "@/components/depth";
import { sportSignals } from "./sportSignals";
import { Panel, PanelHead } from "@/components/ui/terminal";

export interface ValidatedSignalsStripProps {
  sport: string;
  className?: string;
}

/** The gate-tested signals that feed a sport's prediction (verdict chips). */
export function ValidatedSignalsStrip({
  sport,
  className,
}: ValidatedSignalsStripProps) {
  const signals = sportSignals(sport);

  return (
    <Panel className={className}>
      <PanelHead
        title="validated signals"
        right={
          <InfoTip
            text={
              "Candidate signals that were run through the leak-free gate for this " +
              "sport. A SHIP is a calibration-only survivor (vs_close UNPROVEN), " +
              "never a market edge. A REJECT is a recorded success, not a failure."
            }
            ariaLabel="what are validated signals?"
          />
        }
      />

      <div className="p-3 text-xs">
        {signals.length === 0 ? (
          <p className="font-data text-[11px] text-faint">
            No gate-tested signals catalogued for this sport yet -- honest empty.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {signals.map((s, i) => (
              <li
                key={`${s.name}-${i}`}
                className="flex flex-wrap items-center justify-between gap-2"
              >
                <span className="text-muted-foreground">{s.name}</span>
                <SignalVerdictBadge verdict={s.verdict} stat={s.stat} />
              </li>
            ))}
          </ul>
        )}

        <p className="mt-2 border-t border-border pt-2 font-data text-[10px] leading-relaxed text-faint">
          Gate verdicts feed the model as priors/scouting only. Calibration, not a
          market edge. vs-close UNPROVEN. No $.
        </p>
      </div>
    </Panel>
  );
}
