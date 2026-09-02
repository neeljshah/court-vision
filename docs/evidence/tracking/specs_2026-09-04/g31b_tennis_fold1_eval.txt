GAP G31 (fold 1 + held-out evaluation) | sport tennis | worktree a6 | log cx_g31b_tennis_fold1_eval
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. The trainer is COMMITTED in a6 as b78d8cb46. Do not rewrite it.
PREMISE (step 0): fold 0 is ALREADY COMPLETE. Checkpoint data/models/tennis_keypoints_fold0.pt
exists on the pod (46,735,897 bytes, Sep 2 03:20) and /tmp/g31_fold0.log carries the result:
held_out tennis09, PCK@7px 0.0774, median_px 17.395, frames_ge_4_in_7 0.0, train 1713 / test 300,
final train loss 0.000007. Re-read that log first. If it does not reproduce, STOP and report
FALSIFIED. Do NOT retrain fold 0.
TWO FACTS THE PLAN GETS WRONG, carry both into the memo: (a) the trainer supports folds 0 and 1
ONLY (argparse choices=(0,1); held_out = tennis09 or tennis10), so nyYk is NEVER held out and
this is a 2-FOLD result, not 3-fold; (b) the model is trained on torchvision
ResNet18_Weights.IMAGENET1K_V1, which this program flags research-only, so the memo must carry a
LICENCE line reading: research-only, ImageNet weights, not shippable as trained.
LIMIT (step 1): the published ceiling is TennisCourtDetector 0.933 acc / 2.83 px median at 8,841
labels (G09 Table D). At 2,013 pseudo-labels, materially below it is EXPECTED and is not a
failure. The question this lane answers is only: does the model solve frames the classical
cannot? Fold 0 already returns frames_ge_4_in_7 = 0.0, so CLOSED AT LIMIT is the expected
verdict. Report it plainly if fold 1 agrees. Never lower the 7px bar to manufacture a number.
CHANGE (step 2): run fold 1 on the pod GPU. Then evaluate both folds and compare to the classical
on the SAME ranges, reading docs/evidence/tracking/tennis_sequential_plan_2026-09-01/*.json
(already committed; no /tmp copy step is needed).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per fold: PCK@7px at 1280x720, median px error, and the fraction of test frames
                  with >= 4 keypoints within 7px (denominator = held-out match test frames)
  before        = fold 0: 0.0774 / 17.395 px / 0.0 on 300 held-out tennis09 frames
  bar           = HONESTY, not a number. Required: the 2-fold table, plus the COUNT of frames
                  solved by the model AND NOT by the classical on the same ranges, each of at
                  least 30 such frames rendered and eye-checked if 30 exist. Zero such frames is
                  a valid and expected result and is reported as CLOSED AT LIMIT.
  n             = 300 held-out frames per fold
  eye check     = 12 renders per fold, EVENLY SPACED over the held-out match; no head slice
  must not move = the 7px bar, the 2,013-frame pseudo-label set, every harness threshold, and
                  the classical solver
NON-TAUTOLOGY: PCK measured against the G23 pseudo-labels is distillation fidelity, not accuracy
against truth, because the labels came from the classical solver. Say this in the memo. A
residual against the points used to fit is not independent evidence (B8).
EVIDENCE: docs/evidence/tracking/tennis_keypoint_heldout_match_2026-09-04.md -- the 2-fold table,
the model-not-classical count, the render tally, the LICENCE line, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file.
POD: fold 1 training is pod GPU work; own nohup nice job, unique /tmp log, never kill anything
(the daemon and the MLB book capture are 24/7), no git on the pod, NO scp of any module.
COMMIT: explicit pathspec, in a6, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
