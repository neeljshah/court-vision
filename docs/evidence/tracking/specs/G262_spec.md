GAP G262 | sport soccer | worktree a5 | log g262_soccer_width_as_unknown
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file, NO `IMAGE_SPACE`, NO coordinate contract and NO threshold.** Build in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G260 may be running on a6; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G256b, G259 AND G261 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- THREE SOCCER NEGATIVES ALL BLAMED THE SAME THING, AND IT MAY BE SOLVABLE RATHER
THAN FATAL.**
  - **G256b:** no legal two-line-plus-conic input, because **the second line would have required the
    unknown pitch width.**
  - **G259:** **0 complete penalty-area or goal-area rectangles** in 1,195 five-second samples.
  - **G261:** **0 four-edge and 0 three-edge penalty-box cases**, only 2 two-edge cases, in the same 1,195.

**Every one of those stopped on a dimension the Laws of the Game leave free (roughly 100-110 m by 64-75 m).
I have been treating pitch width as a forbidden input. It can instead be treated as an UNKNOWN TO BE
SOLVED.**

**THE ACCOUNTING TO VERIFY -- do not take it from me, check it and report what you find.** Anchoring pitch
coordinates at the centre spot:
  - **centre circle, radius 9.15 m by rule: a conic, 5 constraints**
  - **halfway line: 2 constraints**
  - that is **7 for a homography's 8 degrees of freedom -- one short**, which is why G256b stopped
  - **add a touchline: +2 constraints and +1 unknown (the half-width), giving 9 and 9 -- determined**
  - **add BOTH touchlines: 11 constraints for 9 unknowns -- over-determined, plus a symmetry check**

**AND THE PAYOFF IS BIGGER THAN A FIT: THE RECOVERED WIDTH IS AN OBJECTIVE PLAUSIBILITY TEST.** If the
solver returns a half-width implying **64-75 m**, that is consistent with the Laws; if it returns 30 m or
200 m, the fit is wrong **and no human eye was needed to say so.** **This programme has been almost
entirely eye-gated, and G257 measured that gate at only 20 px resolution -- an independent numeric
plausibility check is worth having on its own.**

**THE SOURCE, VERIFIED:** `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4`,
**2,341,768,743 bytes**, SHA-256 `7e4c123f91eb7e096ae2a018482818929b000c9bc2b8b9ca47b542b61ba8c55e`.
**`/workspace` EXISTS ONLY ON THE POD** -- reach it over ssh as G252-G261 did. Confirm bytes and SHA-256
first and STOP if either differs.

METHOD:
  1. **VERIFY THE DEGREES-OF-FREEDOM ACCOUNTING YOURSELF and state it in the memo.** If it is wrong, say
     so and stop -- **that alone would be a complete result** and would close the idea cheaply.
  2. **Reuse G259's committed survey.** Re-screen for frames showing **the centre circle, the halfway line,
     and at least one touchline** in usable extent. **G256b already identified frame 5400 as having the
     centre circle and halfway line** -- start there and check whether a touchline is also usable.
     **Report how many samples show all three, and how many show both touchlines.**
  3. **VERIFY IDENTITY BEFORE ANY FIT (G246's protocol): commit a zoomed crop for every fitted line and for
     the conic**, stating which painted feature it is and **what portion you actually observed.** A line
     inferred through players or extended beyond the paint is not the line.
  4. **SOLVE FOR THE HOMOGRAPHY AND THE HALF-WIDTH JOINTLY.** Report the recovered pitch width in metres.
     **State plainly whether it falls in the Laws' 64-75 m range**, and treat a value outside it as
     evidence the fit is wrong, not as a discovery about the stadium.
  5. **CHECK DEGENERACY: report the observed fraction of the centre circle's circumference, the image angle
     between the halfway line and the touchline, and the condition number of the system solved.** A
     touchline nearly parallel to the halfway line in the image, or a barely-observed circle, is
     degenerate -- **report it, do not fit it silently.**
  6. **HARD GATE: render and report PASS or FAIL in ONE LINE first, judged on INDEPENDENT geometry the fit
     did NOT use** -- the penalty box, the goal area, the penalty arc, or the second touchline if you fit
     only one. **Never judge on a fitted element. The fit residual is NOT evidence** (G242/G244/G247/G248),
     and **G254 showed an optimiser can improve its own objective while moving the projection off the
     markings.**
  7. **REPORT THE WIDTH CHECK AND THE EYE GATE SEPARATELY.** They are independent evidence and their
     agreement or disagreement is itself informative. **Per G257 a PASS bounds error at roughly the eye
     gate's resolution; it does NOT certify correctness.**
  8. **Do NOT change `IMAGE_SPACE`, the coordinate contract or any production module. A FAIL, an
     implausible width, or "no frame shows all three features" are all FULL SUCCESSES** -- report the
     screen counts either way.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` ON THE POD (baseline ~33,185 MB of 50,000), STOP and report if it
fails.** Stream any decode. **Do NOT delete any corpus source or the two abandoned partials in
`footage_bridge`.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** **one clip, one camera plan, one labeller** -- all four
soccer negatives so far describe THIS broadcast's camera, not soccer footage generally, and this row
inherits that. **This CONSUMES manual geometry and is NOT automatic calibration**, which remains 0/17.
**A recovered width inside 64-75 m is a plausibility check, not a measurement of the pitch** -- many wrong
fits can produce a plausible number, so it is necessary and not sufficient. **Fitting a line or arc from a
short observed portion extrapolates it across the image and small angular error amplifies with distance**
-- report how much of each feature you observed. Eye-label reliability here has never cleared 80 pct blind
agreement on four criteria; **G246 showed repeatable labels can be uniformly wrong; G257 measured the eye
gate at 20 px.**

ACCEPTANCE RULE:
  metric        = your verification of the DOF accounting; the counts of samples showing circle + halfway
                  line + one touchline, and both touchlines; the identity crops with observed portions;
                  the recovered pitch width in metres with its Laws-range verdict; the degeneracy report;
                  and the eye-gate verdict stated separately, FIRST in one line
  before       = soccer has 0 accepted homographies; three rows stopped on the unknown pitch width or on
                 absent box geometry, and none tried solving for the width
  bar          = NO pass bar. **A PASS with a plausible recovered width would be the first soccer pitch
                 coordinates this programme has produced, with an objective check the eye gate cannot
                 give.** **"The DOF accounting is wrong", "no frame shows all three features", and "the
                 recovered width is implausible" are all equally full successes.** Do not tune, do not
                 relabel after the gate, and do not report an implausible width as a stadium fact.
  n            = 1 clip, the re-screened sample count, 1 fitted frame if any, 1 labeller -- name every
                 denominator in the verdict line
  eye check    = the identity crops gate the inputs; the withheld-geometry render is the eye GATE; the
                 recovered width is the independent numeric check
  must not move = every threshold, bar and verdict, `IMAGE_SPACE`, the coordinate contract, G253's
                  harness, G259's committed survey, existing label files, `src/` and `domains/` (READ and
                  IMPORT ONLY), the pod daemon and keeper, the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g262_soccer_width_as_unknown_2026-09-04.md with the DOF verification, the
screen counts, every identity crop and observed portion, the recovered width and its range verdict, the
degeneracy report, the eye-gate verdict stated FIRST, every disk-guard probe, bytes freed, and a NOT
VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting
(A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
