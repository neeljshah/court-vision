GAP G266 | sport wnba then ncaa_basketball | worktree a5 | log g266_multiframe_constraint_accumulation
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file, NO court-model key and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G260 may be running on a6; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G222, G233d, G253, G257, G264 AND G265 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- EVERY CLOSURE TONIGHT HAS THE SAME SHAPE, AND IT MAY BE THE WRONG QUESTION.**
Four footage classes were screened and only the WNBA clip yields a fittable frame:

| footage | finding |
|---|---|
| NCAA broadcast | 0/300 with a conic (centre logo); **0/300 with four lines, 1/300 with three** |
| amateur basketball | 0 usable four-point sets; largest 3 collinear |
| broadcast soccer | 0/1,195 rectangles; 0 four-edge boxes; 0/1,195 four-feature |

**Every one of those asks whether a SINGLE FRAME contains four primitives. But a broadcast camera PANS,
and different frames of the same shot show different geometry.** G265's near miss is the tell: frame
129465 has far sideline, centre line and far-end baseline, and is short only the free-throw line -- **which
other frames in the same shot may well show.**

**AND THIS PROGRAMME HAS ALREADY VALIDATED THE MISSING PIECE.** G222 and G233d established that
**direct-to-seed matching WITHIN a shot is excellent** -- 452-1,863 matches, 421-1,848 inliers, RMS
0.299-0.703 px, holding 1,200 frames, and G241b confirmed it reproduces bit-exactly. **So frames within a
shot can be related to each other with high confidence.** If frame A contributes two lines and frame B
contributes two more, **their constraints can be mapped into ONE reference frame and fitted jointly.**

THE QUESTION: **can a court be calibrated from geometry accumulated ACROSS frames of one camera shot,
where no single frame carries enough?**

METHOD -- POSITIVE CONTROL FIRST, AND IT IS BINDING:
  1. **PROVE IT WHERE THE ANSWER IS KNOWN.** On `wnba__wnba_01.mp4` around G233d's validated seed frame
     **19599**, take a set of frames within that shot, relate them with **G222's landed matcher
     unchanged**, and **fit the court from constraints accumulated across them.** Compare the result to
     **G233d's published map**, reporting a projected-court pixel discrepancy **over shared in-frame
     sample points, with that denominator named** -- G253's control reported 2.849 px median over 231 of
     634, and the G253-VERIFIER-DENOMINATOR row exists because the denominator was omitted.
  2. **IF THE CONTROL FAILS, STOP AND REPORT.** Accumulated constraints inherit inter-frame matching
     error, and **if that error swamps the gain, the idea is dead cheaply.** That is a full success.
  3. **ONLY ON A PASSING CONTROL, apply it to the NCAA clip.** Start from G265's named near miss, **frame
     129465** (far sideline, centre line, far-end baseline present; free-throw line missing), and
     accumulate over its shot. **Reuse G264's committed 300-frame survey to locate the shot; do not
     re-survey.**
  4. **REPORT THE ACCUMULATED CONSTRAINT COUNT AND WHERE EACH CAME FROM** -- which frame contributed which
     primitive, and the inter-frame match quality (matches, inliers, RMS) used to transport it. **A
     constraint transported through a weak match is a weak constraint; say so per constraint.**
  5. **VERIFY IDENTITY BEFORE ANY FIT (G246's protocol): commit a zoomed crop for every contributed
     primitive in ITS OWN frame**, stating what is at it and what portion you observed. **Transporting a
     misidentified feature makes it no more correct.**
  6. **CHECK DEGENERACY on the accumulated set**: image angles, near-concurrency, condition number, and
     **how far apart in the shot the contributing frames are** -- a wide baseline helps geometry and hurts
     match quality, so report both.
  7. **THE GATE IS A BLIND LADDER** (G257's definition, about 5/10/20/40/100 px), randomised, with order
     and PASS/FAIL/CANNOT JUDGE verdicts **committed BEFORE un-blinding**, judged only on INDEPENDENT
     geometry the fit did not use. **The gate passes only if the candidate is PASS AND perturbations at
     and above a stated magnitude are correctly FAIL.** Report the discrimination threshold beside G257's
     20 px.
  8. **On a gate pass, measure withheld-geometry offsets with G252's method** beside G252's WNBA figures
     (median 5 px, p90 19 px).
  9. **The fit residual is NOT evidence** (G242/G244/G247/G248); **G254 showed an optimiser can improve its
     own objective while moving the projection off the markings**; **per G257 a gate pass BOUNDS error, it
     does not certify correctness.**
 10. **Do NOT tune, relabel after a verdict, add a court key, or propose a production change. A FAIL is a
     full success.**

**DISK GUARD, CORRECTED SCOPE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** -- the scope
the 50 GB quota is enforced on, last measured **36,419 MB**, about 13.6 GB free. **`dd conv=fsync` probe
before writing, STOP and report if it fails.** Stream decodes; never write a full decode to disk. **Do NOT
delete any corpus source or the two abandoned partials in the bridge directory.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one shot per clip, one labeller. **Accumulation assumes the
frames belong to ONE continuous shot** -- G241b showed a cut collapses matching abruptly (310 to 182
matches in one frame), so **verify no cut lies between your contributing frames and say how.** Constraints
transported between frames inherit that transport's error, which is **not** the same as observing them
directly. **This CONSUMES manual geometry and is NOT automatic calibration**, which remains 0/17.
Eye-label reliability here has never cleared 80 pct blind agreement on four criteria, and **G246 showed
repeatable labels can be uniformly wrong.**

ACCEPTANCE RULE:
  metric        = the control's projected-court discrepancy against G233d's published map with its named
                  shared-point denominator; then only on a passing control, the accumulated constraint
                  inventory with per-constraint transport quality, identity crops, degeneracy diagnostics,
                  the committed blind ladder and discrimination threshold, the combined gate verdict
                  stated FIRST, and any withheld-geometry offsets
  before       = four footage classes yield no single frame with four primitives, while within-shot
                 matching is measured as excellent and reproduces bit-exactly
  bar          = NO pass bar. **"The control fails, so accumulation cannot beat its own transport error"
                 is a FULL SUCCESS and closes the idea cheaply.** **A passing control plus an NCAA gate
                 pass would be the first calibration of a second arena and the first evidence that the
                 single-frame limitation is not binding.** Do not tune to reach either.
  n            = 1 control shot, 1 NCAA shot if reached, 1 labeller -- name every denominator in the
                 verdict line
  eye check    = the blind ladder IS the gate
  must not move = every threshold, bar and verdict, G222's matcher settings, G233d's published seed and
                  labels, `court_points_for_sport`, the coordinate contract, G253's harness, G252's method,
                  G257's displacement definition, G264's committed survey, `src/` and `domains/` (READ and
                  IMPORT ONLY), the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g266_multiframe_constraint_accumulation_2026-09-04.md with the control
result and its denominator, the cut check, the accumulated constraint inventory with transport quality,
every identity crop, degeneracy diagnostics, the committed blind ladder with ordering statement, the
discrimination threshold, the gate verdict stated FIRST, any offsets, every disk-guard probe with the
`du -sm /workspace` figure, bytes freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE
SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
