"use client";

// ExecutionQualityPanel.tsx -- expected CLV at placement vs threshold, placement
// latency, and gated/ungated placement counts.
//
// HONESTY RAILS: UNITS/probability only, no $. Older ledger rows carry no
// exec_gate/latency -- n_gated stays 0 and averages stay "--", never a
// fabricated number. ASCII only. <=300 LOC.

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
            <span className="microlabel">gated placements</span>
            <Num className="text-[14px] font-semibold text-foreground">
              {q ? q.n_gated : 0}
            </Num>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="microlabel">ungated placements</span>
            <Num className="text-[14px] font-semibold text-muted-foreground">
              {q ? q.n_ungated : 0}
            </Num>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="microlabel">avg expected CLV</span>
            <Num
              className={`text-[14px] font-semibold ${
                q?.avg_expected_clv_pct != null
                  ? q.avg_expected_clv_pct >= 0
                    ? "text-up"
                    : "text-down"
                  : "text-faint"
              }`}
            >
              {fmtPctSigned(q?.avg_expected_clv_pct ?? null)}
            </Num>
            {t ? (
              <span className="font-data text-[9px] text-faint">
                min {fmtPctSigned(t.prop_expected_clv_min_pct)} (prop) / {" "}
                {fmtPctSigned(t.ingame_expected_clv_min_pct)} (in-game)
              </span>
            ) : null}
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="microlabel">median latency</span>
            <Num className="text-[14px] font-semibold text-foreground">
              {fmtMs(q?.median_placement_latency_ms ?? null)}
            </Num>
          </div>
          {t ? (
            <div className="flex flex-col gap-0.5">
              <span className="microlabel">gate thresholds</span>
              <span className="font-data text-[10px] text-muted-foreground">
                max drift {fmtPctSigned(t.ingame_max_drift_pct)} / max spread{" "}
                {t.ingame_max_spread_bp.toFixed(0)}bp
              </span>
            </div>
          ) : null}
        </div>
        {noGated ? (
          <p className="px-4 pb-3 text-[11px] text-faint">
            No gated placements yet -- expected-CLV gating and latency stamping
            apply to newly placed in-game/prop bets only.
          </p>
        ) : null}
      </Panel>
    </div>
  );
}
