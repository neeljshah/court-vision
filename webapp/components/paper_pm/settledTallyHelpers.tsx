"use client";

// settledTallyHelpers -- TallyTile component and deriveSettledTally helper.
//
// Extracted from PaperTrailSettled.tsx to keep that file under the 300-LOC rail.
// Re-exported via PaperTrailSettled for backward compat with existing tests.

import type { PaperTrailRow } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SettledTally {
  nSettled: number;
  nOpen: number;
  nWin: number;
  nLoss: number;
  nPush: number;
  nVoid: number;
}

// ---------------------------------------------------------------------------
// deriveSettledTally
// ---------------------------------------------------------------------------

export function deriveSettledTally(rows: PaperTrailRow[]): SettledTally {
  let nSettled = 0, nOpen = 0, nWin = 0, nLoss = 0, nPush = 0, nVoid = 0;
  for (const r of rows) {
    if (r.status === "open" || !r.graded) {
      nOpen++;
    } else {
      nSettled++;
      const o = (r.outcome || "").toLowerCase();
      if (o === "win") nWin++;
      else if (o === "loss") nLoss++;
      else if (o === "push") nPush++;
      else nVoid++;
    }
  }
  return { nSettled, nOpen, nWin, nLoss, nPush, nVoid };
}

// ---------------------------------------------------------------------------
// TallyTile -- small stat tile for the tally strip
// ---------------------------------------------------------------------------

export function TallyTile({
  label,
  value,
  valueClass,
  testId,
  loading,
}: {
  label: string;
  value: string;
  valueClass?: string;
  testId?: string;
  loading?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-bg-subtle px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      {loading ? (
        <div
          className="mt-0.5 h-6 w-12 animate-pulse rounded bg-slate-700/50"
          role="presentation"
          aria-busy="true"
          aria-label={`${label} loading`}
        />
      ) : (
        <div
          className={`mt-0.5 font-mono text-base tabular-nums ${valueClass ?? "text-foreground"}`}
          data-testid={testId}
        >
          {value}
        </div>
      )}
    </div>
  );
}
