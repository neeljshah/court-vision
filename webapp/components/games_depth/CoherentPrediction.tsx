"use client";

// CoherentPrediction.tsx -- the ONE coherent headline prediction for a game.
//
// Reads the pregame model probabilities off the Report (the same anchor that
// spines the whole market surface), picks the highest-probability side, and shows
// it with a ProvenanceBadge (which engine + phase produced it) and an
// UncertaintyBar (probability + InfoTip). There is NO held-out band fabricated --
// if a residual band is not supplied the bar honestly shows the point only.
//
// HONESTY RAILS: probability only -- NO $ anywhere. A missing prob renders an
// honest empty state, never a fabricated number. vs_close is UNPROVEN.

import * as React from "react";
import type { Report } from "@/lib/api";
import { ProvenanceBadge, UncertaintyBar, InfoTip } from "@/components/depth";
import { Panel, PanelHead } from "@/components/ui/terminal";

export interface CoherentPredictionProps {
  report: Report | null;
  sport: string;
  className?: string;
}

// Descriptive per-sport engine label for the ProvenanceBadge. soccer family is
// Dixon-Coles-class; basketball is the possession Monte-Carlo sim; the rest use
// the rating-anchored model. Purely descriptive provenance, no numbers.
function engineLabel(sport: string): string {
  if (sport === "nba") return "possession MC";
  if (sport === "soccer" || sport === "soccer_intl") return "Dixon-Coles EW Poisson";
  if (sport === "mlb") return "MOV-Elo";
  if (sport === "tennis") return "Elo";
  return "rating-anchored";
}

interface HeadlinePick {
  label: string;
  prob: number | null;
}

// The coherent headline pick: highest-probability side of the pregame anchor.
function headlinePick(report: Report | null): HeadlinePick {
  const pg = report?.pregame;
  const probs = pg?.model_probs;
  const home = pg?.home;
  const away = pg?.away;
  if (!probs) return { label: "prediction", prob: null };
  const entries = Object.entries(probs).filter(
    ([, v]) => typeof v === "number" && Number.isFinite(v)
  ) as Array<[string, number]>;
  if (entries.length === 0) return { label: "prediction", prob: null };
  let [bestKey, bestVal] = entries[0];
  for (const [k, v] of entries) if (v > bestVal) [bestKey, bestVal] = [k, v];
  const side = bestKey.replace(/_ml$/, "");
  const label =
    side === "home" ? home ?? "home" : side === "away" ? away ?? "away" : side;
  return { label, prob: bestVal };
}

/** The single coherent prediction with provenance + uncertainty (no $). */
export function CoherentPrediction({
  report,
  sport,
  className,
}: CoherentPredictionProps) {
  const pick = headlinePick(report);
  const leak = report?.pregame?.leak_guard;

  return (
    <Panel className={className}>
      <PanelHead
        title="the one prediction"
        right={
          <span className="flex items-center gap-2">
            <InfoTip
              text={
                "One coherent prediction spines every market on this game. This is " +
                "the highest-probability side of the pregame anchor; the full market " +
                "surface below is derived from the same engine matrix."
              }
              ariaLabel="what is the coherent prediction?"
            />
            {leak ? (
              <span
                className={
                  "border px-1.5 py-px font-data text-[10px] font-bold uppercase tracking-wider " +
                  (leak.in_sample ? "border-danger text-down" : "border-success text-up")
                }
              >
                {leak.in_sample ? "in-sample" : "leak-free"}
              </span>
            ) : null}
          </span>
        }
      />

      <div className="p-3">
        <div className="mb-2 text-sm font-medium text-foreground">{pick.label}</div>

        <UncertaintyBar prob={pick.prob} label="P(pick)" />

        <div className="mt-3 flex items-center justify-between border-t border-border pt-2">
          <ProvenanceBadge model={engineLabel(sport)} phase="pregame" />
          <span className="font-data text-[10px] text-faint">
            vs-close UNPROVEN
          </span>
        </div>
      </div>
    </Panel>
  );
}
