GAP G254 | sport wnba | worktree a5 | log g254_projection_refinement_and_basin
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G253 may be running on a6; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and say in your memo that you checked and when you began. EXCLUDE
YOUR OWN PROCESS AND YOUR OWN CHECKER COMMAND** -- G252 did this correctly, excluding the checker and its
parent. The `track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and
`foundry_runner` are PERMANENT residents and the load floor.

**READ THE LANDED G233d, G248 AND G252 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- G252 FOUND THE ERROR, AND THE OBVIOUS QUESTION IS WHETHER IT CAN BE REMOVED.**
G252 measured, for the first time in this programme, **how accurate an eye-valid calibration actually is**:
on the 27 VALID frames the nearest strong edge is a median **5 px** from the projected marking, **p90 19
px**, inside a 24-px search. **The median sits within G140's 11.39 px label repeatability scale, but the
p90 of 19 px exceeds it**, so the upper tail is not explained by hand-label noise alone. G252 correctly
declined to decompose the cause further.

**That single number plausibly explains all four validity negatives at once** (G242, G244, G247, G248): a
projection off by 5-19 px looks right to a human at overlay scale while missing a thin painted line, so
every pixel-precise statistic was measuring the wrong thing.

THE QUESTIONS, IN ORDER:
  **(1) Can the offset be REFINED AWAY?**
  **(2) Does a refined court still PASS the eye gate?**
  **(3) HOW ROUGH CAN THE STARTING POINT BE AND STILL CONVERGE?**

**Question 3 is the one that matters most, and it is why this row is worth running.** Automatic
calibration is **0 of 17** because the automatic search never produces a good starting homography. **But
if refinement has a wide basin of convergence, the automatic search would only need to be approximately
right, not right** -- which is a completely different and much easier problem. **This row does not attempt
automatic calibration; it measures whether the target for one is as strict as we have assumed.**

METHOD:
  1. **Start from G233d's published, gate-PASSED seed homography** on `wnba__wnba_01.mp4` frame **19599**,
     scale 1.0. **Do not relabel and do not re-derive it.** Reuse G252's landed offset measurement
     machinery so the before and after numbers are directly comparable.
  2. **REFINE the homography by minimising the distance between projected court lines and detected image
     edges.** State the objective, the optimiser, the edge detector and its settings, and the convergence
     criterion. **Refine the MATRIX, not the labels** -- the hand labels stay untouched.
  3. **Report the G252 offset distribution BEFORE and AFTER refinement**, per line type and pooled, using
     G252's exact method and the same 24-px search and censoring statement. **If the offset does not
     improve, say so plainly** -- that is a complete result.
  4. **RE-RUN THE HARD EYE GATE ON THE REFINED COURT and report PASS or FAIL in one line.** **The refined
     fit has a residual by construction and it is NOT evidence** -- G242, G244, G247 and G248 established
     that no fitted or match statistic indicates correctness. **Judge on INDEPENDENT geometry: the arc,
     the sidelines, the painted-end markings.** **A refinement that lowers the objective while moving the
     court off the paint is a FAILURE and must be reported as one** -- render it and say so.
  5. **MEASURE THE BASIN OF CONVERGENCE.** Perturb the starting homography by **known, stated amounts** --
     translate, rotate and scale the projected court by a range of magnitudes -- **re-run refinement from
     each perturbed start, and report the largest perturbation from which it still returns to the same
     answer.** Define "same answer" as a stated projected-court pixel discrepancy from the unperturbed
     refined result, and **say what you chose and why before reporting outcomes.** **Report the full
     perturbation-versus-outcome table, not just the boundary.**
  6. **STATE THE IMPLICATION FOR AUTOMATIC CALIBRATION HONESTLY AND NARROWLY.** If the basin is wide, say
     what accuracy an automatic starting guess would need **on this one frame** -- and say explicitly that
     this does NOT demonstrate automatic calibration, which remains 0/17. **If the basin is narrow, that
     is the more important result**: it would mean refinement cannot rescue a rough automatic guess, and
     it should be reported as decisively as a wide one.
  7. **Do NOT tune the objective, the detector settings or the perturbation set after seeing a gate
     result. Do NOT propose a production change. Do NOT re-open the validity-signal question.**

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,104 MB of 50,000), STOP and report if it fails.**
Stream any decode; never write a full decode to disk. **Do NOT delete any corpus source or the two
abandoned partials in `footage_bridge`.** Delete every temporary artifact and report bytes freed.

**HONEST LIMITATIONS to state, not discover:** **ONE frame, ONE seed, ONE clip, ONE arena.** A basin
measured on a single frame is not a property of the method or of the footage class. **Refinement
optimises against detected edges, which are themselves a detector output and can be wrong, absent, or
belong to something that is not a court marking** -- crowd rails, bench lines and floor logos all produce
edges. **The 24-px search censors larger offsets by construction**, and a no-candidate result must never
be read as a small offset. **This CONSUMES the hand-labelled seed and is NOT automatic calibration**,
which remains 0/17. Eye-label reliability in this programme has never cleared 80 pct blind agreement on
any of four measured criteria, and G246 showed repeatable labels can be uniformly wrong.

ACCEPTANCE RULE:
  metric        = the G252 offset distribution before and after refinement, per line type and pooled; the
                  refined court's eye-gate verdict in one line with its render; the full
                  perturbation-versus-convergence table with the stated "same answer" criterion; and the
                  largest converging perturbation
  before       = G252 measured eye-valid projections at median 5 px / p90 19 px offset, with the tail
                 exceeding G140's 11.39 px label repeatability; nothing has tried to reduce it
  bar          = NO pass bar. **"Refinement does not reduce the offset" is a full success.** **"It reduces
                 the offset but the refined court fails the eye gate" is a full success and an important
                 warning.** **"A narrow basin" is a full success and would show refinement cannot rescue a
                 rough automatic guess.** **"A wide basin with a passing gate" would be the most
                 consequential outcome**, because it would make the automatic problem approximate rather
                 than exact. Do not tune to reach any of them.
  n            = 1 frame, 1 seed, 1 clip, plus the perturbation grid you state -- name every denominator
                 in the verdict line
  eye check    = the refined-court render is the GATE; the perturbation table is the measurement
  must not move = every threshold, bar and verdict, the court model, the coordinate contract, the harness,
                  G222's matcher settings, G233d's published seed and its labels, `src/` and `domains/`
                  (READ and IMPORT ONLY), the pod daemon and keeper, the corpus, the two abandoned
                  partials
EVIDENCE: docs/evidence/tracking/g254_projection_refinement_and_basin_2026-09-04.md with the objective and
optimiser description, before/after offset distributions, the refined-court gate verdict and render, the
full perturbation-versus-convergence table, the automatic-calibration implication stated narrowly, every
disk-guard probe, bytes freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT
AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
