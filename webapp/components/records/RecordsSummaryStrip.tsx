"use client";

// RecordsSummaryStrip.tsx -- W1-records-surface summary strip.
// Shows total / settled / win% from the FILTERED slice (or full page slice).
// UNITS only -- NO $ / ROI / P&L token anywhere. ASCII only. Under 300 LOC.

import type { PaperPredictionRow } from "@/lib/types";
import { cn } from "@/lib/utils";

interface RecordsSummaryStripProps {
  rows:     PaperPredictionRow[];
  total:    number;  // total count from the envelope (not the page slice)
  loading?: boolean;
}

function StatCell({ label, value, tone = "slate" }: {
  label: string;
  value: string | number;
  tone?: "slate" | "green" | "red" | "amber";
}) {
  const valueCls = cn("font-mono text-[14px] font-semibold tabular-nums", {
    "text-slate-200": tone === "slate",
    "text-emerald-400": tone === "green",
    "text-rose-400": tone === "red",
    "text-amber-400": tone === "amber",
  });
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono text-[9px] uppercase tracking-widest text-slate-600">{label}</span>
      <span className={valueCls} data-testid={`summary-${label.toLowerCase().replace(/\s+/g, "-")}`}>
        {value}
      </span>
    </div>
  );
}

export function RecordsSummaryStrip({ rows, total, loading = false }: RecordsSummaryStripProps) {
  const settled    = rows.filter((r) => r.outcome != null);
  const wins       = settled.filter((r) => r.outcome === "win").length;
  const losses     = settled.filter((r) => r.outcome === "loss").length;
  const winPct     = settled.length > 0 ? (wins / settled.length) * 100 : null;
  const winPctStr  = winPct != null ? `${winPct.toFixed(1)}%` : "--";
  const winTone    = winPct != null && winPct >= 52 ? "green" : winPct != null && winPct < 48 ? "red" : "slate";
  const totalUnits = rows.reduce((s, r) => s + (r.stake_units ?? 0), 0);
  const unitsStr   = totalUnits > 0 ? `${totalUnits.toFixed(2)}u` : "--";

  // model_prob vs market_prob divergence (probability-space, calibration not edge)
  const divRows = rows.filter((r) => r.model_prob != null && r.market_prob != null);
  const meanDiv = divRows.length > 0
    ? divRows.reduce((s, r) => s + (r.model_prob! - r.market_prob!), 0) / divRows.length
    : null;
  const maxDiv  = divRows.length > 0
    ? Math.max(...divRows.map((r) => Math.abs(r.model_prob! - r.market_prob!)))
    : null;
  const divStr  = meanDiv != null
    ? `${meanDiv >= 0 ? "+" : ""}${(meanDiv * 100).toFixed(1)}pp`
    : "--";
  const maxDivStr = maxDiv != null ? `${(maxDiv * 100).toFixed(1)}pp` : "--";
  const divTone: "green" | "red" | "amber" | "slate" =
    meanDiv == null ? "slate"
    : meanDiv > 0.02 ? "green"
    : meanDiv < -0.02 ? "red"
    : "amber";

  if (loading) {
    return (
      <div
        data-testid="records-summary-strip"
        className="flex flex-wrap gap-6 rounded border border-slate-800 bg-slate-900/50 px-4 py-3"
      >
        {["total", "settled", "win-rate", "units"].map((k) => (
          <div key={k} className="h-8 w-16 animate-pulse rounded bg-slate-800/60" />
        ))}
      </div>
    );
  }

  return (
    <div
      data-testid="records-summary-strip"
      role="region"
      aria-label="records summary"
      className="flex flex-wrap gap-6 rounded border border-slate-800 bg-slate-900/50 px-4 py-3"
    >
      <StatCell label="total" value={total} />
      <StatCell label="settled" value={settled.length} />
      <StatCell label="wins" value={wins} tone="green" />
      <StatCell label="losses" value={losses} tone="red" />
      <StatCell label="win rate" value={winPctStr} tone={winTone} />
      <StatCell label="page units" value={unitsStr} />

      {/* model_prob vs market_prob divergence -- W1-records-clv-analytics */}
      {divRows.length > 0 && (
        <>
          <div className="w-px self-stretch bg-slate-800" aria-hidden />
          <div className="flex flex-col gap-0.5">
            <span className="font-mono text-[9px] uppercase tracking-widest text-slate-600">
              avg model edge
            </span>
            <span
              data-testid="summary-avg-model-edge"
              className={cn("font-mono text-[14px] font-semibold tabular-nums", {
                "text-emerald-400": divTone === "green",
                "text-rose-400":    divTone === "red",
                "text-amber-400":   divTone === "amber",
                "text-slate-200":   divTone === "slate",
              })}
            >
              {divStr}
            </span>
            <span className="font-mono text-[8px] text-slate-700">prob-space, not edge</span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="font-mono text-[9px] uppercase tracking-widest text-slate-600">
              max divergence
            </span>
            <span
              data-testid="summary-max-divergence"
              className="font-mono text-[14px] font-semibold tabular-nums text-slate-400"
            >
              {maxDivStr}
            </span>
            <span className="font-mono text-[8px] text-slate-700">{divRows.length} rows w/ both</span>
          </div>
        </>
      )}

      <span className="self-end font-mono text-[9px] text-slate-700">
        units only -- no edge is claimed
      </span>
    </div>
  );
}
