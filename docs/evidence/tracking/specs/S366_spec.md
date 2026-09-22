GAP S366 | sport all (maker channel) | worktree harness-h24 (master-based) | log cx_s366_touch_queue_sensitivity
# At-limit fills as a NAMED SENSITIVITY using displayed touch size (design: docs/evidence/harness/ASTRA_ROUND12_2026-09-21.md section 1, at-limit paragraph; section 6 row 7)

SINGLE PROBLEM: the rebuilt capture records displayed size at the touch (raw_market yes_bid_size_fp / yes_ask_size_fp), so at-limit
fills can be studied -- but displayed size does not reveal intervening arrivals or true priority. The primary fill path must stay
strictly-through; an at-limit scenario must be isolated, conservative and impossible to confuse with the primary.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/execution/touch_queue_sensitivity.py` fails.

CHANGE:
1. scripts/platformkit/execution/touch_queue_sensitivity.py (<= 300 LOC): builds book_snapshots for
   scripts.platformkit.execution.tape_fill_sim.simulate_fills from S341 snapshot rows -- size at the EXACT quote price level only
   (from the ladder or the touch-size fields, parsed as Decimal from the raw strings); queue ahead = MULTIPLIER x displayed size
   with MULTIPLIER a declared scenario parameter (default 2, also 4 and 8); unknown size at that level -> NO at-limit fill (the
   quote can only fill strictly-through); depletion only by later matching-aggressor prints; no cancellation credit; reset on
   replace. Output fills are tagged scenario = "touch_queue_x<multiplier>" and are returned SEPARATELY from the primary
   strictly-through fills; a helper asserts the primary result is byte-identical with and without this module.
2. tests/platformkit/execution/test_touch_queue_sensitivity.py: exact-level mapping, unknown size blocks at-limit fills, larger
   multiplier never yields more fills, conservation with fractional sizes, primary-path isolation.
3. Memo docs/evidence/harness/S366_touch_queue_sensitivity_2026-09-21.md.

CONTROLS: PREPARE only, NEW files only (edit no pre-existing module; import landed code), construct / fixture tests, no real
archive run, no network, no measured calibration, fill or markout number. ACCEPTANCE: the per-file tests pass; every CLI has
--help; diff = NEW files only. Vocabulary follows contract Q6; automated scan required; assemble retracted-figure literals
from single digits. The memo ends with a NOT VERIFIED list. The pod is OFF.
