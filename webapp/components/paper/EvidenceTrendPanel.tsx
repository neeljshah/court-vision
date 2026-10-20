"use client";

// EvidenceTrendPanel.tsx -- the CLV-trend slot on /paper. Renders the site-wide
// CLV Unavailable sentence (lib/clvUnavailable.ts): no closing-line-value reading
// exists as of 2026-10-19 (JOB_EVIDENCE_PACKET s4/s5), so no CLV trend is drawn.

import { Panel, PanelHead } from "@/components/ui/terminal";
import { Unavailable } from "@/components/p6/Primitives";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";

export function EvidenceTrendPanel({ asOf, stale }: { asOf?: string | null; stale?: boolean }) {
  return (
    <div data-testid="evidence-trend-panel">
      <Panel>
        <PanelHead title="Evidence trend (CLV over time)" asOf={asOf ?? null} stale={stale} />
        <div className="p-4">
          <Unavailable reason={CLV_UNAVAILABLE} />
        </div>
      </Panel>
    </div>
  );
}
