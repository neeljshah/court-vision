GAP G132 | sport basketball | worktree a3 | log cx_g132_additive_candidate_union
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This is the design the MECHANISM points at, not another guess. Read
docs/evidence/tracking/g129_why_more_candidates_loses_recall memo,
g123_low_contrast_lines_2026-09-02.md and g120_fragment_merge_2026-09-02.md first.
THE CHAIN, and each step narrowed the problem:
  - G115: paint-line detection recall is 25/68 visible lines = 36.76 pct, Wilson [26.30, 48.64].
  - G120 (fragment merging) and G123 (CLAHE contrast) both REJECTED -- recall fell to 35.29 pct and
    33.82 pct, and CLAHE recovered NONE of the 17 low-contrast misses.
  - G129 found why, and it corrected the orchestrator's own framing. Neither intervention was
    ADDITIVE; both were REPLACEMENTS. CLAHE regenerates the entire LSD proposal set (witness
    wnba_05 frame 6912 lane_right: segments 77 -> 82, groups 58 -> 57, and the group that previously
    matched the true line no longer matches), and merging replaces fragment spans, changing group
    geometry. Mechanism split: CLAHE proposal-set change 7 of 10 records (70 pct), merge geometry 3
    (30 pct), and greedy correspondence claiming, top-N eviction and non-determinism 0 (0 pct).
  - The baseline reproduced at 25/68 TWICE, so the pipeline is deterministic and both REJECTs stand.
THE UNTRIED DESIGN: keep the original proposals AND add the enhanced ones. Run segment detection on
the original frame and on the contrast-enhanced frame, UNION the segments, and group once over the
union. Then a true line found in the original cannot be lost by enhancement, because its segments
are still present -- which is exactly the loss G129 traced in 7 of 10 cases.
  (a) PRE-REGISTER before running: the enhancement parameters (reuse G123's committed ones rather
      than picking new ones, and say so), how duplicate or near-duplicate segments across the two
      sets are handled, and whether grouping runs once over the union or separately per set. Write
      these in the memo BEFORE any number.
  (b) RE-MEASURE on the SAME 30 frames and SAME 68 visible lines under the protocol frozen at
      98b7d6974. Do not re-choose the correspondence tolerances and do not relabel visibility.
      Report recall before and after with Wilson 95 pct intervals, per line role.
  (c) VERIFY THE ADDITIVE PROPERTY DIRECTLY, and this is the point of the row: confirm that every
      true line matched in the 25/68 baseline is STILL matched under the union. If any baseline
      match is lost, the union is not behaving additively and you must say why before reporting any
      gain. A design justified by additivity that is not additive is worse than no design.
  (d) MEASURE THE COST. Report candidate precision before and after against the G84 audited labels,
      and the candidate volume. A union roughly doubles the proposal set, so precision will fall by
      construction; the question is whether it falls faster than recall rises. Report both.
  (e) STATE the implied all-four-line co-occurrence and compare it to the 1.83 pct that 36.76 pct
      implies. That is the number that decides whether a solve becomes possible.
DO NOT change any harness threshold, the coordinate contract, the rung ladder, the G84 sample or
seed, the G115 visibility labels, line_calibration.py, or the detector parameters 28.0 / 5.0 / 10.0.
Do not declare court_feet for any clip.
CONTEXT ON WHY BASKETBALL AT ALL: G111's 66.8 pct reachability was RETRACTED after the G126 audit
found its labels agree with source frames only 22/45 = 48.9 pct; the current estimate is 33.8 pct
and G130 is re-censusing it. At 33.8 pct basketball is still far above soccer (0/100), football (a
third direction in 0/60) and baseball (1/80), so it remains the only sport where detector work is a
lever that exists. But do NOT cite 66.8 pct anywhere.
ACCEPTANCE RULE:
  metric        = recall on the same 68 visible lines before and after the union, Wilson 95 pct
                  intervals; AND whether all 25 baseline matches survive; AND precision before/after
  before        = recall 25/68 = 36.76 pct; CLAHE-as-replacement 23/68; merge-as-replacement 24/68
  bar           = NO pass bar on the gain. Success is the union preregistered, the additive property
                  checked directly, and recall and precision both re-measured on the frozen sample.
                  A third REJECT is a full success and would say the line route is exhausted, which
                  is worth knowing before more effort goes into it.
  n             = the same 30 frames and 68 visible lines; state both denominators
  eye check     = REQUIRED. Render union candidates and look at them. A union that scores well by
                  blanketing the frame with segments until something lands on every line is the
                  failure mode, and only the eye and the precision number catch it together.
  must not move = the G93/G115 frozen protocol at 98b7d6974, the G84 sample and seed, the G115
                  visibility labels, every detector parameter, line_calibration.py, every harness
                  threshold, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g132_additive_candidate_union_2026-09-0X.md with the parameters
stated first, the additive-property check, before/after recall and precision, the implied
co-occurrence, the renders, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g132_union/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a3, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
