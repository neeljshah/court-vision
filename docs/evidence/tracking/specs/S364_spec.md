GAP S364 | sport all (maker channel) | worktree harness-h22 (master-based) | log cx_s364_fee_time_certification
# Fee and timestamp certification: rounding and receipt semantics can corrupt every fee-netted measurement (design: docs/evidence/harness/ASTRA_ROUND12_2026-09-21.md section 6 row 4)

SINGLE PROBLEM: scripts/platformkit/execution/venue_fees.py documents its own unverified corners (the per-order cent ceiling, the
sports-series exception, the maker ratio, a cap); fractional cumulative fills now reach it as Decimals (row S357) and are coerced
inside it; and capture receipts come from two clocks (local request / response times vs venue created_time). Nothing certifies
either against dated fixtures.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/execution/fee_time_certification.py` fails.

CHANGE:
1. scripts/platformkit/execution/fee_time_certification.py (<= 300 LOC, stdlib + decimal): (a) a DATED fee fixture table written
   from venue_fees.py's own cited schedule text (each row: contracts, price, expected whole-order fee, the rule that produces it,
   the source line in venue_fees.py) covering integer and FRACTIONAL cumulative quantities, the cent-ceiling boundary cases, prices
   1, 50 and 99 cents, and partial-fill sequences whose incremental fees must sum to the whole-order fee; `certify_fees()` runs
   them and reports every mismatch -- it NEVER edits venue_fees.py; a mismatch is a finding for the owner. (b) `clock_skew_report
   (rows)`: from capture rows compute, per source and per hour, the distribution of response_end minus venue created_time for
   trades and of response_end minus request_start (latency); flag negative skew (venue time after local receipt), skew drift over
   one second per hour, and rows whose request_start precedes tick_start. Counts and durations only; never a price.
2. tests/platformkit/execution/test_fee_time_certification.py (synthetic rows for every flag; the fee table is self-consistent).
3. Memo docs/evidence/harness/S364_fee_time_certification_2026-09-21.md with the finisher commands.

CONTROLS: PREPARE only, NEW files only (edit no pre-existing module; import landed code), construct / fixture tests, no real
archive run, no network, no measured calibration, fill or markout number. ACCEPTANCE: the per-file tests pass; every CLI has
--help; diff = NEW files only. Vocabulary follows contract Q6; automated scan required; assemble retracted-figure literals
from single digits. The memo ends with a NOT VERIFIED list. The pod is OFF.
