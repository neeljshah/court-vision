GAP G248 | sport wnba | worktree a5 | log g248_projected_line_image_agreement
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G243c may be running on a6; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and say in your memo that you checked and when you began. EXCLUDE
YOUR OWN PROCESS AND YOUR OWN CHECKER COMMAND from that check** -- a G243c dispatch refused on a self-match
and had to be re-issued. The `track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs,
`inplay_capture_runner` and `foundry_runner` are PERMANENT residents and the load floor.

**READ THE LANDED G242, G244 AND G247 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- THREE SIGNAL FAMILIES ARE NOW EXHAUSTED AND ONE REMAINS.**
  - **G242:** G222's acceptance rule accepted **89 of 89** whole-game frames, including replays, graphics,
    close-ups and the wrong hoop end.
  - **G244:** against blind VALID/INVALID labels committed before any diagnostic was read, **no match
    diagnostic separates the classes** -- matches, inliers, inlier ratio and RMS all interpenetrate -- and
    **the single-frame cut-drop idea failed too** (cut drops of 128 and 165 sit inside an ordinary range
    of -283 to 170).
  - **G247:** a G242-exact replay (control 89/89, zero mismatches) tested seven pre-registered quad-shape
    checks and **none separates.** Its most telling line: **no INVALID map inverted, lost convexity,
    changed corner order, or placed a projected corner outside the image.** **Every wrong map is a
    perfectly well-formed, convex, correctly-wound, in-bounds quad of plausible area.**

**So the shape of the projection carries no information, and neither does the quality of the match. The
one thing never tested is whether the projection AGREES WITH WHAT IS ACTUALLY IN THE IMAGE.** That is
precisely what the human eye check does: it asks whether the projected arc lands on a painted arc. **This
row mechanises the eye check itself.**

THE QUESTION: **do the projected court LINES coincide with real image structure, and does that separate
valid maps from invalid ones?**

METHOD:
  1. **REUSE COMMITTED DATA. Do NOT re-run the match.** G247 persisted the per-frame homographies and
     ordered corners; G244's blind labels are committed at
     `docs/evidence/tracking/g244_blind_validity_labels_2026-09-04.csv`. **Load both. Do NOT relabel.**
     Decode the same 89 stride-2000 frames in ONE sequential pass to get clean pixels -- **the G242
     renders are 960x540 overlays and are NOT suitable as the image input.**
  2. **Project the court model's LINE GEOMETRY, not just the four corners** -- baselines, sidelines, lane
     boundaries, the free-throw line, the three-point arc and the centre circle -- sampling points along
     each curve.
  3. **COMPUTE THESE PRE-REGISTERED SIGNALS AND REPORT EVERY ONE, whatever the outcome.** Fixed here so
     none can be chosen after seeing results:
     **(a) EDGE-RESPONSE CONTRAST:** mean image gradient magnitude sampled ON the projected curves, minus
     the mean at **control points offset perpendicularly by a small distance** (use both a near and a far
     offset and say what you used). **The control offsets are essential** -- without them this measures
     "is there any edge in the image", which a jersey close-up would also satisfy.
     **(b) LINE-DETECTOR AGREEMENT:** run a line detector and report **the fraction of projected line
     length that has a detected segment within a stated pixel distance AND a similar orientation.**
     **(c) MARKING CONTRAST:** court markings are painted light against a darker floor, so report the
     brightness difference between on-curve samples and the same perpendicular control offsets.
     **(d) COVERAGE:** the fraction of projected curve length that falls inside the image bounds, since a
     projection can be well-formed yet mostly off-frame.
  4. **Report each signal's distribution BY CLASS with the OVERLAP stated explicitly**, in G244's and
     G247's exact format: the INVALID range, how many VALID fall inside it, the VALID range, how many
     INVALID fall inside it. **The overlap is the answer; a difference in medians is not.**
  5. **STATE THE MULTIPLE-COMPARISONS HAZARD.** Four signals against 89 in-sample points, roughly 27 VALID
     and 28 INVALID. **Say plainly that one of four looking good by chance is possible**, rather than
     presenting the best of four as a discovery.
  6. **CANNOT JUDGE is roughly a third of the sample and must never be merged into another class.** Report
     it separately -- and note that a low signal on CANNOT JUDGE frames is EXPECTED and is not evidence of
     separation between VALID and INVALID.
  7. **DO NOT FIT A THRESHOLD AND REPORT ITS ACCURACY ON THESE SAME 89 FRAMES.** If a signal separates
     cleanly, **say so, give the exact overlap, and label it IN-SAMPLE ONLY.**
  8. **OUT-OF-SAMPLE CONFIRMATION IS MANDATORY FOR ANY CLEAN SEPARATION.** Take a fresh sample from the
     same clip that was **NOT among the 89** -- a different stride offset -- blind label it by G244's
     protocol (labels written and committed BEFORE any signal is computed), and report whether the
     separation holds. **In-sample separation that fails out of sample is a NEGATIVE and must be reported
     as one.**
  9. **If nothing separates, say so plainly and do not soften it.** With G242, G244 and G247 that would
     establish **there is no available automatic validity signal at all**, and the programme would need a
     trained model or a different sensor rather than another hand-built statistic. That is a complete and
     highly consequential result.
 10. **Do NOT propose a production gate, and do NOT re-open the match-diagnostic or quad-shape questions.**

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,059 MB of 50,000), STOP and report if it fails.**
**Stream the decode; never write a full decode to disk. Do NOT re-commit G242's 12.4 MB artifact. Do NOT
delete the two abandoned partials in `footage_bridge`.** Delete every temporary artifact and report bytes
freed. Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** 89 frames, ONE clip, ONE seed, ONE arena, a wide stride, and
**one labeller's labels, inherited from G244 rather than made by you.** Eye-label reliability in this
programme has never cleared 80 pct blind agreement on any of four measured criteria, and **G246 showed
repeatable labels can be uniformly wrong**. **This row mechanises an eye check; it does not validate the
eye check.** A separation found here is in-sample until step 8 confirms it, and even then it is one clip
and one arena. Nothing here bears on automatic calibration, which remains 0/17.

ACCEPTANCE RULE:
  metric        = each of the four pre-registered signals with its per-class distribution and its explicit
                  overlap count; the CANNOT JUDGE distribution reported separately; the
                  multiple-comparisons statement; and, for any clean separation, the mandatory
                  out-of-sample confirmation
  before       = G242 (acceptance accepts everything), G244 (no match diagnostic separates; drop dynamics
                 fail) and G247 (no quad-shape check separates; every invalid map is a well-formed quad)
  bar          = NO pass bar. **"Nothing separates them" is a FULL SUCCESS and the most consequential
                 outcome available** -- with the three prior rows it would establish that no hand-built
                 signal indicates court validity and redirect the programme to a trained model or a
                 different instrument. **"Signal X separates them, confirmed out of sample" is the other
                 full success** and would be the programme's first automatic validity signal. Do not fit a
                 threshold, and do not present the best of four as a discovery.
  n            = 89 in-sample frames, 4 pre-registered signals, 1 clip, 1 seed, plus any out-of-sample
                 confirmation sample -- state every denominator in the verdict line
  eye check    = G244's committed blind labels are the ground truth; any out-of-sample labels must follow
                 the same blind protocol and be committed before any signal is computed
  must not move = every threshold, bar and verdict, G222's matcher settings, the seed construction, the
                  court model, the coordinate contract, the harness, G244's committed labels, G247's
                  persisted matrices, `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and
                  keeper, the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g248_projected_line_image_agreement_2026-09-04.md with the decode method,
the projected line geometry used, all four signals with per-class distributions and overlaps, the CANNOT
JUDGE breakdown, the multiple-comparisons statement, any out-of-sample confirmation, every disk-guard
probe, bytes freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE
MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
