GAP G255 | sport wnba and basketball (amateur) | worktree a6 | log g255_amateur_gate_independent_check
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file, NO fitted map and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G254 may be running on a5; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and say in your memo that you checked and when you began. EXCLUDE
YOUR OWN PROCESS AND YOUR OWN CHECKER COMMAND AND ITS PARENT** -- G252 and G253 both did this correctly.

**READ THE LANDED G252 AND G253 MEMOS, AND THE G253-VERIFIER-DENOMINATOR LEDGER ROW, FIRST.**

**WHY THIS ROW EXISTS -- THE PROGRAMME'S BIGGEST CLAIM RESTS ON ONE PERSON LOOKING ONCE.**
G253 produced **the first calibration of non-broadcast footage this programme has ever made**: on amateur
frame 540, fitting only the far sideline, centre line and centre circle, the **withheld** left-end
three-point arc and painted-end geometry were judged to agree. Its degeneracy diagnostics are clean --
line angle 87.600 degrees, observed conic fraction 0.58, Jacobian condition 40.369.

**But that PASS is ONE labeller's eye judgement on ONE render, and unlike the WNBA control it has no
objective anchor.** The control could be checked numerically against G233d's published map (2.849 px
median over **231 of 634** shared in-frame points -- see the verifier row). **The amateur gate cannot be
checked that way, because there is no known-good amateur map to compare against.**

**This programme's own discipline is that eye-label reliability has never cleared 80 pct blind agreement
on any of four measured criteria, and G246 showed repeatable labels can be uniformly wrong.** A headline
result carried by a single unreplicated eye judgement is exactly the thing that discipline exists to
catch. **A second orchestrator look at the render was uncertain about whether the projected arc sits on
the painted arc** -- that is not a finding, it is a reason to measure.

THE QUESTION: **does G253's amateur PASS survive an independent blind judgement, and what is the fit's
accuracy in PIXELS on geometry it did not use?**

METHOD:
  1. **PART ONE -- BLIND RE-JUDGEMENT, BEFORE READING G253's VERDICTS.** Open
     `g253_line_and_conic_calibration_2026-09-04_artifact/amateur_line_conic_render.jpg` and
     `control_lines_only_render.jpg` and record **PASS / FAIL / CANNOT JUDGE** for each, judging **only
     the withheld geometry** -- for the amateur fit that is the left-end three-point arc and painted-end
     markings; **the far sideline, centre line and centre circle are FITTED INPUTS and are not
     evidence.** **Write and commit your verdicts BEFORE reading G253's memo verdicts**, and say in the
     memo that you did it in that order. Then report agreement with G253.
  2. **NOTE THE CONTROL RENDER'S KNOWN READING HAZARD:** it projects a full 94x50 ft court model onto a
     hoop-end view, so **most of its geometry lands off-court by construction** and an unaided glance can
     read as misaligned. **Judge only near-end withheld geometry there, and say so.**
  3. **PART TWO -- CONVERT THE EYE JUDGEMENT INTO A NUMBER. This is the real deliverable.** Reuse G252's
     landed offset machinery unchanged: for the amateur fit, sample points along the **WITHHELD** court
     lines only -- the left-end arc and painted-end markings -- and measure the **perpendicular distance
     to the nearest strong image edge**, with G252's stated search radius and its explicit censoring
     statement. **Measuring the fitted far sideline, centre line or centre circle would be circular and
     must not be reported as accuracy.**
  4. **Report median, p90 and max, plus the no-candidate count**, and **place it beside G252's WNBA
     figures (median 5 px, p90 19 px on 27 VALID frames)** so the two footage classes are directly
     comparable. **Do the same for the control's withheld near-end geometry**, giving a three-way
     comparison: WNBA seeded points, WNBA lines-only, amateur line-plus-conic.
  5. **STATE THE VERDICT PLAINLY.** **If your blind judgement disagrees with G253's, say so and do not
     soften it** -- a disagreement on the programme's headline claim is the single most valuable thing
     this row can produce, and it would mean the amateur PASS needs to be re-stated or retracted. **If it
     agrees and the offsets are comparable to the WNBA figures, the claim is strengthened and should be
     reported as replicated by an independent labeller** -- still n=2 labellers on one frame, and say so.
  6. **Do NOT re-fit, do NOT relabel, do NOT tune, do NOT adjust G253's map, and do NOT propose a
     production change.** This row judges and measures; it does not repair.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,116 MB of 50,000), STOP and report if it fails.**
Stream any decode. **Do NOT delete any corpus source, G253's artifact, or the two abandoned partials in
`footage_bridge`.** Delete every temporary artifact and report bytes freed.

**HONEST LIMITATIONS to state, not discover:** **one frame per footage class and, after this row, two
labellers -- which is a replication, not a reliability measurement.** "Nearest strong edge" is a detector
output that can be wrong, absent, or belong to a floor logo, bench line or crowd rail rather than a court
marking; **report the no-candidate count and never read it as a small offset.** The search radius censors
larger offsets by construction. The amateur court model is **assumed, not measured** -- an uncalibrated
oblique view cannot establish 84 versus 94 ft, so an offset measured against it inherits that assumption.
**This CONSUMES manual geometry and is NOT automatic calibration**, which remains 0/17. **G242, G244, G247
and G248 established that no fitted residual or match statistic indicates correctness.**

ACCEPTANCE RULE:
  metric        = the blind PASS/FAIL/CANNOT JUDGE verdicts for both renders with the stated ordering, and
                  agreement with G253; then the withheld-geometry perpendicular-offset distributions
                  (median, p90, max, no-candidate count) for the amateur fit and the control, placed
                  beside G252's WNBA figures
  before       = G253's amateur PASS is one labeller's eye judgement on one render with no objective
                 anchor; the control has one (2.849 px median over 231 of 634 shared in-frame points)
  bar          = NO pass bar. **"The independent judgement DISAGREES" is the most valuable outcome** and
                 would require G253's headline to be re-stated. **"It agrees and the offsets are
                 comparable to the WNBA figures" is a full success** and would make the first
                 non-broadcast calibration a replicated result. **"The offsets are much worse than the
                 WNBA figures despite a PASS" is a third full success** and would say the eye gate is too
                 coarse for this footage. Do not tune, and do not re-fit to reach any of them.
  n            = 2 renders, 1 frame each, 1 additional labeller -- state every denominator in the verdict
                 line
  eye check    = the blind verdicts ARE part of the measurement; the offsets are the other part
  must not move = every threshold, bar and verdict, G253's fitted map and inputs, G252's method and search
                  radius, the court models, the coordinate contract, the harness, existing label files,
                  `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and keeper, the corpus, the
                  two abandoned partials
EVIDENCE: docs/evidence/tracking/g255_amateur_gate_independent_check_2026-09-04.md with the committed
blind verdicts and the ordering statement, the agreement with G253, the withheld-geometry offset
distributions for both fits beside G252's WNBA figures, the no-candidate counts, every disk-guard probe,
bytes freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.**
Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
