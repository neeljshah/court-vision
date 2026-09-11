G405 fix 1b -- STRICT-GATE ATTEMPT, RETAINED UNMODIFIED, SUPERSEDED.

This attempt gated the discovery population with seen = ledger | sources.txt | discover.log
and applied the live MAX as a PER-QUERY cap. The archived live recipe
(/workspace/feeder/discover_sources.py sha256 00504c02ae66c2..) uses seen = ledger |
sources.txt only and a RUN-WIDE cap, so this gate was stricter than live and excluded 18
discover.log-only ids (codex-sol REJECT of ed876f9b3, ACCEPTANCE-1 / B10 / Q3).

Its numbers (17 YES / 12 NO / 1 UNKNOWN over a stricter-gate draw of 30) are HISTORICAL and
are never a current result. The current result is the fix 1c pass in the parent directory,
drawn from the live-recipe gate. att1_ungated/ (beside this directory) holds the first,
ungated attempt. Nothing here was edited after the codex-sol review; only the scan receipt
common_receipts/q6_scan.json was regenerated to emit opaque pattern indices instead of
restricted-token JSON labels (fix 1c CORRECTION 2).
