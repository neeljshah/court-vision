# G373 execution preregistration

Spec: docs/evidence/tracking/specs/G373_spec.md.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B, Q1, and Q6.
Worktree: C:/Users/neelj/nba-track-a11 only. This is PREPARE ONLY; no pod command, inference, rating, training, evaluator call, or scored comparison occurs in this commit.

## Binding premise before any new inference

The finisher must re-run the named binding condition: reproduce A0 and A7 held-out integer counts against the current SHA-256 values of src/tracking/ball_detect_track.py and models/weights/yolov8n_ball.pt. Record both hashes and the re-run output in binding_replay.json before any new A0 inference. The historical comparison is A0 TP=0, FP=8 and A7 TP=2, FP=178 over the same 549 held-out frames. If the re-run condition still holds, execute the CHANGE steps; premise falsification is allowed only after quoting that exact output.

## Frozen source schedule

The existing source is docs/evidence/tracking/g363_ball_coverage_2026-09-09/frames.csv (349326 bytes, all rows 1920x1080), with 881 unique keys split into 332 development and 549 held-out frames. Its recorded LF-normalized SHA-256 is b0c5e8953d4385a84b0d258e5b98da32149a985f3b49964df566abd1bf3565ea. Context identity is docs/evidence/tracking/g363_ball_coverage_2026-09-09/cache_manifest.csv (549779 bytes); no cache, video, or corpus store was opened in this prepare-only commit.

Before ratings, the finisher seals exact frame and context hashes, split membership, and a fixed extra-frame sample. Ratings use a blind full-frame native pass, then optional 256-pixel crops; v1 labels remain alongside a separately sealed v2 reference. Native diameter is max(box_w, box_h). Both-VISIBLE agreement names both populations and reports per-frame, p90, and missingness.

## Matching and bars

Primary matching is one-to-one centre-only at 720p: distance <= max(3 px, half the reference diameter). IoU >= 0.30 is secondary only and never decides the primary result. UNKNOWN predictions are false positives. Every 549 held-out reference frame remains in the denominator.

The fixed bars are C >= 0.25, Wilson lower precision >= 0.90, FP/N_absent <= 0.01, and at least 150 VISIBLE plus 150 ABSENT held-out frames. C is TP/549. The integer recall implication is TP >= 138 of 285 VISIBLE frames (48.42 pct), not 50 pct. No bar may move.

## Arms, selection, and evaluator protocol

A8 requires at least 500 unique adjudicated development boxes from at least five games; otherwise it is LIMIT. A9 requires a concrete pinned implementation and licence receipt sealed with the arm list; otherwise it is LIMIT with no substitute. A10 is unavailable whenever A8 lacks boxes. Cumulative A8/A9 training is capped at 120 GPU minutes with steps, batch, and seed fixed before training.

Before every scored loss comparison, use scripts/platformkit/eval_gate/walkforward.py or cpcv_evaluate with purging and a symmetric nonzero embargo. Use one stable evaluator state per scored tick, never one state per game standing for its ticks. Archive paired losses only from evaluator records. Improvement is baseline loss minus candidate loss; positive means candidate better. No such comparison is authorised by this prepare-only commit.

## Evidence sequence

After the binding replay, seal the v2 reference and development-only arm choice. Seal selected weights and configuration before exactly one new held-out candidate run. Archive ratings_v2.csv, reference_v2.csv, dev_boxes.csv, arms.csv, predictions.csv, frame_scores.csv, licence_receipt.json, summary.json, weights/, and sheets/ under this evidence directory. The memo reports GPU and inference minutes separately, source path/size/resolution for each opened input, route and weight hashes, and an explicit NOT VERIFIED list.

## Execution accounting

No score, evaluator state, ledger charge, route execution, or candidate selection was launched by this commit. The orchestrator commits this preregistration by explicit pathspec (lane_commit); it is intentionally sealed before any measurement.
SEAL sha256 8f504e3712db5e7d4f408383061a67e4ac912b6388a8b8e2f367a6cfbea5b0cb
