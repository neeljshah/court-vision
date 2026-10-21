// lib/clvUnavailable.ts -- the ONE site-wide CLV sentence and the July snapshot label.
// Truth source: docs/JOB_EVIDENCE_PACKET.md section 4 (aggregate CLV row) and
// section 5 (forward paper record). Every CLV tile, strip and stat renders this
// sentence through the Unavailable sentinel instead of a July proxy-close number.

import { FIGURES } from "@/lib/figures";

// The as-of is the forward-window figure's own date (docs/evidence/CANONICAL_FIGURES.json
// via lib/figures.ts), never a date typed here; the series start is the packet's.
export const CLV_UNAVAILABLE =
  `No closing-line-value reading exists as of ${FIGURES.forward_window_counts.as_of} (forward paper series since 2026-10-06, no verdict); the July 2026 snapshot's CLV figures were a proxy and are not shown.`;

export const JULY_SNAPSHOT_LABEL =
  "July 2026 model snapshot, simulated units, not the forward record (as of 2026-07-16)";
