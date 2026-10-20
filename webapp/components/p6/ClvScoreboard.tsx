"use client";

import type { ReactNode } from "react";
import type { ClvScoreboard as Clv } from "@/lib/p5api";
import { Unavailable } from "./Primitives";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";

// ClvScoreboard -- renders the site-wide CLV Unavailable sentence. No real
// closing-line-value reading exists as of 2026-10-19 (JOB_EVIDENCE_PACKET s4/s5);
// the July 2026 snapshot's CLV numbers were proxy-close figures and are not shown.
// The clv prop stays so callers keep their feed wiring; its values never render.
export function ClvScoreboard({
  asOf,
  stale,
  extraRight,
}: {
  clv?: Clv | null | undefined;
  asOf?: string | null;
  stale?: boolean;
  extraRight?: ReactNode;
}) {
  return (
    <Panel>
      <PanelHead title="CLV scoreboard" asOf={asOf} stale={stale} right={extraRight} />
      <div className="p-4" data-testid="clv-scoreboard-unavailable">
        <Unavailable reason={CLV_UNAVAILABLE} />
      </div>
    </Panel>
  );
}
