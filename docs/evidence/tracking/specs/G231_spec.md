GAP G231 | sport tennis | worktree a5 | log g231_out_of_bounds_structure
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. `domains/` is READ
and IMPORT only. Build in `scripts/platformkit/tracking/`.

**S1 MACHINE: RUN LOCALLY. Do NOT use the pod** -- G211b is measuring per-frame TIME there and any load
corrupts it. **Every input is already committed, so this row needs no network at all:**
`docs/evidence/tracking/g219_inputs/tennis_ref01_tracking_data.csv`,
`docs/evidence/tracking/g219b_inputs/tennis_01_tracking_data.csv`,
`docs/evidence/tracking/g219b_inputs/tennis_02_tracking_data.csv`. **Verify each SHA-256 (given in
G230's memo) and report it.**

**WHY THIS ROW EXISTS -- G230 FOUND SOMETHING LARGE AND DID NOT EXPLAIN IT, BY DESIGN.** G230 was
deliberately descriptive. It measured, against the adapter's own declared **78 x 36 ft** plane:

    | table | player rows outside | fraction | outside ft: median / p90 / p99 / max | beyond generous run-off |
    |---|---:|---:|---|---:|
    | `tennis_ref01` |    196 | **13.71 pct** | 1.661 / 7.331 / 9.166 / 12.628 |    0 |
    | `tennis_01`    | 12,805 | **76.37 pct** | 3.325 / 16.849 / 25.928 / 33.985 | 1,171 |
    | `tennis_02`    |  1,140 | **75.80 pct** | 4.723 / 12.586 / 24.211 / 29.626 |   57 |

**Three quarters of player rows in two tables lie outside the court those tables claim to be measured
in, and G230 explicitly did not ask why.** **The asymmetry is the lever: `tennis_ref01` is broadly
plausible while the other two are not, so this is NOT a uniform property of the tennis path and
something distinguishes them.**

THE QUESTION: **is the out-of-bounds mass STRUCTURED -- a consistent direction, a scale error, a
specific failing clip or camera -- or is it unstructured spread?**

**A DIFFERENCE ALREADY VISIBLE IN THE METADATA, which you should test rather than assume:**
`tennis_ref01` declares **29.97 fps and source height 360**; `tennis_01` and `tennis_02` declare
**59.94005994005994 fps and source height 1080** (G219b). **Source width is NOT recorded in any of
them.** So they are different captures at different resolutions.

METHOD:
  1. Confirm SHA-256, row counts (1,861 / 19,437 / 1,637) and that each declares
     `coordinate_space=court_feet`. **Split rows by `cls`** -- G219 established the historical ball id
     collides with player epoch ids, so do not assume every row is a player. Name the ELIGIBLE
     DENOMINATOR per table.
  2. **DIRECTION IS THE PRIMARY DIAGNOSTIC.** For every out-of-bounds player row, classify WHICH side it
     exceeds -- `x < 0`, `x > 78`, `y < 0`, `y > 36` -- and report the joint distribution per table.
     **A mass concentrated beyond ONE edge is a translation or origin error; mass beyond BOTH ends of
     the same axis is a SCALE error; mass spread over all four is unstructured.** These three have
     completely different causes and completely different fixes, so **say which pattern you observe.**
  3. **TEST THE SCALE HYPOTHESIS EXPLICITLY.** If the projection's scale were wrong by a factor k, then
     dividing the coordinates by k would bring the bulk inside the plane. **Fit the single k that
     minimises out-of-bounds mass per table and report it, along with the residual out-of-bounds
     fraction at that k.** **A k close to 1 refutes the scale hypothesis; a k near a meaningful ratio is
     a strong lead.** Note the singles court is **78 x 27 ft** against the doubles **78 x 36 ft**, so
     `36/27 = 1.333` is one ratio worth naming -- **but be careful, a doubles model is LARGER than
     singles, so a singles/doubles mix-up alone cannot push players OUT; say so if the arithmetic does
     not support it rather than forcing the story.**
  4. **IS IT A FEW BAD TRACKS OR THE WHOLE TABLE?** Report the distribution of out-of-bounds fraction
     PER TRACK. **"A handful of tracks are entirely off-court while the rest are clean" is a completely
     different finding from "every track is uniformly 76 pct off-court"**, and it decides whether this
     is a per-track identity failure or a global projection failure.
  5. **IS IT TIME-LOCALISED?** Report out-of-bounds fraction against source frame. **If the bad rows
     cluster in a contiguous span, the homography was wrong for part of the clip** -- consistent with a
     camera lock that drifted or a re-solve that failed. `domains/tennis/tracking/camera_lock.py` holds
     drift-checked homography reuse (`LOCK_MIN_FRESH_SOLVES = 3`, `DRIFT_CEILING_720P_PX = 5.0`); the
     tables carry `calibration_provenance` and `projection_status`, **so report the out-of-bounds
     fraction BROKEN DOWN BY those columns.** That is likely the single most informative cut available.
  6. **Do NOT fix anything, do NOT propose a `src/` or `domains/` change, and do NOT introduce a gate or
     threshold.** The 78 x 36 plane is the adapter's declared model, used here as a reference. **If your
     evidence points at a specific cause, state it as a diagnosis with its `file:line` basis and stop.**

**HONEST LIMITATIONS to state, not discover:** three clips of one sport from a NON-DETERMINISTIC route
(G190/G195/G198/G203), so you are diagnosing THESE tables, not a population. **A row being inside the
court is NOT evidence it is correct** -- plausibility is necessary, never sufficient, exactly as G230
said. Source width is unrecorded, so any pixel-space reasoning is limited. If `calibration_provenance`
or `projection_status` has too few distinct values to be informative, say so rather than manufacturing a
breakdown.

ACCEPTANCE RULE:
  metric        = per table: joint distribution of which edge is exceeded; the best-fit scale k and the
                  residual out-of-bounds fraction at that k; per-track out-of-bounds distribution;
                  out-of-bounds against source frame; and the breakdown by `calibration_provenance` and
                  `projection_status`
  before        = G230 measured 76.37 pct / 75.80 pct / 13.71 pct of player rows outside the declared
                  plane and deliberately did not explain it; the cause is unknown and the asymmetry
                  between tables is unexplained
  bar           = NO pass bar. **"The out-of-bounds mass is unstructured" is a FULL SUCCESS** and would
                  say the projection is simply noisy rather than systematically wrong. **A named
                  structure -- one edge, one scale factor, a few tracks, one time span, or one
                  provenance value -- is the other full success.** Do not force a story the numbers do
                  not support.
  n             = 3 committed tables, 22,935 rows (CONSTRUCT, exhaustive for coordinate-valid rows)
  eye check     = none; this row is table analysis
  must not move = every threshold, bar and verdict, the coordinate contract, the harness, the 78 x 36 ft
                  court model, `src/` (READ ONLY), `domains/` (READ and IMPORT ONLY), the pod (DO NOT
                  USE IT), the committed input tables
EVIDENCE: docs/evidence/tracking/g231_out_of_bounds_structure_2026-09-04.md with the SHA-256
confirmations, the per-edge joint distribution, the scale-fit result, the per-track and per-frame
distributions, the provenance/status breakdown, an explicit statement of which pattern was observed, an
explicit statement that no gate or threshold was introduced, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
