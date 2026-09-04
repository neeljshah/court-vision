GAP G243 | sport basketball (amateur) | worktree a6 | log g243_seeded_calibration_amateur
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. Build in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G241 on a5 and G242 on a6; N=2 is optimal per G200/G216, so **do not
start until one of them has finished**). **Check first, do NOT interrupt a running row, and say in your
memo that you checked and when you began.** The `track_daemon`, `keep_track_daemon.sh`, `adapter_run`
jobs, `inplay_capture_runner` and `foundry_runner` are PERMANENT residents and the load floor.

**WHY THIS ROW EXISTS -- IT IS THE FIRST TEST OF THE STATED GOAL: ANY FOOTAGE.**
G233d proved seeded calibration works on **broadcast WNBA**: one hand label at frame 19599 of
`wnba__wnba_01.mp4` passed its gate on independent geometry and held 1,200 frames at 0.30-0.70 px RMS.
**Every calibration row this programme has ever run was on professional broadcast footage.** The goal is
tracking on arbitrary footage -- high-school and amateur video included.

`data/footage_corpus/g220c__jh3fnwMi7dM.mp4` is **amateur fixed-camera high-school basketball**, 1920x1080,
28,865 frames, 960.1 s. G239 measured its DETECTION behaviour (median 20 boxes/frame vs WNBA's 11, median
track length 500 vs 205, ~50 fewer ids, and a band-7 spike of 25.5 pct consistent with bench and crowd).
**Nothing has ever tried to CALIBRATE it.**

THE QUESTION: **does one hand-labelled seed produce a court on amateur fixed-camera footage, and how far
does it hold?**

**A FIXED CAMERA IS THE EASY CASE AND THAT IS THE POINT.** No pan, no cuts, no zoom -- the failure modes
that limit broadcast footage are absent, so if the seeded method cannot work here it cannot work on
amateur footage at all. A NEGATIVE here is therefore MORE informative than a positive.

**THE COURT MODEL TRAP -- READ THIS BEFORE FITTING ANYTHING.** A wrong court model is what cost G233b and
G233c. **A high-school court is 84 x 50 ft with a 12-ft lane. A WNBA/NBA court is 94 x 50 ft with a 16-ft
lane.** Do NOT reuse G233d's `court_points_for_sport("wnba")` points here.
  - **Inspect `court_points_for_sport` and report EXACTLY which sport keys exist and what dimensions each
    returns.** If no high-school model exists, **say so and state plainly which key you used and what it
    assumes** -- do not silently substitute one.
  - **The 84-vs-94 ft difference changes the in-court denominator**, so an in-court fraction computed
    against a 94-ft court would be wrong here. State the court extent you scored against.
  - **First confirm from the footage which court this actually is.** Do not assume high-school dimensions
    from the clip's provenance; say what you observed.

METHOD:
  1. **Pick a seed frame and justify it** -- a frame with clearly visible painted geometry. Verify your
     decode is frame-exact with a `select=eq(n,N)` filter (`ffmpeg -ss` before `-i` is NOT frame-exact)
     and state the index and the method.
  2. **THE LABEL IS NEW AND ITS REPEATABILITY MUST BE MEASURED INSIDE THIS ROW.** Unlike G233d you have
     no G196-validated label to inherit. **Label the four court points THREE times independently, each
     time from a fresh view of the frame, and report the per-point spread (median and max px) against
     G140's p90 repeatability of 11.39 px.** Fit from one labelling, name which, and **report how much
     the gate verdict and the RMS would move under the other two.** A row resting on an eye label must
     measure that label's agreement, not assume it.
  3. **HARD GATE, as in G233d: render the projected court on the seed frame and report PASS or FAIL in
     ONE LINE BEFORE ANYTHING ELSE.** On FAIL, STOP -- no propagation, no in-court fraction, no
     labels-per-hour. **The four labelled points are FITTED INPUTS and are NOT evidence. Judge on
     INDEPENDENT geometry -- the three-point arc, the sidelines, the centre circle.**
  4. Only on a PASS: **propagate DIRECT-to-seed with G222's landed harness unchanged** -- direct, never
     chained; chaining is what produced G215's misleading ~50-frame ceiling. Report matches, inliers,
     inlier ratio and RMS versus distance at regular intervals so this row is commensurable with G222,
     G233d and G241.
  5. **Run far.** A fixed camera plausibly holds the whole clip; **28,865 frames is the natural bound.**
     State your target and why, and report whether it failed or reached the bound.
  6. Project detected feet to court feet and report the **in-court fraction versus distance** using
     G230's method and vocabulary, **against the court extent you named in the trap section above.**
  7. **Renders are the deliverable**: several distances including the furthest. Commit every render.
  8. **Compare to G233d explicitly** -- horizon, inliers, RMS, in-court fraction -- and say whether
     amateur fixed-camera footage is easier or harder than broadcast, with the numbers side by side.
  9. **Do NOT tune the seed, adjust a label after seeing the gate, or change the matcher.** Relabelling
     until the gate passes would invalidate the row entirely.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~32,783 MB of 50,000), STOP and report if it fails.**
A long run decodes many frames -- **decode to memory, keep renders small, delete every temporary artifact
and report bytes freed.** Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** one clip, one seed, one camera, one labeller. **This
CONSUMES A HAND LABEL and is not automatic calibration**, which remains 0/17. **Plausibility is necessary,
never sufficient.** The in-court fraction includes officials, bench and spectators, and **this clip is
worse for that than broadcast** -- G239's band-7 spike of 25.5 pct and G225's frame of 19 raw boxes
yielding 2 visibly on-court players both apply. G239's amateur-vs-broadcast detection comparison was
CONFOUNDED and must not be quoted here as a clean result. Direct-reference drift at distance 0 is 0.0 BY
CONSTRUCTION and is not evidence.

ACCEPTANCE RULE:
  metric        = the seed-render PASS/FAIL stated FIRST; the three-labelling repeatability spread in px
                  and its effect on the verdict; then only on PASS, inliers/RMS versus distance to failure
                  or to the 28,865-frame bound, the in-court fraction against a NAMED court extent, the
                  renders, and a side-by-side comparison with G233d
  before       = seeded calibration is proven on ONE professional broadcast clip and has never been tried
                 on amateur footage; the stated goal is arbitrary footage
  bar          = NO pass bar. **A FAIL is a FULL SUCCESS and is the more informative outcome** -- a fixed
                 camera is the easy case, so a failure here bounds the whole amateur-footage ambition and
                 should be reported as decisively as a pass. **A PASS would be the first calibration of
                 non-broadcast footage this programme has produced.** Do not relabel to reach a verdict.
  n            = 1 clip, 1 seed, 3 independent labellings, one span -- state this denominator in the
                 verdict line
  eye check    = the seed render is the GATE; the distance renders are the deliverable
  must not move = every threshold, bar and verdict, the court model, the coordinate contract, the
                  harness, G222's matcher settings, existing label files, `src/` and `domains/` (READ and
                  IMPORT ONLY), the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g243_seeded_calibration_amateur_2026-09-04.md with the court-model
finding and the key you used, the seed frame and decode method, all three labellings and their spread, the
gate result stated FIRST, any propagation and in-court results with the named court extent, all renders,
the G233d comparison, every disk-guard probe, bytes freed, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
