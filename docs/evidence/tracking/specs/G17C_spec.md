GAP G17 v3 (LIMIT measurement, final attempt) | sport soccer | worktree a8 | log cx_g17c_soccer_role_limit
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. Rule 2 adjudication by the orchestrator: attempts 1 and 2 were
colour-heuristic DESIGNS measured against no ground truth. v3 builds the ground truth and
measures the ceiling, so it is the LIMIT measurement rule 2 requires and it is the LAST attempt.
UNBLOCKED 2026-09-02: the label set EXISTS and is complete. docs/evidence/tracking/soccer_roles_labels/
holds labels.csv (300 rows + header), crops/ (300 JPEGs, filenames match column 1 of labels.csv),
crop_manifest.csv and per_frame_counts.csv. Verify the 300/300 filename join in step 0 and then
proceed. Do NOT re-label and do NOT wait for anything.
PREMISE (step 0): the detector over-counts humans against the manual column. n=100 blind verdict
is AMBIGUOUS: manual median 13.0, pct >= 14 is 0.490, paired delta manual-minus-detector -1.23.
Attempt 1 pushed the delta to +2.26 (over-rejects real players); attempt 2 reached +0.90 but at
11.4 pct render disagreement against a 10 pct bar and landed unused with zero callers. Reproduce
the -1.23 baseline on the n=100 packet before changing anything. If it does not reproduce, STOP
and report FALSIFIED.
LIMIT (step 1): the broadcast camera holds only 10 to 16 of 22 players, so ANY count-based
verdict is bounded by framing, not by the classifier. Say what that bound is in the memo. This
lane measures how close a supervised role classifier gets to that bound, not whether the verdict
flips.
CHANGE (step 2): a 3-class crop classifier (player / referee / other). NOT colour heuristics.
resnet18 trained FROM SCRATCH, or a DINO (Apache) backbone. DO NOT use torchvision
ResNet18_Weights.IMAGENET1K_V1 or any ImageNet checkpoint -- this program flags those
research-only and this is a sellable-stack lane. Nothing SoccerNet-derived may enter the
pipeline; that is a licence breach and an automatic reject. 5-fold CV on the crops, then re-run
the paired delta on the untouched n=100 packet.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else, all three or nothing):
  metric        = (a) held-out crop accuracy over 5-fold CV (denominator = 300 labeled crops);
                  (b) paired delta manual-minus-detector on the n=100 packet (denominator = 100
                  sealed frames); (c) render disagreement rate
  before        = paired delta -1.23 at n=100; no labeled role set has ever existed
  bar           = crop accuracy >= 0.90 AND |paired delta| < 1.0 AND render disagreement < 10 pct,
                  AND per-class recall reported for all three classes.
                  READ THIS BEFORE YOU REPORT: the label set is player 268 / other 25 /
                  referee 7, so the MAJORITY-CLASS BASELINE IS 0.8933. A model that always
                  answers `player` scores 0.8933 and finds zero referees, which is 0.0067
                  under the accuracy bar. Accuracy alone therefore CANNOT show this model is
                  useful, and reporting it alone is a B1/B9 tautology. Report per-class recall
                  and the majority-class baseline alongside every accuracy figure, and state
                  plainly whether the model beats that baseline for a reason other than class
                  imbalance. With 7 referee examples over 5 folds (1.4 per fold) the honest
                  expected outcome for the referee class is CLOSED AT LIMIT on label scarcity
                  rather than on model capability -- say so if that is what you find.
  n             = 300 crops for (a); 100 frames for (b)
  eye check     = the render disagreement tally itself, EVENLY SPACED over the 100 packet frames;
                  no head slice
  must not move = the sealed n=100 packet CSVs, the deterministic detector landed as G22/G24,
                  every harness threshold, and the three bars above
NON-TAUTOLOGY: the crops must not be drawn only from frames the classifier already handles.
State the sampling rule and which frames are excluded.
IF ANY OF THE THREE BARS IS MISSED: report CLOSED AT LIMIT. S1 is never re-adjudicated and
soccer count features close at limit. That is a success, not a failure.
EVIDENCE: docs/evidence/tracking/soccer_role_classifier_v3_2026-09-04.md plus the label set --
CV accuracy per fold, the paired-delta table, the disagreement tally, a LICENCE line naming every
weight and dataset used, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file.
POD: NONE. Do NOT use the pod and do NOT ask for a pod path -- attempt 1 of this lane stalled and
returned no work because it waited on a pod mount that was never needed. The label set, the crops
and the classifier are ALL LOCAL and CPU-sized: 300 JPEG crops of about 50x100 px each. Train and
cross-validate in-process on this machine. If you believe you need a GPU for 300 crops, that is
itself the finding -- write it down and continue on CPU anyway.
COMMIT: explicit pathspec, in a8, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
