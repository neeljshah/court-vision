"use client";

// ClvInline -- honest inline CLV display. Shows CLV% when settled + real/proxy
// close exists; renders "--" (NEVER 0) when pending or no close.
// UNITS / probability only -- no dollar value is ever derived here.

import { cn } from "@/lib/utils";
import { fmtPct } from "@/lib/utils";
import { EMPTY_CELL } from "@/lib/tokens";
import type { PaperTrailRow } from "@/lib/p5api";

function clvCellClass(v: number | null): string {
  if (v == null) return "text-muted-foreground";
  if (v > 0) return "text-success";
  if (v < 0) return "text-danger";
  return "text-muted-foreground";
}

function isSettledWithClose(r: PaperTrailRow): boolean {
  return (
    r.graded &&
    r.clv_pct != null &&
    !r.clv_unavailable &&
    r.clv_status !== "no_close" &&
    r.clv_status !== null
  );
}

type Props = {
  row: PaperTrailRow;
  showStatus?: boolean;
};

export function ClvInline({ row, showStatus }: Props) {
  const settled = isSettledWithClose(row);
  const isProxy = row.clv_is_proxy;

  if (!settled) {
    // pending / no-close / void -- NEVER render a 0-fill value.
    const label =
      row.status === "open" ? "pending" : row.clv_unavailable ? "no-close" : EMPTY_CELL;
    return (
      <span className="font-mono text-[11px] text-muted-foreground">{label}</span>
    );
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 font-mono text-[11px]",
        clvCellClass(row.clv_pct),
      )}
    >
      {isProxy ? (
        <span title="CLV vs proxy close, not real book" className="text-warning">
          ~
        </span>
      ) : null}
      <span>{fmtPct(row.clv_pct as number)}</span>
      {showStatus && row.clv_status ? (
        <span className="text-[10px] text-muted-foreground">
          ({row.clv_status})
        </span>
      ) : null}
    </span>
  );
}
