GAP G246 | sport basketball (amateur) | worktree a6 | log g246_amateur_gate_failure_diagnosis
**MEASUREMENT AND DIAGNOSIS ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT
only. Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G244 may be running on a5; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and say in your memo that you checked and when you began.** The
`track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner`
are PERMANENT residents and the load floor.

**READ `G243b_spec.md` AND ITS LANDED MEMO FIRST. THIS ROW ASKS WHY, AND ONLY WHY.**

G243b did everything right and **both seed gates FAILED** on
`basketball__amateur_jh3fnwMi7dM.mp4` (1280x720, 3,601 frames, SHA-256
`773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea`), seed frame **2760**:
  - **Clustered** (four paint corners), labelling 1 fitted: `(45,385) (283,276) (363,424) (624,306)`
  - **Spread** (paint free-throw corners plus centre-circle top/bottom): `(363,424) (624,306) (1140,359)
    (1160,468)`
  - Label repeatability over 3 independent labellings: clustered median 9.925 / max 10.630 px; spread
    median 10.630 / max 11.314 px -- **both under G140's 11.39 px p90**, and **all three labellings gave
    the same FAIL verdicts.** So this is not label noise.
  - It used its own high-school model (84x50 ft, 12-ft lane, 19-ft paint depth, 6-ft centre-circle radius,
    19 ft 9 in arc) because **`court_points_for_sport` has only two keys, `ncaa_basketball` and `wnba`,
    and BOTH assume a 94-ft court.**

**THE MECHANISM THAT MAKES THIS WORTH A ROW.** G243b reported its self-fit round-trip RMS as
**0.000000000 px for both sets, and correctly called it degenerate**: four point correspondences exactly
determine a homography, so the residual is zero **whether or not the correspondence is right.**
**Therefore a wrong point-role mapping, a wrong axis convention, or a mislabelled feature is INVISIBLE to
every fitted metric and shows up ONLY in the render.** That is the same lesson G242 taught from the other
direction, and it means a silent bookkeeping error is fully consistent with what G243b observed.

THE QUESTION: **why did both gates fail -- a bookkeeping error, a wrong court model, or genuinely
unrecoverable geometry?**

METHOD:
  1. **VERIFY POINT IDENTITY FIRST.** Re-open the exact seed frame 2760 and, for each of the 8 labelled
     pixels, **state what court feature is actually at that pixel.** Do not assume the role names are
     correct. **Commit a zoomed crop around each labelled point.** If a point is not the feature its role
     claims, that alone may be the answer.
  2. **VERIFY THE COURT MODEL AGAINST THE FOOTAGE.** Is the lane actually 12 ft, the court 84 ft, the arc
     19 ft 9 in? **Say what is visibly checkable and what is not.** Report whether the visible markings are
     consistent with the high-school model G243b assumed, and note that
     **`court_points_for_sport` has no high-school key at all** -- that is a platform gap worth stating.
  3. **ENUMERATE THE ROLE MAPPINGS AND AXIS CONVENTIONS, AND RENDER EVERY ONE.** For the SAME labels and
     the SAME model, vary only the correspondence: the ordering of the four points, and the axis
     convention (which baseline is y=0, whether x increases left-to-right). **Render all variants and
     COMMIT ALL OF THEM, not only any that look right.**
  4. **THIS IS DIAGNOSIS, NOT TUNING, AND THE DIFFERENCE MUST BE PROTECTED.** You are not permitted to
     search for something that passes and then present it as a calibration. **If a variant produces a
     render that lands on the independent painted geometry, you MUST say it was found by enumeration**,
     and you MUST then do step 5 before claiming anything.
  5. **OUT-OF-SAMPLE CONFIRMATION IS MANDATORY FOR ANY PASSING VARIANT.** Apply that same mapping,
     unchanged, to **a DIFFERENT seed frame in the same clip**, label it fresh, and render. **A mapping
     found by enumeration on one frame and confirmed on an independent frame is a finding. One that is
     not confirmed is a coincidence and must be reported as such.**
  6. **JUDGE EVERY RENDER ON INDEPENDENT GEOMETRY -- the three-point arc, the sidelines, and the centre
     circle, which this footage shows and G233d's crop did not. NEVER on the fitted points.** Ignore any
     RMS: with four points it is identically zero and carries no information.
  7. **If no variant works, say so plainly.** "The failure is not a role mapping or an axis convention"
     is a complete result and would point at the court model or the camera geometry instead.
  8. **Do NOT propagate, do NOT compute an in-court fraction, do NOT compute labels-per-hour, and do NOT
     propose a production change or a new `court_points_for_sport` key.** This row answers one question.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,024 MB of 50,000), STOP and report if it fails.**
**Do NOT delete the two abandoned partials in `footage_bridge`** (2,490,710,544 and 4,999,500,276 bytes)
-- that decision is not yours. Keep renders small, delete every temporary artifact and report bytes freed.
Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** one clip, one seed frame for the enumeration, one labeller.
Eye-label reliability in this programme has never cleared 80 pct blind agreement on any of four measured
criteria, and this row is entirely eye-judged. **A four-point homography has zero residual by
construction, so no fitted number here is evidence of anything.** G242 is controlling: match counts,
inliers, inlier ratio and RMS do not establish that a court is correct. Nothing here bears on automatic
calibration, which remains 0/17. A diagnosis is not a fix and must not be reported as one.

ACCEPTANCE RULE:
  metric        = the per-point identity check with committed crops; the court-model check against the
                  footage; every enumerated variant with its committed render and eye verdict; and, for
                  any passing variant, the mandatory out-of-sample confirmation on an independent frame
  before       = G243b failed both gates across 3 labellings under G140's repeatability p90, using a
                 self-built high-school model because no such key exists; no cause was established
  bar          = NO pass bar. **"It was a role mapping / axis convention, confirmed out of sample" is one
                 full success. "No variant works, so it is not bookkeeping" is an equally full success**
                 and would redirect the question to the court model or the camera. Do not present an
                 enumerated pass as a calibration, and do not tune the labels.
  n            = 1 clip, 1 seed frame enumerated, 1 confirmation frame, 1 labeller -- state this in the
                 verdict line
  eye check    = every enumerated render IS the measurement
  must not move = every threshold, bar and verdict, `court_points_for_sport`, the coordinate contract, the
                  harness, G222's matcher settings, the label files, `src/` and `domains/` (READ and
                  IMPORT ONLY), the pod daemon and keeper, the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g246_amateur_gate_failure_diagnosis_2026-09-04.md with the point-identity
crops, the court-model check, every enumerated variant and render, any out-of-sample confirmation, the
plain cause statement or its absence, every disk-guard probe, bytes freed, and a NOT VERIFIED list.
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
