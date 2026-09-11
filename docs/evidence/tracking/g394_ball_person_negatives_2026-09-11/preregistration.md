# G394 preregistration: person-contained DEV negatives

## Scope and status

This artifact is sealed before any G394 rating, training, candidate detector
inference, or scored comparison. This landing is PREPARE-ONLY. The Claude
finisher alone may measure after required dependencies, allocation, and launch
receipts are independently checked.

## Binding before-condition re-run

The full joins over these read-only G389 inputs reproduced the required counts:
`docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/dev_boxes_v3.csv`,
`docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/reference_v3.csv`,
and `docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/frames_v3.csv`.
They yielded 530 DEV boxes in 27 games, 425 DEV ABSENT frames, 386 such frames
in the same 27 games, and held-out VISIBLE/ABSENT/UNKNOWN counts of 302/188/59.

## Frozen inputs and identities

- G389 readiness input is `docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/readiness.json`,
  SHA-256 `d11a1c8cdd52098ee6de16aec6df103ca22990c00cd45cd4bb4f8712bd7c8ef6`.
- G390 recipe input is `docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/args.yaml`,
  SHA-256 `463157bf0730a6457e5515c8fb609b1c16900210accae7a851742d10e6709aec`.
- A8 final-weight identity is `0f05a61618687bda2005ce4ac8343c5987f60ba0076245597de59f7380398762`.
- The person checkpoint must be named by its exact existing full path and
  SHA-256 before any launch. Automatic download or fallback is refused.
- All candidate crop inputs retain their original bytes, decode receipt, source
  game identity, and native resolution. Missing bytes remain missing.

## Fixed candidate and selection protocol

- The person pass, if authorized later, uses class 0, imgsz 640, conf 0.25,
  and IoU 0.70. A8 uses its original settings with conf 0.05.
- A candidate is only an A8 rank-0 call centre contained in at least one person
  rectangle. Person rectangles select records only; no pixels are masked.
- A retained crop is one native 320 by 320 crop centred on the call, clipped
  and padded deterministically. Full context and the exact transform accompany it.
- Eligible keys sort by game, section, numeric frame index, then key. Selection
  is `min(120, N)` at indices `round(j*(N-1)/(n-1))`, including both endpoints.
- If N is below 30, the prospective work closes CLOSED AT LIMIT before training.
- Two independent pixel raters must jointly mark NO_BALL. BALL or uncertainty
  disqualifies the selected crop without replacement; every selected state is retained.
- The threshold is at least 30 jointly confirmed, unique-parent-frame crops
  across at least five DEV games, with no held-out game or context overlap.

## Fixed prospective training and benchmark protocol

- Training retains 530 original positives and 425 original ABSENT negatives,
  appending every accepted crop once with an empty ball-label file. It uses the
  original initialization, seed 373, ten epochs, no augmentation, and final epoch only.
- Before a permitted launch, seal the actual negative manifest, recipe, readiness,
  route and checkpoint hashes, context and evaluator inputs, and one-run allowance.
- Charge the training launch before it starts. Failure or deadline closes the run;
  no alternate seed or crop quota is allowed.
- Freeze final weights and configuration before charging the one held-out token.
  Charge that token before one candidate inference over all 549 planned keys.
  Partial or failed inference spends the token and no rerun is permitted.
- Baseline reproduction is from archived predictions only. Candidate scoring, if
  later authorized, retains all 549 states and archived per-key records.

## Unmoved bars and verdict conditions

The fixed benchmark has all 549 frames: 302 VISIBLE, 188 ABSENT, 59 UNKNOWN.
The bars are C0 at least 0.25, Wilson 95 percent precision lower bound at least
0.90, and ALL FP divided by 188 at most 0.01. The centre tolerance is
`max(3 px, diameter_720p/2)` and the candidate confidence is 0.05. A result
meeting every bar is DONE on the reused set only; otherwise it is NOT VALIDATED.
Supply shortfall is CLOSED AT LIMIT; identity fault is NOT VALIDATED; a missing
seal, token, or receipt is REJECT; and a timeout is NOT VALIDATED.

## Accounting and language

No trial is charged, no evaluator is called, no metric is computed, and no
rating, training, inference, or render is performed by this prepare-only landing.
For any future paired loss record, improvement means baseline loss minus
candidate loss; positive means the candidate has lower loss. This sign convention
does not state a result here. All future OOS comparisons use the shared evaluator
with purging and a symmetric nonzero embargo, with one evaluator state per scored
tick under a stable key and archived losses derived only from evaluator records.
SEAL sha256 6fdfa08ab1ce9f95db51f3bbdc9e6eb789b7f4027d03ad15b8dde61dabde90d5
