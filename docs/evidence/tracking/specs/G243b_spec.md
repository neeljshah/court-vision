GAP G243b | sport basketball (amateur) | worktree a6 | log g243b_seeded_calibration_amateur
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. Build in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G241b may still be running on a5; N=2 is optimal per G200/G216).
**Check first, do NOT interrupt a running row, and say in your memo that you checked and when you began**
-- G243 and G245 both did this correctly. The `track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs,
`inplay_capture_runner` and `foundry_runner` are PERMANENT residents and the load floor.

**READ `docs/evidence/tracking/specs/G243_spec.md` AND `G245_spec.md` AND THEIR MEMOS FIRST.**
G243 was FALSIFIED because I named a clip that existed nowhere -- my error, landed as
G243-PREMISE-CORRECTION. **G245 has now acquired real amateur footage and verified it is suitable.** This
row is G243 re-issued against material that exists.

**THE SOURCE, AS MEASURED BY G245 -- VERIFY IT YOURSELF BEFORE BUILDING ANYTHING:**
  - Path: `/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4`
  - **24,523,745 bytes; SHA-256 `773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea`**
  - **1280x720 -- NOT 1920x1080. 3,601 frames -- NOT 28,865.** 30 fps, 120.100000 s.
  - High-school gym, coaches camera: **wide, near-fixed, modest pan, no hard cuts or zooms in the
    section.** Painted baseline, sideline, lane and free-throw geometry visible; **three-point arcs at
    BOTH ends; centre circle visible in wide midcourt views.**
  - **`stat` the file and confirm the SHA-256 and `ffprobe` identity before you fit anything.** G243 died
    for want of exactly this check.

THE QUESTION: **does one hand-labelled seed produce a court on amateur fixed-camera footage, and how far
does it hold?**

**A NEAR-FIXED CAMERA IS THE EASY CASE AND THAT IS THE POINT.** A FAIL here is MORE informative than a
pass and is a FULL SUCCESS: it would bound the whole amateur-footage ambition on measurement.

**THE COURT MODEL TRAP.** A high-school court is **84 x 50 ft with a 12-ft lane**; a WNBA court is
**94 x 50 ft with a 16-ft lane**. Do NOT reuse G233d's `court_points_for_sport("wnba")`.
  - **Inspect `court_points_for_sport`, report EXACTLY which sport keys exist and what each returns**, and
    state plainly which you used and what it assumes.
  - **The 84-vs-94 ft difference changes the in-court denominator.** State the court extent you scored
    against.
  - **Confirm from the FOOTAGE which court this is.** Do not assume from provenance.

**RESOLUTION CAVEAT:** at 1280x720 there are fewer pixels per foot than G233d's 1920x1080, so **a pixel
error here is a larger real-world error.** Do not compare px figures with G233d without saying so.

METHOD:
  1. **Pick a seed frame and justify it** -- a wide frame with the most painted geometry visible. Verify
     the decode is frame-exact with a `select=eq(n,N)` filter (`ffmpeg -ss` before `-i` is NOT
     frame-exact); state the index and method.
  2. **THE LABEL IS NEW, SO MEASURE ITS REPEATABILITY INSIDE THIS ROW.** Label **three times
     independently**, each from a fresh view. Report per-point spread (median and max px) against G140's
     p90 of 11.39 px, fit from ONE labelling, name it, and **report how much each gate verdict and RMS
     move under the other two.**
  3. **TWO LABEL SETS, BOTH FITTED FROM THE SAME FRAME -- THIS IS THE NEW MEASUREMENT.**
     **(a) CLUSTERED:** the four paint corners, matching G233d's construction, for comparability.
     **(b) SPREAD:** four widely separated court points that this wide view makes available for the first
     time and the WNBA hoop-end crop never did.
     **Report the gate and the RMS for BOTH.** The programme has never tested whether label geometry
     drives calibration quality, and a wide amateur view is the first chance to. **Do not tune either set
     after seeing its gate.**
  4. **HARD GATE: render the projected court on the seed frame for each set and report PASS or FAIL in ONE
     LINE EACH, BEFORE ANYTHING ELSE.** If both FAIL, STOP -- no propagation, no in-court fraction, no
     labels-per-hour. **The labelled points are FITTED INPUTS and are NOT evidence.** **Judge on
     INDEPENDENT geometry -- the three-point arc, the sidelines, and here the CENTRE CIRCLE, which is
     visible in this footage and was not in G233d's crop.** That makes this a stronger eye check than any
     the programme has run.
  5. On a PASS, propagate **DIRECT-to-seed with G222's landed harness unchanged** -- direct, never
     chained; chaining produced G215's misleading ~50-frame ceiling. Report matched features, inliers,
     inlier ratio and RMS versus distance.
  6. **CRITICAL, FROM G242:** G222's acceptance rule **accepted 89 of 89 whole-game frames including
     replays, graphics and the wrong hoop end**. **So inliers, inlier ratio and RMS do NOT establish that
     a court is correct. ONLY THE RENDERS DO.** Never report a hold based on acceptance. Say this in the
     memo.
  7. **The bound is 3,601 frames** -- the whole clip. State whether it failed or reached the bound.
  8. Project detected feet to court feet and report the **in-court fraction versus distance** using G230's
     method and vocabulary, **against the court extent you named**. Report it to **three decimals**, and
     say it is one draw from a non-deterministic detector (G241 found 808 of 1,201 detector records
     differed on an exact re-run while geometry reproduced bit-exactly).
  9. **Renders are the deliverable**: several distances including the furthest. Commit every render.
 10. **Compare to G233d explicitly** -- gate, horizon, inliers, RMS, in-court fraction -- and say whether
     amateur near-fixed footage is easier or harder than broadcast, with the numbers side by side and the
     resolution caveat stated.
 11. **Do NOT tune a seed, adjust a label after seeing a gate, or change the matcher.**

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,018 MB of 50,000), STOP and report if it fails.**
**Do NOT delete the two abandoned partials in `footage_bridge` (4,999,500,276 and 2,490,710,544 bytes) --
that decision is not yours.** Decode to memory, keep renders small, delete every temporary artifact and
report bytes freed. Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** one clip, one seed, one camera, one labeller, and only
**120.1 seconds** of footage. **This CONSUMES A HAND LABEL and is not automatic calibration**, which
remains 0/17. **Plausibility is necessary, never sufficient.** The in-court fraction includes officials,
bench and spectators -- G225 found one frame with 19 raw boxes yielding 2 visibly on-court players.
Eye-label reliability in this programme has never cleared 80 pct blind agreement on any of four measured
criteria. G245's suitability judgement was single-labeller. "Amateur" is a source description, not a
controlled condition.

ACCEPTANCE RULE:
  metric        = the source identity check; the two seed-render PASS/FAIL verdicts stated FIRST, one line
                  each; the three-labelling repeatability spread and its effect on each verdict; then on
                  any PASS, inliers/RMS versus distance to failure or to the 3,601-frame bound, the
                  in-court fraction to three decimals against a NAMED court extent, the renders, and a
                  side-by-side comparison with G233d carrying the resolution caveat
  before       = seeded calibration is proven on ONE professional broadcast clip at 1920x1080; nothing has
                 ever been calibrated on amateur footage, and until G245 the corpus contained none
  bar          = NO pass bar. **A FAIL on both label sets is a FULL SUCCESS and the more informative
                 outcome.** **A PASS would be the first calibration of non-broadcast footage this
                 programme has produced.** **A SPLIT -- one label set passing and the other failing -- is
                 the most useful outcome of all**, because it would identify label geometry as a lever.
                 Do not relabel to reach a verdict.
  n            = 1 clip, 1 seed, 2 label sets, 3 independent labellings -- state this denominator in the
                 verdict line
  eye check    = the seed renders are the GATE; the distance renders are the deliverable
  must not move = every threshold, bar and verdict, the court model, the coordinate contract, the harness,
                  G222's matcher settings, existing label files, `src/` and `domains/` (READ and IMPORT
                  ONLY), the pod daemon and keeper, the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g243b_seeded_calibration_amateur_2026-09-04.md with the source identity
check, the court-model finding, the seed frame and decode method, all three labellings and their spread,
both gate verdicts stated FIRST, any propagation and in-court results, all renders, the G233d comparison,
every disk-guard probe, bytes freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME
COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
