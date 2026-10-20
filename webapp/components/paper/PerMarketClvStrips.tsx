"use client";

// PerMarketClvStrips.tsx -- the per-market CLV slot on /paper. Renders the
// site-wide CLV Unavailable sentence (lib/clvUnavailable.ts) instead of the July
// 2026 snapshot's proxy-close median CLV figures: no closing-line-value reading
// exists as of 2026-10-19 (JOB_EVIDENCE_PACKET s4/s5). Props kept for wiring.

import type { ExecutionBlock } from "@/lib/paperToday";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { Unavailable } from "@/components/p6/Primitives";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";

export function PerMarketClvStrips({
  asOf,
  stale,
}: {
  execution?: ExecutionBlock;
  asOf?: string | null;
  stale?: boolean;
}) {
  return (
    <div data-testid="per-market-clv-strips">
      <Panel>
        <PanelHead title="CLV by market" asOf={asOf} stale={stale} />
        <div className="p-4">
          <Unavailable reason={CLV_UNAVAILABLE} />
        </div>
      </Panel>
    </div>
  );
}
