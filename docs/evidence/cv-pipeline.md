# Broadcast Video to Court Coordinates on a Consumer GPU -- built from primitives

> A complete computer-vision pipeline that turns NBA broadcast footage into per-player
> court coordinates and behavioral features, running on a single consumer RTX 4060, with
> the tracking math implemented from scratch rather than wrapped from a black box. The
> single truth-source for any figure below is
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md); this page states the honest
> capability and is explicit about what is NOT yet demonstrated.

---

## The claim

Broadcast video comes in; court coordinates and behavioral features come out. The pipeline
runs end-to-end on one consumer GPU (RTX 4060, 8GB) and writes per-track court positions
plus behavioral fields to `data/tracking_data.csv`. What makes it an engineering artifact
rather than a library demo is that the load-bearing pieces are built from primitives:

- **Multi-object tracking from scratch.** A 6D constant-velocity Kalman filter for motion
  prediction, and the Hungarian algorithm for globally-optimal frame-to-frame ID assignment
  over a blended IoU-plus-appearance cost, with a greedy fallback. Not a wrapped tracker.
- **A custom-trained ball detector.** YOLOv8n fine-tuned to a single ball class, then
  exported across PyTorch, ONNX, and TensorRT for deployment.
- **Court homography from classical CV.** HSV masking, `HoughLinesP`, line-intersection
  cornering, and `getPerspectiveTransform` recover the camera-to-court matrix per clip, with
  a static-matrix fallback and unit tests on synthetic courts.
- **Broadcast hardening.** A SIFT three-tier strategy with inlier gating, EMA smoothing,
  drift re-anchoring, and replay/scene-cut suspension so player trajectories are not
  corrupted during graphics and replays. A two-frame confirmation gate is unit-tested.
- **OSNet re-ID reimplemented in PyTorch** -- omni-scale blocks and depthwise-separable
  convolutions -- behind a layered inference backend (TensorRT to torchreid to standalone to
  MobileNetV2 to HSV histograms), so it runs whether or not the accelerated deps are present.
- **A feature layer hardened against silent corruption** -- pixel-vs-feet auto-rescale,
  physical-validity caps, phantom-slot filtering, and roughly ten documented sentinel-leak
  fixes, each guard tied to a specific observed broadcast artifact.

The end result at scale: anonymous tracker slots resolved to real NBA player identities
across 240-plus games -- **17,254 `cv_features` rows spanning 241 games and 252 distinct
real NBA player IDs** (counted directly from the local database this session).

---

## What is NOT demonstrated (the honest inventory)

The engineering is real; several tempting metrics are not, and the page says so plainly.

- **MOT accuracy is not benchmarked.** There are no ground-truth labels, so no validated
  multi-object-tracking metrics exist. The pipeline's `self_evaluation` gates measure
  self-consistency, not accuracy against a labeled reference. Position accuracy (any
  "inches" figure), ID-switch counts, and track-stability scores are **not claimed** --
  they would require ground truth this project does not have.
- **The tracker holds ~5-6 stable slots, not 10.** The detector finds all ten players, but
  on real broadcast footage the tracker maintains only up to about five to six stable
  identity slots. Reliable ten-player broadcast tracking is **not yet demonstrated**, and no
  frame-rate headline is claimed as an achieved throughput.
- **The re-ID network ships with ImageNet-pretrained weights, not NBA-fine-tuned ones.**
  The OSNet architecture was reimplemented from scratch, but it runs on stock ImageNet
  weights; the production appearance model in practice is the HSV color histogram. This is a
  reimplemented architecture, not a trained-on-basketball re-ID model.
- **CV features carry no measured predictive value today.** In the production prop models
  every CV-derived feature has SHAP importance approximately 0.0; the CV-lift report reads
  `has_cv_data: false`. The plumbing is complete and the thesis is credible, but the CV
  layer is **not** a demonstrated predictive moat -- it does not yet move the model. See
  [docs/KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md).

---

## Receipts

Every source and test path below is committed and was verified present this session. The
database and trained weights are local-only (gitignored) and named for provenance, not as
fresh-clone artifacts.

| Capability | Committed proof artifact | Status |
|---|---|---|
| End-to-end pipeline orchestration | `src/pipeline/unified_pipeline.py` | committed |
| Kalman + Hungarian tracker from primitives | `src/tracking/advanced_tracker.py` (`_make_kf()` / `_assign()`) | committed |
| Custom YOLOv8n ball-detector training | `scripts/train_ball_yolo.py` | committed |
| Court homography from classical CV | `src/tracking/court_detector.py` | committed |
| Homography unit tests (synthetic courts) | `tests/test_court_detector.py` (7/7 pass) | committed |
| Broadcast homography confirmation gate | `tests/test_homography_thresholds.py` | committed |
| OSNet re-ID reimplementation + backend chain | `src/tracking/osnet_reid.py` | committed (ImageNet weights -- see caveat) |
| Feature layer with sentinel-leak guards | `src/pipeline/tracking_feature_extractor.py` | committed |
| Ball-detector weights (PyTorch/ONNX/TensorRT) | `models/weights/yolov8n_ball.{pt,onnx,engine}` | local-only (gitignored) |
| Resolved identities at scale | `data/nba_ai.db` `cv_features`: 17,254 rows / 241 games / 252 player IDs | local-only (gitignored) |

---

## Reproduce notes

The source and tests are on a fresh clone; the trained weights, the video, and the
`nba_ai.db` corpus are local-only, so a fresh clone reproduces the *code and the unit tests*,
not the end-to-end run. The homography module is the cleanest standalone check:

```
python -m pytest tests/test_court_detector.py -q
python -m pytest tests/test_homography_thresholds.py -q
```

These pass without any GPU, video, or private data -- they exercise the classical-CV court
recovery on synthetic courts and the two-frame broadcast confirmation gate. The full
pipeline (`src/pipeline/unified_pipeline.py`) needs the trained weights and a clip, and every
accelerated component degrades gracefully to a CPU path when its dep is absent (SIFT for
LoFTR, EasyOCR for PaddleOCR, HSV histograms for the neural re-ID, CSV for Postgres), so it
runs on a laptop or a GPU server without code changes.

---

## Why it matters

Two things, and the second is the point. First, the CV engineering: implementing Kalman
filtering, the Hungarian assignment, a classical-CV homography recovery, and an omni-scale
re-ID architecture from primitives -- and hardening all of it against the silent-corruption
failure modes broadcast footage is prone to -- is mid-level CV-engineer work done solo. Every
guard in the feature layer traces to a specific broadcast artifact that was observed and
diagnosed.

Second, the honesty discipline. The easy version of this page would claim a re-ID accuracy, a
positional precision in inches, a ten-player frame rate, and a CV-feature edge. None survive
scrutiny, so none appear here. The pipeline outputs court coordinates and resolves real
player identities at real scale; the accuracy of those coordinates is not yet benchmarked
against ground truth, and the CV features do not yet move the prediction model. Stating
exactly that -- what works, and what is built-but-unproven -- is the same discipline that runs
through the rest of this evidence layer.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
