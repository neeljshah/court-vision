"use client";

// DistributionPanel.tsx -- full prediction / probability interval display.
//
// Shows the coherent pregame prediction (from CoherentPrediction) PLUS the
// prop P(over/under) distribution from the W2 props board, with UncertaintyBar
// for each. There is NO $ anywhere -- probabilities and model intervals only.
//
// HONESTY RAILS: no $ field, no fabricated probability, no edge claim.
// Missing prop lines -> explicit UNAVAILABLE (e.g. NBA offseason).
// clv_is_proxy shown honestly.

import * as React from "react";
import { cn } from "@/lib/utils";
import { UncertaintyBar } from "@/components/depth/UncertaintyBar";
import { ProvenanceBadge } from "@/components/depth/ProvenanceBadge";
import { Panel } from "@/components/p6/Primitives";
import { Unavailable, Empty } from "@/components/honest/HonestState";
import { isExtUnavailable } from "@/lib/p5api_ext";
import type { Report } from "@/lib/types";
import type { PropsBoardEnvelope, PlayerPropRow } from "@/lib/p5api_ext";

export interface DistributionPanelProps {
  report: Report | null;
  propsData: PropsBoardEnvelope | null;
  sport: string;
  className?: string;
}

// Derive headline pick (highest-prob side) from the report's model_probs.
function headlinePick(
  report: Report | null,
): { label: string; prob: number | null; low?: number; high?: number } {
  const pg = report?.pregame;
  const probs = pg?.model_probs;
  if (!probs) return { label: "prediction", prob: null };
  const entries = Object.entries(probs).filter(
    ([, v]) => typeof v === "number" && Number.isFinite(v),
  ) as Array<[string, number]>;
  if (entries.length === 0) return { label: "prediction", prob: null };
  let [bestKey, bestVal] = entries[0];
  for (const [k, v] of entries) if (v > bestVal) [bestKey, bestVal] = [k, v];
  const side = bestKey.replace(/_ml$/, "");
  const home = pg?.home ?? "home";
  const away = pg?.away ?? "away";
  const label =
    side === "home" ? home : side === "away" ? away : side;
  return { label, prob: bestVal };
}

function engineLabel(sport: string): string {
  if (sport === "nba") return "possession MC";
  if (sport === "soccer" || sport === "soccer_intl") return "Dixon-Coles";
  if (sport === "mlb") return "MOV-Elo";
  if (sport === "tennis") return "Elo";
  return "rating-anchored";
}

// Compact prop row: player + stat + P(over) / P(under) bars.
function PropRow({ row }: { row: PlayerPropRow }) {
  const lineStr = row.line != null ? ` ${row.line}` : "";
  return (
    <div className="flex flex-col gap-1 border-t border-slate-800 pt-2 first:border-t-0 first:pt-0">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-200">
          {row.player} <span className="text-slate-500">{row.stat}{lineStr}</span>
        </span>
        {row.tier && (
          <span className="font-mono text-[10px] text-slate-500">{row.book} | tier {row.tier}</span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <UncertaintyBar
          prob={row.p_over ?? null}
          low={
            row.p_over != null && row.proj_sigma != null && row.proj_mean != null
              ? Math.max(0, row.p_over - row.proj_sigma * 0.1)
              : undefined
          }
          high={
            row.p_over != null && row.proj_sigma != null && row.proj_mean != null
              ? Math.min(1, row.p_over + row.proj_sigma * 0.1)
              : undefined
          }
          label="P(over)"
        />
        <UncertaintyBar
          prob={row.p_under ?? null}
          label="P(under)"
        />
      </div>
      {row.clv_is_proxy && (
        <span className="font-mono text-[10px] text-amber-500">
          CLV proxy (no true close)
        </span>
      )}
    </div>
  );
}

/** Full prediction / interval display: headline + props (no $). */
export function DistributionPanel({
  report,
  propsData,
  sport,
  className,
}: DistributionPanelProps) {
  const pick = headlinePick(report);
  const engine = engineLabel(sport);
  const leak = report?.pregame?.leak_guard;

  const propsUnavail =
    !propsData ||
    isExtUnavailable(propsData) ||
    propsData.status === "unavailable";
  const propRows: PlayerPropRow[] = propsUnavail
    ? []
    : (propsData?.props ?? []);

  return (
    <Panel
      title="Prediction + interval"
      right={
        <span className="font-mono text-[10px] text-slate-500">
          probability only -- no $
        </span>
      }
      className={className}
    >
      {/* Headline game prediction */}
      <div className="mb-4 rounded border border-slate-800 bg-surface-1/30 p-3">
        <div className="mb-1 flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
            game prediction
          </span>
          <div className="flex items-center gap-2">
            {leak && (
              <span
                className={cn(
                  "rounded border px-1.5 py-0.5 font-mono text-[10px]",
                  leak.in_sample
                    ? "border-red-900 text-red-400"
                    : "border-emerald-900 text-emerald-400",
                )}
              >
                {leak.in_sample ? "in-sample" : "leak-free"}
              </span>
            )}
            <ProvenanceBadge model={engine} phase="pregame" showTip={false} />
          </div>
        </div>
        <p className="mb-2 text-sm font-medium text-slate-100">{pick.label}</p>
        <UncertaintyBar
          prob={pick.prob}
          low={pick.low}
          high={pick.high}
          label="P(pick)"
        />
        <p className="mt-2 font-mono text-[10px] text-slate-600">
          vs-close UNPROVEN -- calibration, not a market edge
        </p>
      </div>

      {/* Props distribution */}
      <div>
        <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
          prop projections
        </p>
        {propsUnavail ? (
          <Unavailable
            reason={
              (propsData as { reason?: string; note?: string } | null)
                ?.reason ??
              (propsData as { reason?: string; note?: string } | null)
                ?.note ??
              "prop lines unavailable (no feed)"
            }
          />
        ) : propRows.length === 0 ? (
          <Empty
            label="No prop lines"
            hint="Prop board is empty -- no lines captured for this game."
          />
        ) : (
          <div className="flex flex-col gap-2">
            {propRows.slice(0, 6).map((r, i) => (
              <PropRow key={`${r.player}-${r.stat}-${i}`} row={r} />
            ))}
            {propRows.length > 6 && (
              <p className="text-[10px] text-slate-600">
                +{propRows.length - 6} more prop lines
              </p>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}
