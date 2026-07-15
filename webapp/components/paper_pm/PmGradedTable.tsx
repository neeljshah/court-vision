"use client";

// PmGradedTable -- WS8: renders PmDisplayRow[] (output of toPaperTrailRows).
// Units-only columns; CLV sentinel shown honestly; no $ column anywhere.
//
// HONESTY RAILS:
//   - Only PmDisplayRow entries (dropped=false) are rendered.
//   - Dropped rows are excluded from the table entirely (never zero-filled).
//   - Units column: "1.50u" suffix, NEVER a "$" string.
//   - CLV: numeric ratio displayed as % when known; "no-close" for INSUFFICIENT_DATA.
//   - executed is ALWAYS false (paper-only); noted in an sr-only caption.
//   - No pnl / roi / dollar column is present anywhere.

import { cn } from "@/lib/utils";
import { EMPTY_CELL, tierBadgeClass } from "@/lib/tokens";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge, Unavailable } from "@/components/p6/Primitives";
import { Skeleton } from "@/components/ui/skeleton";
import type { PmDisplayRow, PmMappedRow } from "./paperTrailAdapter";

// ---------------------------------------------------------------------------
// Format helpers (no $ anywhere)
// ---------------------------------------------------------------------------

function fmtUnits(u: number): string {
  return `${u.toFixed(2)}u`;
}

function fmtProb(p: number | null): string {
  if (p == null) return EMPTY_CELL;
  return `${(p * 100).toFixed(1)}%`;
}

function fmtPriceTaken(p: number | null): string {
  if (p == null) return EMPTY_CELL;
  return p.toFixed(3);
}

function fmtClvDisplay(clvDisplay: number | "INSUFFICIENT_DATA"): {
  text: string;
  cls: string;
} {
  if (clvDisplay === "INSUFFICIENT_DATA") {
    return { text: "no-close", cls: "text-muted-foreground" };
  }
  const pct = (clvDisplay * 100).toFixed(2);
  const cls =
    clvDisplay > 0
      ? "text-success"
      : clvDisplay < 0
        ? "text-danger"
        : "text-muted-foreground";
  return { text: `${pct}%`, cls };
}

type ResultTone = "green" | "red" | "slate" | "amber";

function resultTone(result: string | null): ResultTone {
  if (!result) return "amber";
  switch (result.toLowerCase()) {
    case "win":
      return "green";
    case "loss":
      return "red";
    case "void":
    case "push":
      return "slate";
    default:
      return "amber";
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type PmGradedTableProps = {
  rows: PmMappedRow[];
  loading?: boolean;
  error?: string | null;
};

/**
 * PmGradedTable -- renders the output of toPaperTrailRows.
 *
 * Accepts PmMappedRow[] (union of PmDisplayRow | PmDroppedRow). Only
 * PmDisplayRow entries (dropped=false) are rendered; dropped rows are counted
 * and shown as a warning but NEVER fabricated into the table.
 */
export function PmGradedTable({ rows, loading, error }: PmGradedTableProps) {
  const displayRows: PmDisplayRow[] = rows.filter(
    (r): r is PmDisplayRow => !r.dropped,
  );
  const droppedCount = rows.length - displayRows.length;

  if (loading) {
    return (
      <div aria-busy="true" aria-label="Loading PM graded trades" className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }

  if (error) return <Unavailable reason={error} />;

  if (displayRows.length === 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-bg-subtle/40 px-4 py-10 text-center text-sm text-muted-foreground">
        {rows.length === 0
          ? "No graded PM trades yet."
          : `All ${rows.length} PM trades were dropped (missing required fields).`}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {droppedCount > 0 ? (
        <p className="text-[11px] text-warning">
          {droppedCount} row{droppedCount !== 1 ? "s" : ""} dropped (missing
          required fields -- not fabricated).
        </p>
      ) : null}

      <ScrollArea className="h-[480px] w-full rounded-lg border border-slate-800">
        <table
          className="min-w-full text-left"
          role="grid"
          aria-label="PM graded paper trade trail"
        >
          <caption className="sr-only">
            PM paper trail -- units and probability only, no dollar amounts.
            All trades are paper-only (executed=false).
          </caption>
          <thead className="sticky top-0 z-10 bg-bg-panel text-[10px] uppercase tracking-wide text-muted-foreground">
            <tr className="border-b border-slate-800">
              <th className="px-2 py-2">Venue</th>
              <th className="px-2 py-2">Market</th>
              <th className="px-2 py-2">Tier</th>
              <th className="px-2 py-2 text-right">Model P</th>
              <th className="px-2 py-2 text-right">Price</th>
              <th className="px-2 py-2 text-right">CLV</th>
              <th className="px-2 py-2">Result</th>
              <th className="px-2 py-2 text-right">Units</th>
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row) => {
              const clv = fmtClvDisplay(row.clvDisplay);
              return (
                <tr
                  key={row.bet_id}
                  className="border-b border-border text-[12px] text-foreground transition-colors hover:bg-surface-2"
                >
                  <td className="px-2 py-1.5 font-mono text-[11px] text-muted-foreground">
                    {row.venue}
                  </td>
                  <td className="px-2 py-1.5 font-mono text-[11px] text-muted-foreground">
                    {row.market_id || EMPTY_CELL}
                  </td>
                  <td className="px-2 py-1.5">
                    {row.tier ? (
                      <span
                        className={cn(
                          "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase",
                          tierBadgeClass(row.tier),
                        )}
                      >
                        {row.tier}
                      </span>
                    ) : (
                      <span className="text-faint">{EMPTY_CELL}</span>
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono tabular-nums text-foreground">
                    {fmtProb(row.model_prob)}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono tabular-nums text-foreground">
                    {fmtPriceTaken(row.price_taken)}
                  </td>
                  <td
                    className={cn(
                      "px-2 py-1.5 text-right font-mono tabular-nums",
                      clv.cls,
                    )}
                  >
                    {clv.text}
                    {row.clv_is_proxy && row.clvDisplay !== "INSUFFICIENT_DATA" ? (
                      <span
                        title="CLV vs proxy close, not real book"
                        className="ml-0.5 text-warning"
                      >
                        ~
                      </span>
                    ) : null}
                  </td>
                  <td className="px-2 py-1.5">
                    <Badge tone={resultTone(row.result)}>
                      {row.result ?? "pending"}
                    </Badge>
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono tabular-nums text-foreground">
                    {fmtUnits(row.units)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </ScrollArea>

      <p className="text-[11px] text-faint">
        Paper mode -- stakes are units (no $). CLV (better-number-than-close) is
        the only honest calibration yardstick. No edge is claimed.
        "no-close" = INSUFFICIENT_DATA (closing line not captured).
      </p>
    </div>
  );
}
