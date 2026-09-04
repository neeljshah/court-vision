GAP G217 | sport ncaa_basketball / wnba | worktree a5 | log g217_oracle_error_decomposition
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build in
`scripts/platformkit/tracking/`.

**S1 MACHINE: RUN LOCALLY. Do NOT use the pod** -- G216 is measuring concurrency throughput there and
any extra load corrupts its numbers. Everything this row needs is committed in the repo: the 17
frames, `docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv`, and the G210b fitter.
If you believe you need the pod, STOP and say why instead of using it.

**WHY THIS ROW EXISTS -- THE ORCHESTRATOR RE-READ G210b's ORACLE AND BELIEVES A LANDED STRATEGIC CLAIM
IS WRONG. Your job is to CONFIRM OR REFUTE THAT, not to agree with me.**

Read `oracle_fit` in `scripts/platformkit/tracking/g210b_court_fit_untruncated_search.py:114`. It does
this: for each of the four true paint lines it computes, for every DETECTED line group, the mean
absolute point-line distance to the two labelled corner points, and picks the `argmin`. It then solves
the homography from **`groups[index].line` -- the DETECTED line geometry**. The labels are used ONLY to
CHOOSE among the detector's own lines; they never construct an exact line.

**Therefore the oracle bounds LINE SELECTION, not line ACCURACY, and its residual error is inherited
from the detected lines themselves.** The landed G214 ledger row states: *"Since the oracle assumes
PERFECT line selection, a better line detector cannot lift the result much -- the ceiling is not
detection quality but the difficulty of a four-point homography at 12 px on these frames."*
**The orchestrator believes the second half of that sentence does NOT follow from this construction.**
It was used to argue that further line-detection work "should not be funded on hope", so if it is
wrong it has already mis-steered the programme.

**The independent reason to doubt the 'homographies are just hard' reading: G196 fitted a homography
from four HAND-LABELLED corners on these same frames and the three-point arc landed correctly
OUT-OF-SAMPLE.** So on this footage the court model and the pure projective assumption are already
demonstrated adequate, and lens distortion is not visibly the problem. **A four-point homography on
these frames is NOT inherently a 29 px operation when its inputs are accurate.**

THE QUESTION: **how much of the oracle's 28.841 px median max-corner error comes from the DETECTED
LINE GEOMETRY, and how much from anything else?**

METHOD:
  1. **Reproduce G210b's oracle number first, unchanged, as your control.** If you cannot reproduce
     0/17 and ~28.841 px median, STOP and report the mismatch -- that is itself the finding, and it
     matters because it would mean a landed row is not reproducible.
  2. **Read out the oracle's own `distances`** (it already returns them: the mean absolute point-line
     distance from each PICKED detected line to the two labelled corner points it should pass through).
     **Report the distribution across all 17 frames and all four roles.** This is a direct measurement
     of how wrong the selected lines are, and nobody has ever looked at it.
  3. **Build a TRUE-LINE control.** Construct the four paint lines EXACTLY from the labelled corner
     points (baseline through corners 0-1, free-throw through 2-3, lane-left through 0-2, lane-right
     through 1-3), pass them to **`solve_line_pairs` unchanged**, and score with **`score_frame` from
     `g205_zero_shot_corner_probe.py` unchanged** so the number is commensurable with G205, G208, G210b
     and G214. **This isolates the fitter and the court model from the detector completely.**
  4. **State the three-way decomposition plainly:** detected-line oracle (G210b's number), true-line
     control (this row), and G196's hand-corner result. **If the true-line control is near zero, the
     error is DETECTED LINE GEOMETRY and detection accuracy is the live lever. If the true-line control
     is ALSO ~29 px, the fitter or the court model is defective and that is a DIFFERENT and equally
     important finding.** Both outcomes are full successes. Do not prefer either.
  5. **If the true-line control scores well, say explicitly what that does and does NOT mean.** It does
     NOT produce automatic calibration -- it consumes labels. It would mean the measured 1/17 ceiling
     is a property of the CURRENT line detectors' accuracy, not of the approach, and that G214's
     defunding recommendation rests on a misreading. **Say so in those words if the evidence supports
     it, and say the opposite if it does not.**

**HONEST LIMITATIONS to state, not discover:** 17 frames is a small construct set and it is the same
one every calibration row has used, so this measures those frames, not a rate. G140's p90 label
repeatability is **11.39 px**, so the 12 px threshold sits at the label noise floor and a true-line
control scoring well is partly a statement about label quality. The labelled corners are themselves
single-source eye labels.

**DO NOT** change `solve_line_pairs`, `score_frame`, the 12 px protocol, the court model, or any
threshold. **DO NOT** add a new line detector or tune an existing one -- this row explains an existing
number, it does not chase a better one.

ACCEPTANCE RULE:
  metric        = the oracle's picked-line distance distribution over 17 frames x 4 roles; the
                  true-line control scored as frames-with-all-four-within-12px over 17 plus median
                  max-corner error; both set beside G210b's 1/17 at 28.841 px
  before        = the oracle's 28.841 px is attributed in the ledger to "the difficulty of a four-point
                  homography at 12 px", and that attribution was used to recommend against further
                  line-detection work
  bar           = NO pass bar. This row ATTRIBUTES an existing error; it does not try to beat it.
                  **"The claim in the G214 row is correct and the orchestrator is wrong" is a FULL
                  SUCCESS and must be reported plainly if that is what the numbers say.**
  n             = 17 frames (CONSTRUCT, exhaustive) x 4 corner roles = 68 label points
  eye check     = render the true-line control's projected court on 3 frames beside G210b's oracle
                  render for the same frames
  must not move = every threshold, `conf`, the 12 px protocol, G205's scorer contract, `solve_line_pairs`,
                  the court model, the coordinate contract, every bar and verdict, `src/` (READ ONLY),
                  the pod (DO NOT USE IT), the corpus
EVIDENCE: docs/evidence/tracking/g217_oracle_error_decomposition_2026-09-04.md with the reproduction of
G210b's control, the picked-line distance distribution, the true-line control table, the three-way
decomposition, the renders, an explicit verdict on whether the G214 strategic claim survives, and a
NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
