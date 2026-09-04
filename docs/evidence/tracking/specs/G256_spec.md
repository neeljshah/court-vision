GAP G256 | sport soccer | worktree a5 | log g256_soccer_line_conic_calibration
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file, NO coordinate contract and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G255 may be running on a6; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and say in your memo that you checked and when you began. EXCLUDE
YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT** -- G252, G253 and G254 all did this correctly.

**READ THE LANDED G253 MEMO FIRST -- this row reuses its method unchanged on a different sport.**

**WHY THIS ROW EXISTS -- SOCCER IS THE BEST POSSIBLE CASE FOR THE METHOD THAT JUST WORKED, AND IT IS
CURRENTLY AT ZERO.**
G253 calibrated amateur basketball from **lines and a conic** where no four identifiable points existed: a
homography has 8 degrees of freedom, **a line correspondence gives 2 constraints and a conic gives 5.** Its
WNBA positive control reproduced G233d's published map to 2.849 px median over 231 of 634 shared in-frame
points.

**Soccer is where that method should pay off most, and where the programme has nothing.** Soccer output is
`image_px` only, it is excluded from the coordinate contract by
`adapter_run.py`'s `IMAGE_SPACE` set, and the landed note records **0 accepted homographies over 200
reference frames** -- the "131 of 132 accepted" figure it used to report was a stale cached homography.
**A soccer pitch is dense with exactly the geometry this method consumes:** touchlines, the halfway line,
the centre circle, penalty areas and goal areas.

**THE DIMENSION TRAP, AND IT IS WORSE THAN BASKETBALL'S -- READ BEFORE FITTING.**
**A soccer pitch is NOT a fixed size.** The Laws of the Game permit roughly **100-110 m length and 64-75 m
width**, and it varies by stadium. **So touchline length and pitch width are NOT known quantities and must
not be used as fitted constraints.** What IS standard and may be used:
  - **centre circle radius 9.15 m**
  - **penalty area 16.5 m deep and 40.32 m wide**
  - **goal area 5.5 m deep and 18.32 m wide**
  - **penalty mark 11 m from the goal line**
**Fit ONLY from standard-dimension geometry. Report explicitly which features you used and what dimension
you assumed for each**, and state that any non-standard assumption invalidates the result. **This is the
same class of error that cost G243b and G233b: a wrong model silently corrupts a fit that still has zero
residual.**

THE QUESTION: **can the line-and-conic method produce a soccer pitch homography where four-point methods
have produced none?**

METHOD:
  1. **Source:** `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4`. **`stat`
     it and report bytes, SHA-256, resolution, frame count, fps and duration before anything else** -- G243
     died for want of exactly that check.
  2. **Select a frame by whether its features are visible and UNOCCLUDED**, and say how you surveyed.
     **A frame showing one penalty area plus the halfway line and centre circle is the ideal shape.**
  3. **VERIFY IDENTITY BEFORE ANY FIT, using G246's protocol: commit a zoomed crop for every fitted line
     and for the conic, stating in words what is at it.** G246 found all eight of G243b's labelled pixels
     were the wrong features, and that no fitted number can detect it.
  4. **Fit with G253's landed harness UNCHANGED**, from standard-dimension features only. **Report the
     degeneracy diagnostics G253 reported: the image-space angle between fitted lines, the observed
     fraction of the conic's circumference, and the condition number.** A degenerate configuration must be
     reported, not fitted and presented.
  5. **HARD GATE: render and report PASS or FAIL in ONE LINE before anything else, judged on INDEPENDENT
     geometry the fit did NOT use** -- if you fit the centre circle and halfway line, judge on the penalty
     area and goal area. **Never judge on a fitted element.** **The fit residual is NOT evidence**: G242,
     G244, G247 and G248 established that no fitted or match statistic indicates correctness, and G254
     showed an optimiser can improve its own objective while moving the projection off the markings.
  6. **On a PASS, measure the accuracy in pixels with G252's method on WITHHELD geometry only**, with its
     search radius and censoring statement, and report median, p90, max and the no-candidate count
     **beside G252's WNBA figures (median 5 px, p90 19 px)** so the sports are comparable.
  7. **Do NOT change `IMAGE_SPACE`, the coordinate contract, or any production module. Do NOT propose a
     production change.** This row measures whether the geometry is recoverable; wiring it anywhere is a
     separate decision that is not yours.
  8. **A FAIL is a full success.** Say plainly which feature or configuration defeated it.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,116 MB of 50,000), STOP and report if it fails.**
Stream the decode; never write a full decode to disk. **Do NOT delete any corpus source or the two
abandoned partials in `footage_bridge`.** Delete every temporary artifact and report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one frame, one labeller. **This CONSUMES manual
geometry and is NOT automatic calibration**, which remains 0/17 -- hand-fitting lines is no more automatic
than hand-fitting points. **Pitch length and width are unknown by rule**, so any claim depending on them is
unsupported. Eye-label reliability in this programme has never cleared 80 pct blind agreement on any of
four measured criteria, and **G246 showed repeatable labels can be uniformly wrong**. A single-frame PASS
says nothing about propagation, coverage, detection or tracking quality on this clip, and nothing about
the coordinate contract, which this row must not touch.

ACCEPTANCE RULE:
  metric        = the source identity check; the features used with their assumed standard dimensions; the
                  identity crops; the degeneracy diagnostics; the gate verdict stated FIRST in one line;
                  and on a PASS the withheld-geometry pixel offsets beside G252's WNBA figures
  before       = soccer is `image_px` only, excluded from the coordinate contract, with 0 accepted
                 homographies over 200 reference frames; G253 has just shown lines and a conic can
                 calibrate where four points do not exist
  bar          = NO pass bar. **A PASS would be the first soccer pitch coordinates this programme has
                 produced, on the sport where four-point methods have produced nothing.** **A FAIL is an
                 equally full success** if it names the feature or configuration that defeated it. Do not
                 tune, do not relabel after the gate, and do not assume a non-standard dimension to make
                 something fit.
  n            = 1 clip, 1 frame, 1 labeller -- state this in the verdict line
  eye check    = the identity crops gate the inputs; the withheld-geometry render is the GATE
  must not move = every threshold, bar and verdict, `IMAGE_SPACE`, the coordinate contract, G253's
                  harness, the court/pitch models, existing label files, `src/` and `domains/` (READ and
                  IMPORT ONLY), the pod daemon and keeper, the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g256_soccer_line_conic_calibration_2026-09-04.md with the source identity,
the survey and frame choice, every identity crop, the features and assumed dimensions, the degeneracy
diagnostics, the gate verdict stated FIRST, any pixel offsets, every disk-guard probe, bytes freed, and a
NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting
(A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
