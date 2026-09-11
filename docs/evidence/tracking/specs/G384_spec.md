GAP G384 | sport basketball | worktree a11 | log cx_g384_ball_phase2_receipt
**RANK 3 - FINISH G373 PHASE 2, OR CLOSE ITS UNSUPPLIED ARM. Landed docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json SHA-256 d3bbf294e9f5f7c4fec9fa60e3ff9b232bf9aad39ecf992a644e727d0faeb250; dev_boxes.csv SHA-256 9de259c4410c483a0bc9d774d44cff895ddb0ac94aec4d8efb3d4ae86b71641d. This is one continuation with G373's execution history, not a new detector tournament.**
**WHERE THIS ROW RUNS:** PC blind adjudication; pod read-only existing native cache, sequential GPU only after reference readiness. Budget: 20 min prepare, 90 adjudicate, 50 train/score, 20 receipt; original cumulative training cap <=120 GPU minutes still binds.
**PREMISE (step 0, BINDING before-condition):** reproduce 283 boxes/27 games and reconcile every queue key against sheet_manifest_all.csv, reference_v2.csv and adjudications_v2.csv before allocating ratings.
The memo says 393 dev +235 held-out remain; this review's complete local join finds 361 dev +235 held-out =596 queued, none already adjudicated. Seal the reconciliation and retain the discrepancy; never blindly add 628 tasks.
If a G373 candidate has already been scored, return PREMISE FALSE with that receipt. If reference/cache identity fails, stop scoring and report NOT VALIDATED; do not regenerate a different benchmark.
METHOD (sealed before any new rating or score):
1. Explicit owner handoff from G373; import its code/seals/accounting, preserve v1 and phase-1 artifacts, and write only G384 additive outputs. Process the whole reconciled queue in fixed interleaved even section/key order, blind to detector predictions.
2. Finisher settles labels/boxes from full native pixels; difficult or unreadable cases remain explicit UNKNOWN, never fabricated agreement. Rebuild the full original 881-frame v2 reference and fixed extra-development sample; audit causal-neighbour dedup.
3. Create a separate full-schema frames_v2.csv with sheet_scale=1.0 for native v2 labels; preserve all 332/549 keys, splits and context hashes. Verify coordinate roundtrip and a planted matching prediction on >=30 evenly spaced visible keys before real scores.
4. Seal the complete reference, native box validation and all development choices. Usability remains median disagreement <=half median native diameter with >=30 pairs; report p90 and unresolved cases, retaining the phase-1 primary-rater evidence.
5. Train A8 only with >=500 unique audited dev boxes/>=5 games and sufficient sealed time budget; A10 requires A8. A9 remains LIMIT absent the originally required pinned licence/dependency receipt; no retroactive substitution.
6. Before training, freeze capped steps/batch/seed, the permitted arm list and development tie rule within the inherited budget. Select on development only; seal weights/config before ONE candidate held-out run, alongside A0 on the same v2 reference.
7. Deadline or incomplete reference/quota -> unrun arms CLOSED AT LIMIT, trained-but-unscored candidate NOT VALIDATED, no benchmark score. Complete reference plus no available replacement -> close arm supply honestly; do not relaunch the old G363 row.
ACCEPTANCE RULE:
| field | binding value |
|---|---|
| metric | Reference completeness/all scheduled keys; audited unique dev boxes; rank-0 TP/FP/FN, C=TP/549, Wilson precision lower, ALL FP/N_absent and TP/N_visible. |
| before | Repeatable v1 A0 0 TP/8 FP over 549; native agreement median 17.33/p90 287.09 px; 283 dev boxes; no candidate score. |
| bar | Scoring only with complete usable reference, >=150 VISIBLE and >=150 ABSENT held-out; C>=0.25, Wilson lower>=0.90, ALL FP/N_absent<=0.01. Centre-only match <=max(3 px, diameter_720p/2); UNKNOWN predictions are FP. |
| n | 881 original reference keys, 549 held-out; all reconciled queued keys attempted/accounted for, >=30 per scored submetric else descriptive. Extra dev games remain excluded from held-out selection. |
| eye check | 30 evenly spaced held-out native frames across the full set, including no detection/ABSENT/UNKNOWN; if no arm runs show reference readiness, never a winner. |
| must not move | G373/G363 historical seals, reference v1, benchmark split, matching and bars, deployed route/weights, G344/G357 constants, daemon and flags. |
| verdict | DONE only on inherited quality bars; PARTIAL/NOT VALIDATED for scored failures; scoped CLOSED AT LIMIT for unsupplied arms. Reused benchmark is not fresh confirmation. |
EVIDENCE: docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10.md and matching directory with queue_reconciliation.csv, reference_v2.csv, frames_v2.csv, transform_checks.csv, dev_boxes.csv, arm_accounting.csv, weights/, predictions.csv, paired_frame_scores.csv, summary.json, renders/ and common receipts.
TEST: tests/platformkit/test_g384_ball_phase2_receipt.py alone: native scale roundtrip, missing-reference prohibition, UNKNOWN FP, quota/A10 dependency and no second candidate held-out execution.
VERSION 2026-09-10 - proposed continuation; limits preserved, phase-1 queue discrepancy must be reconciled.


ORCHESTRATOR FOOTER (binding, 2026-09-10 night): codex terra PREPARES (prereg sealed alone as its OWN commit, `SEAL sha256 <hex>` over every byte above the seal line); a Claude finisher MEASURES; codex-sol VERIFIES; `src/`, `kernel/`, `api/`, `intel/` READ only (PROPOSED diffs only); never write `data/registry/`, never flip a flag, never touch the register; **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** as the memo; every new file <= 300 lines; vocabulary follows contract Q6 with an automated scan (patterns built from character codes); n >= 30 with even sampling; ASCII stdout; **NEVER PARK.** Astra source: docs/research/astra_night_review_2026-09-10.md (local-only).
