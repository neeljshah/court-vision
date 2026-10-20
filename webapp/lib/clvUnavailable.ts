// lib/clvUnavailable.ts -- the ONE site-wide CLV sentence and the July snapshot label.
// Truth source: docs/JOB_EVIDENCE_PACKET.md section 4 (aggregate CLV row) and
// section 5 (forward paper record). Every CLV tile, strip and stat renders this
// sentence through the Unavailable sentinel instead of a July proxy-close number.

export const CLV_UNAVAILABLE =
  "No closing-line-value reading exists as of 2026-10-19 (forward paper series since 2026-10-06, no verdict); the July 2026 snapshot's CLV figures were a proxy and are not shown.";

export const JULY_SNAPSHOT_LABEL =
  "July 2026 model snapshot, simulated units, not the forward record (as of 2026-07-16)";
