GAP G247 | sport wnba | worktree a5 | log g247_projected_quad_validity
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G246 may be running on a6; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and say in your memo that you checked and when you began.** The
`track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner`
are PERMANENT residents and the load floor.

**READ THE LANDED G242 AND G244 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- THE MOST PROMISING VALIDITY SIGNAL WAS NEVER ACTUALLY TESTED.**
G244 blind-labelled G242's 89 whole-game overlays as VALID / INVALID / CANNOT JUDGE, committing the labels
BEFORE reading any diagnostic, and then found **no match diagnostic separates the classes**: VALID values
inside the INVALID range were 25/27 for matches, 25/27 for inliers, 28/28 for inlier ratio and 25/27 for
RMS. It also found G241b's single-frame cut drops (128 and 165 matches) sit **inside** the ordinary
drop range of -283 to 170. **Both negatives are clean and they stand.**

**But G244 could NOT test the cheap geometric sanity checks**, and reported exactly why:
**`NOT_REPRODUCIBLE_FROM_COMMITTED_G242_DATA` -- G242's 89 records contain no per-frame homography (0/89)
and no ordered projected court corners (0/89).** So convexity, projected area, corner ordering, inversion
and fold were **never measured. That is a retention gap, NOT a negative result**, and it is the check with
the strongest mechanism behind it: a homography onto a close-up, a graphic or the wrong hoop end should
plausibly produce a degenerate, inverted or absurdly-sized quad even when the match statistics look
ordinary.

THE QUESTION: **does the SHAPE of the projected court quad separate valid maps from invalid ones, where
every match statistic failed?**

METHOD:
  1. **Re-run G242's 89-frame direct match with its construction UNCHANGED** -- same clip
     `wnba__wnba_01.mp4`, same seed frame 19599, same four labels at scale 1.0,
     `court_points_for_sport("wnba")`, same G222 matcher settings, same stride-2000 sample of 89 frames.
     **This time PERSIST the per-frame homography and the ordered projected court corners.**
  2. **CONTROL: confirm your re-run reproduces G242's per-frame match and inlier counts.** G241 established
     that this geometry reproduces bit-exactly, so **require exact equality and STOP if it differs** -- a
     mismatch would itself be a significant finding. Detector figures are irrelevant here and are not part
     of the control.
  3. **COMPUTE THESE PRE-REGISTERED CHECKS AND REPORT EVERY ONE, whatever the outcome.** They are fixed
     here so that no check can be chosen after seeing results:
     **(a) convexity** of the projected quad; **(b) signed area** and whether the winding inverted
     relative to the seed; **(c) corner ordering** consistency with the seed's ordering; **(d) projected
     area** in pixels, as a ratio to the seed frame's projected area; **(e) aspect ratio** of the quad's
     bounding box; **(f) the fraction of projected corners falling outside the image bounds**; and
     **(g) the condition number of the homography matrix.**
  4. **Join to G244's COMMITTED blind labels** at
     `docs/evidence/tracking/g244_blind_validity_labels_2026-09-04.csv`. **Do not relabel and do not
     revise those labels** -- their value is that they were made blind and committed first.
  5. **Report each check's distribution BY CLASS with the OVERLAP stated explicitly**, in exactly G244's
     format: the INVALID range, how many VALID fall inside it, the VALID range, how many INVALID fall
     inside it. **The overlap is the answer; a difference in medians is not.**
  6. **STATE THE MULTIPLE-COMPARISONS HAZARD IN THE MEMO.** You are testing **seven** checks against
     **89** in-sample points, of which roughly 27 are VALID and 28 INVALID. **With seven checks, one
     looking good by chance is a real possibility and you must say so explicitly** rather than presenting
     the best of seven as a discovery.
  7. **DO NOT FIT A THRESHOLD AND REPORT ITS ACCURACY ON THESE SAME 89 FRAMES.** If a check separates
     cleanly, **say so, give the exact overlap, label it IN-SAMPLE ONLY**, and do NOT propose a production
     gate.
  8. **OUT-OF-SAMPLE CONFIRMATION IS REQUIRED FOR ANY CLEAN SEPARATION.** Take a **fresh sample of frames
     from the same clip that were NOT among the 89** -- for example a different stride offset -- blind
     label them by the same protocol, and report whether the separation holds. **A check that separates
     in-sample and fails out-of-sample is a negative result and must be reported as one.**
  9. **If nothing separates, say so plainly and do not soften it.** Combined with G242 and G244 that would
     mean **no available signal indicates court validity, and every hold claim in this programme is
     render-bound** -- a complete and highly consequential result.
 10. **Do NOT re-open the match-diagnostic question, and do NOT propose a production change.**

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,038 MB of 50,000), STOP and report if it fails.**
**Do NOT re-commit G242's 12.4 MB artifact**; persist only the matrices, corners and derived checks, which
are small. **Do NOT delete the two abandoned partials in `footage_bridge`.** Delete every temporary
artifact and report bytes freed. Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** 89 frames from ONE clip, ONE seed, ONE arena, at a wide
stride, with **one labeller** whose labels came from G244, not from you. Eye-label reliability in this
programme has never cleared 80 pct blind agreement on any of four measured criteria. **CANNOT JUDGE is a
real class of roughly a third of the sample and must not be merged into either other class.** A separation
found here is in-sample until step 8 confirms it, and even then it would be one clip. **Nothing here bears
on automatic calibration, which remains 0/17.** G242 is controlling: a G222 literal match is not a
validity signal.

ACCEPTANCE RULE:
  metric        = the control result stated FIRST; then each of the seven pre-registered checks with its
                  distribution by class and its explicit overlap count; the multiple-comparisons
                  statement; and, for any clean separation, the out-of-sample confirmation result
  before       = G244 measured that no match diagnostic separates the classes and that G241b's cut drops
                 are inside ordinary variation, but could not test quad shape because G242 persisted no
                 matrices or corners
  bar          = NO pass bar. **"No quad-shape check separates them either" is a FULL SUCCESS and the more
                 consequential outcome** -- with G242 and G244 it would establish that no available signal
                 indicates validity and that every hold claim is render-bound. **"Check X separates them,
                 confirmed out of sample" is the other full success** and would give the programme its
                 first automatic validity signal. Do not fit a threshold to these frames, and do not
                 present the best of seven checks as a discovery.
  n            = 89 in-sample frames, 7 pre-registered checks, 1 clip, 1 seed, plus any out-of-sample
                 confirmation sample -- state every denominator in the verdict line
  eye check    = G244's committed blind labels are the ground truth; any out-of-sample labels are new and
                 must follow the same blind protocol
  must not move = every threshold, bar and verdict, G222's matcher settings, the seed construction, the
                  court model, the coordinate contract, the harness, G244's committed labels, `src/` and
                  `domains/` (READ and IMPORT ONLY), the pod daemon and keeper, the corpus, the two
                  abandoned partials
EVIDENCE: docs/evidence/tracking/g247_projected_quad_validity_2026-09-04.md with the control result, the
persisted matrices and corners, all seven checks with per-class distributions and overlaps, the
multiple-comparisons statement, any out-of-sample confirmation, every disk-guard probe, bytes freed, and a
NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
