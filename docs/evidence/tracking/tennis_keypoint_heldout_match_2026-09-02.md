# G31: learned tennis court-keypoint model on a HELD-OUT MATCH -- CLOSED AT LIMIT

Date: 2026-09-02. Gap: G31. Worktree a6, trainer `b78d8cb46`.
Verdict: **CLOSED AT LIMIT.** At 2,013 pseudo-labelled frames the model does not
reach the 7 px bar on either held-out match, and it solves **zero** frames the
classical solver fails on. The bar was not moved and no threshold was touched.

## 1. Result, both folds

| fold | held out | train frames | test frames | PCK@7px | median px | median cells | p90 px | >= 4 kp in 7px |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | tennis09 | 1,713 | 300 | 0.0774 | 17.395 | 1.450 | 24.309 | **0.0** |
| 1 | tennis10 | 1,419 | 594 | 0.0355 | 17.475 | 1.456 | 22.812 | **0.0** |

Published bound for context, not a target: TennisCourtDetector 0.933 accuracy /
2.83 px median at 8,841 hand labels (G09 Table D). At 2,013 pseudo-labels a
materially worse number was expected; the question this row answers is only
whether the model solves frames the classical cannot.

**Frames solved by the model AND NOT by the classical: 0.** The solve proxy
(>= 4 keypoints within 7 px) is 0.0 on both folds under both decoders, so the
count is zero by construction and there is no set of >= 30 such frames to render.

## 2. Independent reproduction (contract A2)

The verifier re-scored both saved checkpoints in a separate process
(`subpixel_probe.jsonl`, script beside it) rather than quoting the trainer. The
argmax path reproduces the trainer exactly:

| fold | trainer PCK / median | verifier argmax PCK / median |
|---|---|---|
| 0 | 0.077381 / 17.395048 | 0.077381 / 17.395048 |
| 1 | 0.035474 / 17.474897 | 0.035474 / 17.474897 |

## 3. A decode hypothesis, tested and FALSIFIED

`decode_heatmaps` takes the heatmap argmax and scales it to source pixels. The
heatmap is 160 x 90 against a 1920 x 1080 source, so **one cell is exactly 12.0
source px** and the 7 px bar is 0.58 of a cell. That raised a real possibility
that the bar was being tested with an instrument too coarse to pass it, which
would have made CLOSED AT LIMIT the wrong verdict.

It was tested directly: the same checkpoints re-scored with quadratic sub-pixel
refinement around the argmax, no retraining.

| fold | argmax median px | sub-pixel median px | argmax PCK@7 | sub-pixel PCK@7 | solve proxy |
|---|---:|---:|---:|---:|---:|
| 0 | 17.395 | 16.874 | 0.0774 | 0.0379 | 0.0 -> 0.0 |
| 1 | 17.475 | 18.281 | 0.0355 | 0.1437 | 0.0 -> 0.0 |

**Hypothesis rejected.** Sub-pixel decoding moves the median by under 1 px, in
opposite directions on the two folds, and does not change the solve proxy at
all. The error is **1.45 heatmap cells**, comfortably larger than the
quantisation floor of half a cell, so it is model error and not a decode
artifact. Quantisation is not the binding constraint and the 7 px bar was a
fair test.

## 4. Render-and-look

4 of the 24 saved renders viewed (2 per fold, evenly spaced, no head slice); 6
are committed beside this memo along with both metrics JSONs. Green is the
model, red is the pseudo-label.

What the renders show, and it matters for how this row is read: **the model has
genuinely learned court structure, and on footage it never saw.** Fold 0 holds
out an Australian Open night match on blue Plexicushion; fold 1 holds out a WTA
Cincinnati day match, different surface, different broadcaster, different camera
height. In both, every predicted keypoint lands on the correct court
intersection. The failure is precision, not comprehension: predictions sit
roughly a cell and a half from truth, with the displacement smallest near the
net centre and largest at the far corners.

So this is not a model that failed to learn. It is a model that learned the
right thing to about 17 px, on a bar that requires 7.

## 5. Two corrections to what the program believed

- **This is a 2-fold experiment, not 3.** `tennis_keypoint_train.py:190` takes
  `--fold` in `{0,1}` and `split_fold():45` holds out tennis09 or tennis10.
  **nyYk is never held out.** PLAN_TRACKING_RESEARCH T3 and the handoff both say
  three folds; they are wrong.
- **LICENCE: research-only, not shippable as trained.** The encoder is
  torchvision `ResNet18_Weights.IMAGENET1K_V1` (`:112-115`, `pretrained=True` by
  default), the exact class of weights this program forbids for the soccer lane.
  A `--no-pretrained` flag exists. Since the verdict is CLOSED AT LIMIT no
  shippable model is needed, so the licence question is recorded rather than
  resolved.

## 6. What this closes, and what it does not

CLOSED AT LIMIT applies to **the distillation route at this label budget and
this architecture**: pseudo-labels from the classical solver cannot teach a
student to beat the teacher, which is the expected outcome, and the student adds
nothing the classical solver does not already provide.

It does NOT establish that a learned keypoint model is unreachable on this
footage. The renders argue the opposite. What has never been tested is a real
hand-labelled corner set, which is why the 5.28 ft classical anchor and every
PCK number here remain **distillation fidelity, not accuracy against truth**.
That is research-plan row T5, and it is unaffected by this close.

## NOT VERIFIED

- 20 of the 24 renders were not viewed.
- No hand-labelled corner truth exists, so every number here is measured against
  pseudo-labels produced by the classical solver (contract B8 applies: this is a
  self-fit and is not independent line evidence).
- The `--no-pretrained` variant was not trained, so the licence-clean ceiling at
  this label budget is unmeasured.
- Nothing was deployed to the pod, and no production tracking path consumes this
  model. The checkpoints stay under `data/models/` on the pod volume only.
- The sub-pixel probe ran against the saved checkpoints only; it was not run as
  part of training, and it is committed as evidence, not as a production path.
