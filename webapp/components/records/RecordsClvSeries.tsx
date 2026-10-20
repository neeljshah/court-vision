"use client";

// RecordsClvSeries.tsx -- the /records CLV-over-time slot. Renders the site-wide
// CLV Unavailable sentence (lib/clvUnavailable.ts) instead of the July 2026
// snapshot's proxy-close cumulative CLV curve: no closing-line-value reading
// exists as of 2026-10-19 (JOB_EVIDENCE_PACKET s4/s5). Props kept for wiring.

import type { ClvSeries } from "@/lib/types";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { Unavailable } from "@/components/p6/Primitives";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";

export interface RecordsClvSeriesProps {
  clvSeries?: ClvSeries | { status: "unavailable"; reason?: string } | null;
  loading?:   boolean;
  nNoClose?:  number;
  asOf?:      string | null;
}

export function RecordsClvSeries(_props: RecordsClvSeriesProps) {
  return (
    <div data-testid="records-clv-series" role="region" aria-label="CLV over time">
      <Panel>
        <PanelHead title="CLV Over Time" />
        <div className="px-4 py-3">
          <Unavailable reason={CLV_UNAVAILABLE} />
        </div>
      </Panel>
    </div>
  );
}
