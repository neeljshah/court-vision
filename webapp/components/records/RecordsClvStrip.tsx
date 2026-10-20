"use client";

// RecordsClvStrip.tsx -- the /records CLV strip. Renders the site-wide CLV
// Unavailable sentence (lib/clvUnavailable.ts): no closing-line-value reading
// exists as of 2026-10-19 (JOB_EVIDENCE_PACKET s4/s5); the July 2026 snapshot's
// proxy-close CLV figures are not shown. Props kept for the page's feed wiring.

import type { ClvScoreboard, Unavailable } from "@/lib/types";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { Unavailable as UnavailablePanel } from "@/components/p6/Primitives";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";

interface RecordsClvStripProps {
  clv?:     ClvScoreboard | Unavailable | null;
  loading?: boolean;
  asOf?:    string | null;
}

export function RecordsClvStrip(_props: RecordsClvStripProps) {
  return (
    <div data-testid="records-clv-strip" role="region" aria-label="CLV scoreboard">
      <Panel>
        <PanelHead title="CLV Scoreboard" />
        <div className="px-4 py-3">
          <UnavailablePanel reason={CLV_UNAVAILABLE} />
        </div>
      </Panel>
    </div>
  );
}
