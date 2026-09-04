GAP G253 | sport wnba then basketball (amateur) | worktree a6 | log g253_line_and_conic_calibration
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO existing label file and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G252 may be running on a5; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and say in your memo that you checked and when you began. EXCLUDE
YOUR OWN PROCESS AND YOUR OWN CHECKER COMMAND** -- a G243c dispatch refused on a self-match.
The `track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and
`foundry_runner` are PERMANENT residents and the load floor.

**READ THE LANDED G233d, G249, G250 AND G251 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- POINT-BASED CALIBRATION IS CLOSED FOR AMATEUR FOOTAGE, BUT THE GEOMETRY MAY STILL
BE THERE.**
Five amateur sources have now been measured or screened and **not one supplies four named, unoccluded,
non-collinear painted intersections in a single frame.** G249: both near court corners are outside the
image in **61/61** frames. G250: **zero same-frame four-point candidates** across 20 inventoried features;
the largest usable set is **three points, all collinear on the centre line.** G251: **4 of 4** further
sources rejected -- three because foreground crowd, bench or scorer table hides the camera-side boundary,
one because a multi-use gym's overlapping markings made identity ambiguous.

**The recurring cause is structural: amateur cameras sit on the near sideline, so near-side geometry is
systematically hidden by crowd, benches and cropping.** More sources of that shape will not help.

**BUT A HOMOGRAPHY DOES NOT REQUIRE POINT CORRESPONDENCES.** It has 8 degrees of freedom. **A line
correspondence contributes 2 constraints; a conic correspondence contributes 5.** G250 found the amateur
clip reliably shows **the far sideline, the centre line, and the centre circle**. That is
**2 lines + 1 conic = 9 constraints for 8 unknowns** -- **sufficient in principle, from exactly the
geometry that is available**, even though only three collinear POINTS exist.

**That arithmetic is a hypothesis, not a result. Degenerate configurations are still possible** -- two
image-parallel lines, or a poorly observed conic -- **and this row must check for that rather than assume
it.**

THE QUESTION: **can a usable court homography be recovered from LINE and CONIC correspondences where four
point correspondences do not exist?**

METHOD -- THE POSITIVE CONTROL COMES FIRST AND IS BINDING:
  1. **PROVE THE METHOD ON FOOTAGE WHERE THE ANSWER IS ALREADY KNOWN, BEFORE TOUCHING AMATEUR FOOTAGE.**
     Use G233d's validated WNBA seed: `wnba__wnba_01.mp4`, frame **19599**, scale 1.0, which PASSED its
     gate and whose 4-point homography is published in its memo. **Fit a homography there from LINES ONLY**
     -- baseline, sidelines, lane boundaries, free-throw line, and the three-point arc as available; note
     that **the centre circle is OUTSIDE that hoop-end crop**, so the conic is not available in the
     control and the control is lines-only.
  2. **Compare the line-fitted homography against G233d's published 4-point matrix**, and **render both
     on the seed frame.** Report the difference as a projected-court discrepancy in pixels, not as a raw
     matrix difference, which is not interpretable.
  3. **IF THE CONTROL FAILS -- if a lines-only fit cannot reproduce a known-good calibration on clean
     broadcast footage -- STOP AND REPORT THAT.** It would mean the method does not work and there is no
     point applying it to harder footage. **That is a full success and the cheapest possible negative.**
  4. **ONLY ON A PASSING CONTROL, apply it to the amateur clip**
     `basketball__amateur_jh3fnwMi7dM.mp4` (24,523,745 bytes, SHA-256
     `773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea`, 1280x720, 3,601 frames), using
     **the far sideline, the centre line and the centre circle** on one of G250's best frames -- 480, 540,
     600 or 2220. **Verify the frame and identity exactly as G243c required: commit a zoomed crop for
     every fitted line and for the conic, stating what is at it, BEFORE any fit.**
  5. **CHECK FOR DEGENERACY EXPLICITLY BEFORE TRUSTING ANY FIT.** Report whether the two lines are
     near-parallel in the image, how much of the conic's circumference is actually observed, and the
     condition number of the system you solve. **A degenerate configuration must be reported as such, not
     fitted and presented.**
  6. **HARD GATE, BOTH CASES: render the projected court and report PASS or FAIL in ONE LINE, before
     anything else. Judge on INDEPENDENT geometry that was NOT used in the fit** -- if you fit the
     sideline and centre line, judge on the arc and the painted-end geometry. **Never judge on a fitted
     element.** This is the same rule that made G233d's PASS meaningful.
  7. **FROM G242, G244, G247 AND G248: match counts, inliers, ratio, RMS and quad shape do NOT establish
     that a court is correct -- ONLY THE RENDERS DO.** Say so in the memo. **A line/conic fit will also
     have a residual; it is not evidence either.**
  8. **Do NOT tune the fit after seeing a gate, do NOT relabel, do NOT add a `court_points_for_sport` key,
     and do NOT propose a production change.**

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,093 MB of 50,000), STOP and report if it fails.**
Decode to memory, keep renders and crops small, delete every temporary artifact and report bytes freed.
**Do NOT delete any corpus source or the two abandoned partials in `footage_bridge`.**

**HONEST LIMITATIONS to state, not discover:** one control frame, one amateur frame, one labeller. **This
CONSUMES HAND-LABELLED GEOMETRY and is not automatic calibration**, which remains 0/17 -- fitting lines by
hand is no more automatic than fitting points by hand. Eye-label reliability in this programme has never
cleared 80 pct blind agreement on any of four measured criteria, and **G246 showed repeatable labels can
be uniformly wrong**. The amateur court model is assumed, not measured. **A passing control proves the
solver works, not that the amateur fit is right**, and a passing amateur gate is one frame, one clip.
**Plausibility is necessary, never sufficient.**

ACCEPTANCE RULE:
  metric        = the control result stated FIRST -- the lines-only fit versus G233d's published matrix as
                  a projected-court pixel discrepancy, with both renders; then, only on a passing control,
                  the amateur degeneracy check (line parallelism, observed conic fraction, condition
                  number), the identity crops, and the amateur gate verdict in one line
  before       = five amateur sources supply no four-point set; G250 found only three collinear points,
                 while the far sideline, centre line and centre circle are reliably present
  bar          = NO pass bar. **"The lines-only control fails to reproduce a known-good calibration" is a
                 FULL SUCCESS and the cheapest negative available** -- it closes the method before it
                 costs anything. **"The control passes but the amateur configuration is degenerate" is a
                 second full success** and would say the geometry is present but not usable. **"Both pass"
                 would be the first calibration of non-broadcast footage this programme has produced.**
                 Do not tune to reach any of them.
  n            = 1 control frame, 1 amateur frame, 1 labeller -- state this in the verdict line
  eye check    = the control comparison renders and the amateur gate render ARE the deliverable
  must not move = every threshold, bar and verdict, `court_points_for_sport`, the court models, the
                  coordinate contract, the harness, G222's matcher settings, existing label files, G233d's
                  published seed, `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and keeper,
                  the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g253_line_and_conic_calibration_2026-09-04.md with the control fit and its
pixel discrepancy against G233d, both control renders, any amateur identity crops, the degeneracy check,
the amateur gate verdict and render, every disk-guard probe, bytes freed, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
