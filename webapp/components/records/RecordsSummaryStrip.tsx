"use client";

// RecordsSummaryStrip.tsx -- W1-records-surface summary strip.
// Shows total / settled / win% from the FILTERED slice (or full page slice).
// UNITS only -- NO $ / ROI / P&L token anywhere. ASCII only. Under 300 LOC.

import type { PaperPredictionRow } from "@/lib/types";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";

interface RecordsSummaryStripProps {
  rows:     PaperPredictionRow[];
  total:    number;  // total count from the envelope (not the page slice)
  loading?: boolean;
  /** Feed generation time (real timestamp from the predictions envelope). */
  asOf?:    string | null;
}

function StatCell({ label, value, tone = "slate" }: {
  label: string;
  value: string | number;
  tone?: "slate" | "up" | "down" | "stale";
}) {
  const valueCls = {
    slate: "text-foreground",
    up:    "text-up",
    down:  "text-down",
    stale: "text-stale",
  }[tone];
  return (
    <div className="flex flex-col gap-0.5">
      <span className="microlabel">{label}</span>
      <span data-testid={`summary-${label.toLowerCase().replace(/\s+/g, "-")}`}>
        <Num className={`text-[14px] font-semibold ${valueCls}`}>{value}</Num>
      </span>
    </div>
  );
}

export function RecordsSummaryStrip({ rows, total, loading = false, asOf = null }: RecordsSummaryStripProps) {
  const settled    = rows.filter((r) => r.outcome != null);
  const wins       = settled.filter((r) => r.outcome === "win").length;
  const losses     = settled.filter((r) => r.outcome === "loss").length;
  const winPct     = settled.length > 0 ? (wins / settled.length) * 100 : null;
  const winPctStr  = winPct != null ? `${winPct.toFixed(1)}%` : "--";
  // Sample-size guard: only color win-rate as a result once N is meaningful.
  // Below 30 settled, win-rate is small-N noise -- show it neutral (no up/down ink).
  const winRateHasN = settled.length >= 30;
  const winTone: "slate" | "up" | "down" | "stale" =
    !winRateHasN ? "slate"
    : winPct != null && winPct >= 52 ? "up"
    : winPct != null && winPct < 48 ? "down"
    : "slate";
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

  if (loading) {
    return (
      <div data-testid="records-summary-strip">
        <Panel>
          <PanelHead title="Summary" asOf={asOf} />
          <div className="flex flex-wrap gap-6 px-4 py-3">
            {["total", "settled", "win-rate", "units"].map((k) => (
              <div key={k} className="h-8 w-16 animate-pulse bg-surface-2" />
            ))}
          </div>
        </Panel>
      </div>
    );
  }

  return (
    <div data-testid="records-summary-strip" role="region" aria-label="records summary">
      <Panel>
        <PanelHead
          title="Summary"
          asOf={asOf}
          right={<span className="font-data text-[9px] text-faint">units only -- no edge is claimed</span>}
        />
        <div className="flex flex-wrap gap-6 px-4 py-3">
          <StatCell label="total" value={total} />
          <StatCell label="settled" value={settled.length} />
          <StatCell label="wins" value={wins} tone="up" />
          <StatCell label="losses" value={losses} tone="down" />
          <StatCell label="win rate" value={winPctStr} tone={winTone} />
          {!winRateHasN && settled.length > 0 && (
            <span className="self-end font-data text-[8px] text-faint">
              small sample (n&lt;30)
            </span>
          )}
          <StatCell label="page units" value={unitsStr} />

          {/* model_prob vs market_prob divergence -- W1-records-clv-analytics */}
          {divRows.length > 0 && (
            <>
              <div className="w-px self-stretch bg-border" aria-hidden />
              <div className="flex flex-col gap-0.5">
                <span className="microlabel">avg model vs market (prob)</span>
                {/* NEUTRAL tone: a signed divergence is not good/bad. Calibration, not edge. */}
                <span data-testid="summary-avg-model-edge">
                  <Num className="text-[14px] font-semibold text-foreground">{divStr}</Num>
                </span>
                <span className="font-data text-[8px] text-faint">prob-space divergence, not edge</span>
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="microlabel">max divergence</span>
                <span data-testid="summary-max-divergence">
                  <Num className="text-[14px] font-semibold text-faint">{maxDivStr}</Num>
                </span>
                <span className="font-data text-[8px] text-faint">{divRows.length} rows w/ both</span>
              </div>
            </>
          )}
        </div>
      </Panel>
    </div>
  );
}
