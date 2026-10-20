"use client";

// ExecutionQualityPanel.tsx -- expected CLV at placement vs threshold, placement
// latency, and gated/ungated placement counts.
//
// HONESTY RAILS: UNITS/probability only, no $. Older ledger rows carry no
// exec_gate/latency -- n_gated stays 0 and averages stay "--", never a
// fabricated number. ASCII only. <=300 LOC.

import { Unavailable } from "@/components/p6/Primitives";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";
import type { ExecutionBlock } from "@/lib/paperToday";
import { EMPTY_CELL } from "@/lib/tokens";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";

function fmtPctSigned(v: number | null): string {
  if (v == null) return EMPTY_CELL;
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtMs(v: number | null): string {
  if (v == null) return EMPTY_CELL;
  return `${Math.round(v)}ms`;
}

export function ExecutionQualityPanel({
  execution,
  asOf,
  stale,
}: {
  execution: ExecutionBlock;
  asOf?: string | null;
  stale?: boolean;
}) {
  const q = execution?.quality ?? null;
  const t = execution?.thresholds ?? null;
  const noGated = !q || q.n_gated === 0;

  return (
    <div data-testid="execution-quality-panel">
      <Panel>
        <PanelHead title="Execution quality" asOf={asOf} stale={stale} />
        <div className="flex flex-wrap items-end gap-6 px-4 py-3">
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">gated placements</span>
            <Num className="text-sm font-semibold text-foreground">
              {q ? q.n_gated : 0}
            </Num>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">ungated placements</span>
            <Num className="text-sm font-semibold text-muted-foreground">
              {q ? q.n_ungated : 0}
            </Num>
          </div>
          <div className="flex max-w-md flex-col gap-0.5" data-testid="exec-quality-clv-unavailable">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">expected CLV</span>
            <Unavailable reason={CLV_UNAVAILABLE} />
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">median latency</span>
            <Num className="text-sm font-semibold text-foreground">
              {fmtMs(q?.median_placement_latency_ms ?? null)}
            </Num>
          </div>
          {t ? (
            <div className="flex flex-col gap-0.5">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">gate thresholds</span>
              <span className="font-data text-[12px] text-muted-foreground">
                max drift {fmtPctSigned(t.ingame_max_drift_pct)} / max spread{" "}
                {t.ingame_max_spread_bp.toFixed(0)}bp
              </span>
            </div>
          ) : null}
        </div>
        {noGated ? (
          <p className="px-4 pb-3 text-[12px] text-faint">
            No gated placements yet -- expected-CLV gating and latency stamping
            apply to newly placed in-game/prop bets only.
          </p>
        ) : null}
      </Panel>
    </div>
  );
}
