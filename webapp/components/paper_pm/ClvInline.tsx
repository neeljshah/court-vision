"use client";

// ClvInline -- honest inline CLV display. Shows CLV% when settled + real/proxy
// close exists; renders "--" (NEVER 0) when pending or no close.
// UNITS / probability only -- no dollar value is ever derived here.

import { cn } from "@/lib/utils";
import { fmtPct } from "@/lib/utils";
import { EMPTY_CELL } from "@/lib/tokens";
import { Num } from "@/components/ui/terminal";
import type { PaperTrailRow } from "@/lib/p5api";

function clvCellClass(v: number | null): string {
  if (v == null) return "text-faint";
  if (v > 0) return "text-up";
  if (v < 0) return "text-down";
  return "text-faint";
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
    return <Num className="text-[11px] text-faint">{label}</Num>;
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[11px]",
        clvCellClass(row.clv_pct),
      )}
    >
      {isProxy ? (
        <span title="CLV vs proxy close, not real book" className="text-stale">
          ~
        </span>
      ) : null}
      <Num>{fmtPct(row.clv_pct as number)}</Num>
      {showStatus && row.clv_status ? (
        <span className="text-[10px] text-faint">
          ({row.clv_status})
        </span>
      ) : null}
    </span>
  );
}
