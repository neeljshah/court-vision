"use client";

// RecordsRollup.tsx -- W1-records-clv-analytics: per-sport count/result rollup.
//
// Reads the already-fetched PaperPredictionRow[] from the records surface
// (all FETCHED rows -- not just the visible page slice) and groups by sport.
// Shows count, wins, losses, pending, and dominant tier per sport.
//
// Honesty rails:
//   - Renders real counts from the fetched data; never fabricates a result.
//   - No $ token. UNITS only. ASCII only. Under 300 LOC.
//   - "pending" = outcome is null/undefined (bet logged, not yet graded).
//   - Shows "no data" when rows=[] (empty fetch, never hides real rows).

import { useMemo } from "react";
import type { PaperPredictionRow } from "@/lib/types";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";

// ---------------------------------------------------------------------------
// Per-sport rollup row
// ---------------------------------------------------------------------------

interface SportBucket {
  sport:    string;
  count:    number;
  wins:     number;
  losses:   number;
  pending:  number;
  pushes:   number;
  // divergence stats: model_prob - market_prob
  nDiv:     number;   // rows with both model_prob and market_prob
  sumDiv:   number;   // sum of (model_prob - market_prob)
  maxDiv:   number;   // max absolute divergence
}

function buildBuckets(rows: PaperPredictionRow[]): SportBucket[] {
  const map = new Map<string, SportBucket>();

  for (const row of rows) {
    const sport = row.sport ?? "unknown";
    if (!map.has(sport)) {
      map.set(sport, {
        sport,
        count:   0,
        wins:    0,
        losses:  0,
        pending: 0,
        pushes:  0,
        nDiv:    0,
        sumDiv:  0,
        maxDiv:  0,
      });
    }
    const b = map.get(sport)!;
    b.count++;

    const oc = (row.outcome ?? "").toLowerCase();
    if (oc === "win")       b.wins++;
    else if (oc === "loss") b.losses++;
    else if (oc === "push") b.pushes++;
    else                    b.pending++;

    if (row.model_prob != null && row.market_prob != null) {
      const div = row.model_prob - row.market_prob;
      b.nDiv++;
      b.sumDiv += div;
      b.maxDiv = Math.max(b.maxDiv, Math.abs(div));
    }
  }

  return Array.from(map.values()).sort((a, b) => b.count - a.count);
}

// ---------------------------------------------------------------------------
// StatCell
// ---------------------------------------------------------------------------

function Cell({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: string | number;
  tone?: "slate" | "up" | "down" | "stale" | "muted";
}) {
  const cls = {
    slate:  "text-foreground",
    up:     "text-up",
    down:   "text-down",
    stale:  "text-stale",
    muted:  "text-faint",
  }[tone];
  return (
    <div className="flex flex-col gap-0.5 min-w-[44px]">
      <span className="microlabel">{label}</span>
      <span data-testid={`rollup-cell-${label.toLowerCase().replace(/\s+/g, "-")}`}>
        <Num className={`text-[13px] font-semibold ${cls}`}>{value}</Num>
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SportRow
// ---------------------------------------------------------------------------

function SportRow({ b }: { b: SportBucket }) {
  const settled  = b.wins + b.losses + b.pushes;
  const winPct   = settled > 0 ? (b.wins / settled) * 100 : null;
  const winTone: "up" | "down" | "slate" | "muted" =
    winPct == null ? "muted"
    : winPct >= 55 ? "up"
    : winPct < 45  ? "down"
    : "slate";

  const meanDiv  = b.nDiv > 0 ? b.sumDiv / b.nDiv : null;
  const divStr   = meanDiv != null
    ? `${meanDiv >= 0 ? "+" : ""}${(meanDiv * 100).toFixed(1)}pp`
    : "--";
  const divTone: "up" | "down" | "slate" | "muted" =
    meanDiv == null ? "muted" : meanDiv > 0 ? "up" : meanDiv < 0 ? "down" : "slate";

  return (
    <div
      data-testid={`rollup-sport-${b.sport}`}
      className="flex flex-wrap items-start gap-4 border border-border bg-surface-2 px-4 py-2.5"
    >
      {/* sport label */}
      <div className="flex flex-col gap-0.5 min-w-[64px]">
        <span className="microlabel">sport</span>
        <span
          data-testid={`rollup-sport-label-${b.sport}`}
          className="font-data text-[13px] font-semibold text-foreground uppercase"
        >
          {b.sport}
        </span>
      </div>

      <Cell label="total" value={b.count} />
      <Cell label="wins"  value={b.wins}  tone={b.wins > 0 ? "up" : "muted"} />
      <Cell label="losses" value={b.losses} tone={b.losses > 0 ? "down" : "muted"} />
      {b.pushes > 0 && <Cell label="push" value={b.pushes} tone="stale" />}
      <Cell label="pending" value={b.pending} tone={b.pending > 0 ? "stale" : "muted"} />

      {/* win rate */}
      <Cell
        label="win rate"
        value={winPct != null ? `${winPct.toFixed(1)}%` : "--"}
        tone={winTone}
      />

      {/* model-vs-market divergence */}
      <div className="flex flex-col gap-0.5 min-w-[56px]">
        <span className="microlabel">avg edge pp</span>
        <span data-testid={`rollup-div-${b.sport}`}>
          <Num
            className={`text-[13px] font-semibold ${
              divTone === "up" ? "text-up"
              : divTone === "down" ? "text-down"
              : "text-faint"
            }`}
          >
            {divStr}
          </Num>
        </span>
        {meanDiv != null && (
          <span className="font-data text-[8px] text-faint">model-mkt (prob)</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RecordsRollup -- main export
// ---------------------------------------------------------------------------

export interface RecordsRollupProps {
  /** All fetched prediction rows (full envelope, not just the current page). */
  rows:     PaperPredictionRow[];
  loading?: boolean;
  /** Total across all pages (from the API envelope) */
  total?:   number;
  /** Feed generation time (real timestamp from the predictions envelope). */
  asOf?:    string | null;
}

export function RecordsRollup({
  rows,
  loading = false,
  total,
  asOf = null,
}: RecordsRollupProps) {
  const buckets = useMemo(() => buildBuckets(rows), [rows]);

  if (loading) {
    return (
      <div data-testid="records-rollup" role="region" aria-label="per-sport rollup loading">
        <Panel>
          <PanelHead title="Per-Sport Breakdown" asOf={asOf} />
          <div className="space-y-2 px-4 py-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-14 w-full animate-pulse border border-border bg-surface-2" role="presentation" />
            ))}
          </div>
        </Panel>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div data-testid="records-rollup" role="region" aria-label="per-sport rollup">
        <Panel>
          <PanelHead title="Per-Sport Breakdown" asOf={asOf} />
          <div className="flex items-center justify-center px-4 py-6">
            <span data-testid="records-rollup-empty" className="font-data text-[11px] text-faint">
              no records to roll up -- waiting for data
            </span>
          </div>
        </Panel>
      </div>
    );
  }

  return (
    <div data-testid="records-rollup" role="region" aria-label="per-sport rollup">
      <Panel>
        <PanelHead
          title="Per-Sport Breakdown"
          asOf={asOf}
          right={
            total != null && total > rows.length ? (
              <span className="font-data text-[9px] text-faint">
                showing {rows.length} of {total} total -- load more pages to expand
              </span>
            ) : undefined
          }
        />
        <div className="space-y-2 px-4 py-3">
          {buckets.map((b) => (
            <SportRow key={b.sport} b={b} />
          ))}

          <p className="font-data text-[9px] text-faint">
            avg edge pp = mean(model_prob - market_prob) across rows with both values
            -- probability-space divergence only, calibration not edge
          </p>
        </div>
      </Panel>
    </div>
  );
}
