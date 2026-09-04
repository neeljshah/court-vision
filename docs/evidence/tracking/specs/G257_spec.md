GAP G257 | sport basketball (amateur) | worktree a6 | log g257_eye_gate_discrimination
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file, NO fitted map and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G256 may be running on a5; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and say in your memo that you checked and when you began. EXCLUDE
YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G253 AND G255 MEMOS AND THE G253-AMATEUR-NOT-REPLICATED LEDGER ROW FIRST.**

**WHY THIS ROW EXISTS -- WE DO NOT KNOW WHETHER THE EYE GATE CAN RESOLVE THIS FOOTAGE AT ALL.**
G253 judged its amateur fit a PASS. G255 blind-judged the same render on the same withheld geometry and
returned **CANNOT JUDGE**, giving a precise reason: the arc and painted-end evidence is **"too faint,
occluded, and visually ambiguous at this render scale to support a PASS or a FAIL."** The amateur headline
is retracted and the result is **unresolved**.

**Unresolved is not the same as wrong, and the fix is not another opinion.** Two things are confounded:
whether the map is right, and **whether a human can tell at all from these renders.** **This programme
gates every calibration on an eye check, so if the eye check cannot discriminate on this footage, that is
a limit on the whole method and not just on one row.**

THE QUESTION: **at what error magnitude can a labeller actually discriminate a court overlay on this
footage -- and does G253's candidate map separate from deliberately wrong ones?**

METHOD:
  1. **RE-RENDER AT A JUDGEABLE SCALE.** Take G253's amateur map **unchanged** and re-render it on amateur
     frame 540 at **full resolution**, with **zoomed insets on the WITHHELD geometry only** -- the
     left-end three-point arc and painted-end markings. **Do NOT re-fit and do NOT adjust the map.** State
     the render scale and inset regions.
  2. **BUILD A DISCRIMINATION SET.** Alongside the candidate, render **deliberately perturbed versions of
     the same map** at identical scale and style, perturbed by **stated, known magnitudes spanning the
     measured error scale up to obviously wrong** -- G255 measured the amateur withheld offset at median
     **12.0 px** / p90 18.0, so a ladder such as roughly 5, 10, 20, 40 and 100 px of projected-court
     displacement is the right span. **Say exactly how you perturbed and by how much.**
  3. **JUDGE THE WHOLE SET BLIND, IN RANDOMISED ORDER, WITHOUT KNOWING WHICH IS THE CANDIDATE.** Record
     **PASS / FAIL / CANNOT JUDGE** for each. **Commit the randomised order and the verdicts BEFORE
     un-blinding**, exactly as G255 committed its verdicts first, and say in the memo that you did it in
     that order.
  4. **THE HEADLINE MEASUREMENT IS THE EYE GATE'S RESOLUTION: the smallest perturbation the labeller
     correctly marks FAIL.** Report the full ladder with each verdict. **This number applies to every eye
     gate in this programme, not just to this row.**
  5. **THEN report what the candidate was called.** **If the labeller cannot separate the candidate from
     maps perturbed by 40 px or more, the eye gate is uninformative on this footage and the amateur
     question cannot be settled by looking -- say that plainly.** **If discrimination is sharp and the
     candidate is called PASS while small perturbations are called FAIL, that is meaningful support for
     the candidate**, and should be reported with the ladder, still as one frame and one labeller.
  6. **DO NOT let the discrimination result be read as a calibration verdict on its own.** A candidate
     that separates from perturbations is consistent with being right; it is not proof. **G242, G244, G247
     and G248 established that no fitted or matched statistic indicates correctness, and G254 showed an
     optimiser can improve its own objective while moving the court off the markings.**
  7. **Do NOT re-fit, relabel, tune, or propose a production change.** This row measures the instrument.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,127 MB of 50,000), STOP and report if it fails.**
Stream any decode. **Do NOT delete any corpus source, G253's or G255's artifacts, or the two abandoned
partials in `footage_bridge`.** Keep renders small enough to commit but large enough to judge -- **say how
you resolved that tension.** Delete every temporary artifact and report bytes freed.

**HONEST LIMITATIONS to state, not discover:** **one frame, one footage class, one labeller.** A
discrimination threshold measured by one person on one frame is **not** a population property of eye
gates. Perturbing a map by N px of projected-court displacement is **not** the same as a real calibration
error of N px, which distorts differently across the image -- **say how you defined the magnitude.** The
candidate map is not known-correct, so **"separates from perturbations" is consistent with correctness,
never proof of it.** Eye-label reliability in this programme has never cleared 80 pct blind agreement on
any of four measured criteria, and G246 showed repeatable labels can be uniformly wrong. **This CONSUMES
manual geometry and bears on automatic calibration not at all**, which remains 0/17.

ACCEPTANCE RULE:
  metric        = the perturbation ladder with its stated magnitudes and definition; the committed
                  randomised order and blind verdicts, written before un-blinding; **the smallest
                  perturbation correctly marked FAIL** -- the eye gate's resolution; and the candidate's
                  blind verdict reported after
  before       = G253 called the amateur fit PASS, G255 called it CANNOT JUDGE at the same render scale,
                  and nothing has tested whether a human can discriminate on this footage at all
  bar          = NO pass bar. **"The eye gate cannot discriminate below ~N px on this footage" is a FULL
                 SUCCESS and the most valuable outcome**, because it bounds every eye-gated claim this
                 programme makes. **"Discrimination is sharp and the candidate separates" is the other
                 full success.** **A labeller who marks everything CANNOT JUDGE has also produced a
                 result** -- report it as the instrument's limit, not as a failed row. Do not un-blind
                 early and do not re-fit.
  n            = 1 frame, 1 candidate, the perturbation ladder you state, 1 labeller -- name every
                 denominator in the verdict line
  eye check    = the blind ladder verdicts ARE the measurement
  must not move = every threshold, bar and verdict, G253's fitted map and inputs, G255's committed
                  verdicts, the court models, the coordinate contract, the harness, existing label files,
                  `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and keeper, the corpus, the
                  two abandoned partials
EVIDENCE: docs/evidence/tracking/g257_eye_gate_discrimination_2026-09-04.md with the render scale and
inset description, the perturbation ladder and its definition, the committed randomised order, the blind
verdicts with the ordering statement, the eye-gate resolution, the candidate's verdict, every disk-guard
probe, bytes freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE
MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
