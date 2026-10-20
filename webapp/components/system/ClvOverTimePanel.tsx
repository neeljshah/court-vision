"use client";

import { Panel, Unavailable } from "@/components/p6/Primitives";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";

// ClvOverTimePanel -- the CLV-over-time slot on /system and /progress. Renders the
// site-wide CLV Unavailable sentence (lib/clvUnavailable.ts): no closing-line-value
// reading exists as of 2026-10-19 (JOB_EVIDENCE_PACKET s4/s5).
export function ClvOverTimePanel() {
  return (
    <Panel title="CLV over time">
      <div data-testid="clv-over-time-unavailable">
        <Unavailable reason={CLV_UNAVAILABLE} />
      </div>
    </Panel>
  );
}
