GAP G258 | sport wnba | worktree a6 | log g258_synthetic_truth_validity
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G256b may be running on a5; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS
PARENT.**

**READ THE LANDED G247, G248, G252 AND G257 MEMOS AND THE G257-IMPLICATION LEDGER ROW FIRST.**

**WHY THIS ROW EXISTS -- THE FOUR VALIDITY NEGATIVES WERE TESTED AGAINST LABELS THAT ARE THEMSELVES ONLY
GOOD TO 20 px.**
G242, G244, G247 and G248 all asked: does any signal separate frames a human labelled VALID from those
labelled INVALID? **The answer was no, four times, and those rows stand.**

**But G257 has now measured the labeller.** A blind perturbation ladder put the **eye gate's resolution at
20 px** -- +20, +40 and +100 px displacements were called FAIL, while the candidate, +5 px and +10 px were
all **CANNOT JUDGE**. And G252 measured the calibration error itself at **median 5 px, p90 19 px.**

**So "VALID" never meant "correct". It meant "within about 20 px."** The VALID class is heterogeneous in
the underlying error, and those four rows were asking pixel-scale statistics to separate a smeared class.
**That is a limitation of the experimental design, and the design can be fixed: replace the eye labels
with SYNTHETIC GROUND TRUTH.**

**THIS DOES NOT REOPEN OR OVERTURN G242/G244/G247/G248.** Their question -- "does any signal track the eye
labels?" -- is answered and closed. **This is a DIFFERENT question their own limitation invites.**

THE QUESTION: **starting from a known map and displacing it by KNOWN amounts, does any
projection-based signal detect the error -- and what is the smallest displacement it detects?**

**THE PAYOFF IS DIRECTLY COMPARABLE TO G257.** The eye resolves 20 px. **If a signal resolves 5 px, it
beats the human and the programme has its first validity gate. If nothing resolves even 40 px, the
negative becomes far stronger than four rows against noisy labels ever established.**

METHOD:
  1. **Start from G233d's published, gate-PASSED seed homography** on `wnba__wnba_01.mp4` frame **19599**,
     scale 1.0. Reuse G247's persisted matrices and G252's landed offset machinery so everything is
     comparable. **Do not relabel and do not re-fit.**
  2. **Build a perturbation ladder with KNOWN displacements**, using **G257's definition of projected-court
     displacement so the two rows are directly comparable** -- say explicitly how you define and apply
     magnitude, and include **0 px (unperturbed) as the control**. A ladder of roughly 0, 2, 5, 10, 20, 40
     and 100 px is the right span.
  3. **NOTE WHICH SIGNALS CANNOT APPLY, AND WHY -- this is itself a result.** Perturbing the MATRIX does
     not change the feature match at all, so **match count, inlier count, inlier ratio and match RMS are
     mathematically incapable of detecting it.** State that plainly rather than measuring it: it explains
     G244's negative structurally, not just empirically.
  4. **MEASURE THE PROJECTION-BASED SIGNALS ACROSS THE LADDER**, at minimum: **G252's perpendicular offset
     to the nearest image edge** (its search radius and censoring statement unchanged), **G248's
     edge-response contrast against perpendicular controls**, and **G247's quad-shape checks**. Report each
     signal's value at every rung.
  5. **REPORT MONOTONICITY AND THE SMALLEST DETECTED DISPLACEMENT PER SIGNAL.** Define "detected" before
     you look -- a stated separation from the 0 px control, using repeated frames to estimate the control's
     own spread -- and **say what you chose and why in advance.** **Do not fit a threshold to the ladder
     and then report its accuracy on the same ladder.**
  6. **STATE THE MACHINE RESOLUTION BESIDE G257's 20 px EYE RESOLUTION.** That comparison is the headline.
  7. **THE CENSORING LIMIT IS CRITICAL HERE.** G252's search radius was 24 px, so **a displacement beyond
     it cannot be measured as a distance and will saturate.** Say where each signal saturates; a saturated
     signal is not a detecting signal.
  8. **DO NOT propose a production gate, do NOT tune, and do NOT claim this settles automatic
     calibration**, which remains 0/17 and is a different problem entirely -- **detecting a bad map is not
     finding a good one.**

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` ON THE POD (baseline ~33,139 MB of 50,000), STOP and report if it
fails.** Stream the decode; never write a full decode to disk. **Do NOT delete any corpus source or the
two abandoned partials in `footage_bridge`.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one frame or a stated small set, one seed, one clip, one
arena. **A synthetic uniform displacement is NOT a real calibration error**, which distorts non-uniformly
across the image -- **a signal that detects synthetic displacement may still fail on real error, and this
row cannot tell you which.** The 0 px control is only as good as G233d's seed, which G257 shows is itself
certified only to ~20 px. **Detecting displacement from a known start is a strictly easier problem than
validating an unknown map**, and the result must never be reported as though it solved the latter.
Nothing here bears on automatic calibration, which remains 0/17.

ACCEPTANCE RULE:
  metric        = the ladder definition; the structural statement of which signals cannot apply and why;
                  each projection-based signal's value at every rung; monotonicity; the pre-declared
                  detection criterion; the smallest detected displacement per signal; the saturation point
                  of each; and the machine resolution stated beside G257's 20 px
  before       = four rows found no signal separating eye-VALID from eye-INVALID, but G257 has since shown
                 the eye labels themselves only resolve 20 px while the error is 5-19 px
  bar          = NO pass bar. **"A signal resolves below 20 px" would give the programme its first
                 validity gate and beat the human judge.** **"Nothing resolves even 40 px against KNOWN
                 truth" is an equally full success** and would make the validity closure far stronger than
                 four rows against noisy labels. Do not fit a threshold to the ladder, and do not present
                 this as automatic calibration.
  n            = the ladder rungs and frame count you state, 1 seed, 1 clip -- name every denominator in
                 the verdict line
  eye check    = none required; this row is signals against known truth. Commit a few ladder renders if
                 they aid a reader
  must not move = every threshold, bar and verdict, G233d's published seed and labels, G247's matrices,
                  G252's method and search radius, G257's committed verdicts, the court model, the
                  coordinate contract, the harness, `src/` and `domains/` (READ and IMPORT ONLY), the pod
                  daemon and keeper, the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g258_synthetic_truth_validity_2026-09-04.md with the ladder definition and
magnitudes, the structural non-applicability statement, the full signal-versus-displacement table, the
pre-declared detection criterion, the per-signal smallest detected displacement and saturation point, the
machine-versus-eye resolution comparison, every disk-guard probe, bytes freed, and a NOT VERIFIED list.
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
