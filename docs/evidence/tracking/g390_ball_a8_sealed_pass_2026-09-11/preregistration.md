# G390 Arm A8 sealed-pass preregistration

Spec: `docs/evidence/tracking/specs/G390_spec.md`.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections A, B, Q1, Q4, and Q6.

## Scope and immutable allocation

This preparation seals one future held-out candidate inference for Arm A8 only. It is not a training, inference, scoring, evaluator, or pod invocation. The future finisher must charge one immutable token before that inference. A token already charged, a failed launch, a partial output, or a completed output closes the allowance: a replacement held-out inference is refused. Arm A9 remains unavailable and Arm A10 is not scheduled.

The future training GPU budget is at most 90 minutes and the cumulative training GPU budget is at most 120 minutes. Any timeout, identity mismatch, source-receipt failure, or budget overrun is recorded as `CLOSED AT LIMIT` with no held-out candidate inference.

## Bound source identities

All paths below resolve inside this worktree. The future run reads one table at a time and never modifies an input.

| purpose | path | SHA-256 | bytes | required condition |
|---|---|---|---:|---|
| native frames | `docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/frames_v3.csv` | `11797e162dd303441a7bde18e66fae4b404341fa2bd611678226182258d58945` | 562358 | 1,620 rows and `sheet_scale=1.0` on every row |
| settled reference | `docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/reference_v3.csv` | `ad00670c3601706d5d817de734fc85d82e8fdc379ea03b21bbe1a46e272ad09e` | 206458 | 1,620 unique settled keys; held-out 302 VISIBLE, 188 ABSENT, 59 UNKNOWN |
| audited development boxes | `docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/dev_boxes_v3.csv` | `e151f932c3b4bffe84c89aa8fde18f08c346a1e3a6e65d27ed4b36f095b7b4fa` | 82373 | 530 unique keys from 27 games |
| readiness receipt | `docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/readiness.json` | `fe8bcbeff936ed7162b706c14b7d1bdf61e32b90ab2aee186be105847f611b64` | 669 | 1,620/1,620 settled; 0 candidate executions; 0 recorded GPU minutes |
| prior execution accounting | `docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10/arm_accounting.csv` | `1d64edae0c8779b1fc195d3207dc8f230166a4225f652dc35da1306487ef3b62` | 302 | A8 historical execution count is zero |
| deployed route identity | `src/tracking/ball_detect_track.py` | `cbc7cd9dfb7e18691f310b7594be046ac0d3184a279c43d8eb427210355bc9ea` |  | hash again on the pod before launch |
| initialization checkpoint | `models/weights/yolov8n_ball.pt` | `bc979654e281c5de6e0e992e1f9587b3a9faa2eec996ea41b1b03954ba0b6e52` |  | hash again on the pod before launch |

The preparation-side complete-table check reproduced: 1,620 frame rows, 1,620 unique settled reference keys, 549 held-out keys, ABSENT=188, UNKNOWN=59, VISIBLE=302, 530 distinct development boxes, 27 development games, candidate executions=0, and recorded G389 GPU minutes=0. The current PC route file hash is not the bound deployed-route hash, and the checkpoint is absent from this worktree; neither observation is a pod identity check. The launch gate therefore remains unverified until the pod hashes the bound route, checkpoint, and cache.

## Frozen A8 configuration

Training: initialize from the bound checkpoint; `imgsz=960`; `batch=2`; `epochs=10`; `optimizer=SGD`; `lr0=0.001`; `lrf=0.01`; `momentum=0.937`; `weight_decay=0.0005`; `warmup_epochs=3.0`; `warmup_momentum=0.8`; `warmup_bias_lr=0.1`; `seed=373`; `workers=0`; `device=0`; `deterministic=True`; `amp=False`; `pretrained=True`; `resume=False`; `cos_lr=False`; `patience=0`; `save=True`; `save_period=-1`; `exist_ok=False`; `cache=False`; `rect=False`; `multi_scale=False`; `single_cls=True`; `fraction=1.0`; `val=False`; `plots=False`; `verbose=False`; `profile=False`; `freeze=0`; `close_mosaic=0`.

Augmentation: `hsv_h=0.0`; `hsv_s=0.0`; `hsv_v=0.0`; `degrees=0.0`; `translate=0.0`; `scale=0.0`; `shear=0.0`; `perspective=0.0`; `flipud=0.0`; `fliplr=0.0`; `bgr=0.0`; `mosaic=0.0`; `mixup=0.0`; `copy_paste=0.0`; `erasing=0.0`; `crop_fraction=1.0`.

Inference: final epoch checkpoint only; `imgsz=960`; `conf=0.05`; `iou=0.70`; `max_det=300`; `agnostic_nms=False`; `classes=0`; `half=True`; `device=0`; `augment=False`; `visualize=False`; `retina_masks=False`; `stream=False`; no tiling, temporal, or held-position output. Retain every no-detection frame. Keep only the highest-confidence OBSERVED rank-0 box per frame.

Training inputs are only the audited development frames and boxes. ABSENT development reference rows may supply negatives. UNKNOWN rows never supply negatives. Game/context separation and all causal-neighbour exclusions remain fixed. No additional footage or class-dependent replenishment is allowed.

## Sealed scoring and evaluation protocol

Before any scorer call, `g390_sealed_input.load_sealed_input` must verify the two bound table hashes, exact key equality, complete settlement, and native `sheet_scale=1.0`; a 0.5-scale row or any missing reference row raises and no score is produced. `g390_score.score_sealed` delegates detection accounting to `g363_score.score_arm`, converts native reference coordinates consistently to 720p, retains UNKNOWN rows, and reports both `TP/549` and `TP/N_visible` plus `ALL_FP/N_absent`.

The future comparison builds exactly one evaluator state per scored tick with a stable `state_key` derived from frame identity, never one state per game. It supplies a sealed per-tick timestamp/context table, uses `cpcv_evaluate` with its symmetric nonzero embargo and purge, archives every evaluator record, and derives archived baseline and candidate loss only from those records. Improvement is baseline loss minus candidate loss; positive means candidate better. No result is reported until the prerequisite evaluator input is present and validated.

The immutable quality bars are `TP/549 >= 0.25`, Wilson 95 percent precision lower bound `>= 0.90`, and `ALL_FP/N_absent <= 0.01`. The centre-only match is at most `max(3 px, diameter_720p/2)`. These bars will not move. The 30-render review must be evenly sampled across all 549 held-out frames and include no-detection frames.

## Prepare-only verdict

VERDICT: NOT EXECUTED. No training, candidate inference, score, evaluator record, token charge, pod job, route identity verification, or weight verification occurred in this preparation.
SEAL sha256 c27ad65d341eb336a6c5fe7c8fb1a412a685b3b86827b8f2285d74dd4944b261
