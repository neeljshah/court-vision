GAP G263 | sport soccer | worktree a5 | log g263_soccer_two_touchline_screen
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file, NO `IMAGE_SPACE`, NO coordinate contract and NO threshold.** Build in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G260 may be running on a6; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G262 MEMO AND THE G262-DOF-CORRECTION LEDGER ROW FIRST.**

**WHY THIS ROW EXISTS -- G262 REFUTED MY MATHEMATICS AND NAMED THE FIX IN THE SAME BREATH.**
I claimed centre circle (5 constraints) + halfway line (2) + **one** touchline (+2, +1 unknown half-width)
gives 9 equations in 9 unknowns. **G262 verified it and found the first 7 correct and the touchline step
false:** there is a one-parameter family `S_t` of projective transformations for which `(H, w)` and
`(S_t H, w_t)` reproduce **the same observed circle, halfway line and single touchline** while changing the
recovered width. **The system carries an unresolved one-dimensional gauge, so any width returned would be
initialisation-dependent -- exactly not the objective check I claimed.**

**Its refutation also names what would work: "Two symmetric touchlines can break this particular gauge
because, generically, `S_t` does not map the pair `y = +/- w z` to another symmetric pair for nonzero `t`."**
It correctly did not drift into that configuration, because its spec said to stop when the accounting is
wrong.

**THIS ROW IS DELIBERATELY NARROW AND CHEAP: does any frame in this clip show the centre circle, the
halfway line AND BOTH touchlines?** Four soccer rows have already closed on absent geometry, so **screen
before building anything.**

METHOD:
  1. **START WITH THE SCREEN, NOT A FIT. Reuse G259's committed survey** -- its 12 panels and manifest are
     landed; do not re-survey. **Re-screen the 1,195 samples for frames showing the centre circle, the
     halfway line, and BOTH touchlines in usable extent.** A partially occluded line is usable; an absent
     one is not.
  2. **REPORT THE COUNTS: how many samples show all four features, and how many show three of them with
     which one missing.** **That count is the deliverable whatever follows**, and it is the fourth
     independent statement about what this camera plan actually presents.
  3. **CONFIRM ANY CANDIDATE AT NATIVE RESOLUTION before accepting it**, as G259 did -- "a low-resolution
     panel impression did not count" was the right standard and remains it.
  4. **IF ZERO SAMPLES QUALIFY, STOP AND REPORT THAT.** **That closes hand-fitted standard-geometry
     calibration for this soccer clip across five independent screens** (G256b two-line-plus-conic, G259
     rectangles, G261 box edges, G262 the one-touchline gauge, and this) **and is a FULL SUCCESS.** Say
     plainly that the conclusion is about **this broadcast's camera plan**, not about soccer footage
     generally -- the corpus holds ONE soccer clip.
  5. **ONLY IF A QUALIFYING FRAME EXISTS:** verify identity first with **committed zoomed crops for every
     fitted line and for the conic, stating what is at it and what portion you observed** (G246's
     protocol); **verify the two-touchline DOF accounting yourself and stop if it is wrong**, exactly as
     G262 did with mine; then solve jointly, **report the recovered pitch width in metres against the
     Laws' 64-75 m range**, report degeneracy (observed conic fraction, image angles, condition number,
     and whether the two touchlines are near-parallel in the image), and **gate on INDEPENDENT geometry
     the fit did not use** -- the penalty box, goal area or penalty arc -- **PASS or FAIL in one line
     first.**
  6. **The fit residual is NOT evidence** (G242/G244/G247/G248), and **G254 showed an optimiser can improve
     its own objective while moving the projection off the markings.** **Per G257 a PASS bounds error at
     roughly the eye gate's 20 px resolution; it does NOT certify correctness.**
  7. **Do NOT change `IMAGE_SPACE`, the coordinate contract or any production module, and do NOT propose a
     production change.**

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` ON THE POD (baseline ~33,197 MB of 50,000), STOP and report if it
fails.** Stream any decode. **Do NOT delete any corpus source or the two abandoned partials in
`footage_bridge`.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** **one clip, one camera plan, one labeller** -- every soccer
finding tonight describes this broadcast, and the corpus holds a single soccer clip. **This CONSUMES manual
geometry and is NOT automatic calibration**, which remains 0/17. A recovered width inside the Laws' range
would be a **plausibility check, not a measurement of the pitch** -- many wrong fits can produce a
plausible number. Eye-label reliability here has never cleared 80 pct blind agreement on four criteria;
**G246 showed repeatable labels can be uniformly wrong; G257 measured the eye gate at 20 px.**

ACCEPTANCE RULE:
  metric        = the count of samples showing circle + halfway line + both touchlines, and the
                  three-of-four counts with the missing feature named; then, only if a candidate exists,
                  your own verification of the two-touchline accounting, the identity crops, the recovered
                  width against 64-75 m, the degeneracy report, and the eye-gate verdict stated FIRST
  before       = four soccer rows have closed on absent geometry or a false DOF premise; the two-touchline
                 configuration is named by G262's refutation and has never been screened
  bar          = NO pass bar. **"Zero samples qualify" is a FULL SUCCESS** and would close hand-fitted
                 standard-geometry soccer calibration for this clip across five independent screens. **A
                 PASS with a plausible recovered width would be the first soccer pitch coordinates this
                 programme has produced.** Do not fit a degenerate configuration and do not report an
                 implausible width as a stadium fact.
  n            = 1 clip, 1,195 re-screened samples, 1 labeller -- name every denominator in the verdict
                 line
  eye check    = the screen counts are the measurement; any identity crops gate the inputs; any
                 withheld-geometry render is the GATE
  must not move = every threshold, bar and verdict, `IMAGE_SPACE`, the coordinate contract, G253's
                  harness, G259's committed survey, existing label files, `src/` and `domains/` (READ and
                  IMPORT ONLY), the pod daemon and keeper, the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g263_soccer_two_touchline_screen_2026-09-04.md with the screen counts and
the missing-feature breakdown, any native-resolution confirmations, any identity crops, any DOF
verification, any recovered width and degeneracy report, any gate verdict stated FIRST, every disk-guard
probe, bytes freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE
MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
