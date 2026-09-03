# G208 learned zero-shot paint-corner probe

## Verdict

**No measured learned candidate clears the acceptance bar.** Official M-LSD tiny
FP32 produced **0 / 17** frames with all four paint-corner roles within 12
native pixels. Its individual corner recall was **2 / 68**, with **2 / 265
(0.75 percent)** proposal hits and **15.59 proposals/frame**. It is therefore
not a positive result, despite a far lower proposal volume than G205.

This row does **not** close the global zero-shot route: ELSED, HAWP, DeepLSD,
and KpSFR each had a concrete bounded exclusion and were not measured. The
M-LSD model weights are `LICENCE-UNVERIFIED`, so this row has not measured a
licence-clean learned candidate. G205's classical candidate and M-LSD both
fail their numerical bar; that is not evidence that the unrun primitives fail.
This does not close labelling.

No production code, `src/`, pod route, `run_clip.py`, corpus target, threshold,
or acceptance bar was changed. No training or fine-tuning occurred.

## Construct and frozen scoring contract

- Input was the unchanged G140 CSV: 68 targets and 17 exhaustive frames, all
  four distinct named roles per frame. Images were read via `source_decode` and
  checked against declared native dimensions: 12 at 1920x1080, four at
  1280x720, and one at 640x360. No scorer resize or 1080p assumption occurred.
- The new harness imports G205's `score_frame` directly. A generic proposal
  makes a target available only at native Euclidean distance <= 12.0 px;
  proposal precision credits a proposal within that radius of any target; the
  primary event requires all four named roles in one frame.
- G140 blind-label p90 repeatability is **11.39 px**. The 12 px tolerance is
  at the label-noise floor: a pass would show rough availability, not
  production-suitable coordinate accuracy.
- Before: G141 had 0 / 68 naive-detector recall. G205 stable-LSD had 0 / 17
  all-four frames, 22 / 68 recall, 80 / 32,777 (0.24 percent) precision, and
  1,928.06 proposals/frame. G196 shows labelled corners recover geometry; this
  row measures detection only.

## Candidate provenance, licences, and acquisition

`LICENCE-UNVERIFIED` means the code licence was established, but no separate
checkpoint licence grant was found. A candidate in that state cannot be shipped
on this evidence even if it meets the metric.

| Candidate | Code licence and establishment | Weight licence and establishment | Exact checkpoint and size | Status |
|---|---|---|---|---|
| ELSED | Apache-2.0: root `LICENSE`, official [ELSED](https://github.com/iago-suarez/ELSED) commit `1878213b2f5f06a9261d8b1838f53d48e5fd128d` | Not applicable; no learned weights | None | Excluded. One official `pyelsed` `pip install --no-deps` build failed at CMake because MSVC C/C++ tooling is absent; no alternate build/binding was tried. |
| M-LSD | Apache-2.0: root `LICENSE`, official [M-LSD](https://github.com/navervision/mlsd) commit `453cafa09467d0272760578d35c1fda38e8895a5` | `LICENCE-UNVERIFIED`: the repository software notice is not a separate weight grant | [M-LSD_512_tiny_fp32.tflite](https://raw.githubusercontent.com/navervision/mlsd/453cafa09467d0272760578d35c1fda38e8895a5/tflite_models/M-LSD_512_tiny_fp32.tflite), 2,491,732 bytes | **Run**, but cannot ship on weight-licence evidence. |
| HAWP | MIT: root `LICENSE`, official [HAWP](https://github.com/cherubicXN/hawp) commit `92ae446875ef9296fc95de7313519aabd638ebb5` | `LICENCE-UNVERIFIED`: no separate checkpoint licence found | [HAWPv3 ImageNet](https://github.com/cherubicXN/hawp-torchhub/releases/download/HAWPv3/hawpv3-imagenet-03a84.pth), 47,315,279 bytes from official GitHub Release API; not fetched | Excluded. Code package 1.0 installed, but its required `easydict==1.13` declares LGPL-3.0. It was immediately uninstalled; no GPL-family dependency was retained or bypassed. |
| DeepLSD | MIT: root `LICENSE`, official [DeepLSD](https://github.com/cvg/DeepLSD) commit `d873fd3619d6e44a9f625bc437ab4786057677e5` | `LICENCE-UNVERIFIED`: official README provides downloads but no separate weight licence | [wireframe](https://cvg-data.inf.ethz.ch/DeepLSD/deeplsd_wireframe.tar), 102,898,321 bytes; [MegaDepth](https://cvg-data.inf.ethz.ch/DeepLSD/deeplsd_md.tar), 102,898,193 bytes from HTTP HEAD; neither fetched | Excluded. The model imports native `pytlsd` and `line_refinement` unconditionally; source submodules were absent from the shallow clone and MSVC is unavailable. No native-build repair was attempted. |
| KpSFR | MIT: root `LICENSE`, official [KpSFR](https://github.com/ericsujw/KpSFR) commit `3d4b7968e2ab34239bf4c175f17a29efa46a691f` | `LICENCE-UNVERIFIED`: official project supplies a URL but no independent weight licence | [WorldCup kpsfr.pth](https://cgv.cs.nthu.edu.tw/KpSFR_data/model/kpsfr.pth), 714,819,558 bytes from HTTP HEAD | Excluded after one official fetch. It reached about 134 MiB in the 30-second local command window before executor termination; it was not resumed or retried. |

Source checkouts and partial downloads are outside this worktree in a temporary
directory; no third-party source or checkpoint is vendored here.

## M-LSD fixed configuration

The following configuration was fixed across all 17 frames and was neither
target-derived nor tuned per frame:

1. Official `M-LSD_512_tiny_fp32.tflite`, model input 512x512, TensorFlow Lite CPU.
2. Official decode `score_thr=0.10` and `dist_thr=20.0`.
3. Form a proposal from each native-pixel segment pair only when it intersects
   inside both observed supports, has acute separation >=35 degrees, and lies
   inside the native image. Endpoint extension is 0 px; deduplication is 2 px.
4. Pass the generic point set unchanged to G205's `score_frame`.

No role labels or homography are produced by this measurement.

## Results

| Candidate | All-four frames | Corner recall | Proposal precision | Proposals/frame | Acceptance |
|---|---:|---:|---:|---:|---|
| G205 stable-LSD (before) | 0 / 17 | 22 / 68 | 80 / 32,777 (0.24%) | 1,928.06 | Fail; unusable volume |
| M-LSD tiny FP32 | **0 / 17** | **2 / 68** | **2 / 265 (0.75%)** | **15.59** | **Fail**; below >=1 / 17 |

M-LSD's lower proposal rate is not success by itself: it makes no all-four
frame available and only two individual roles.

### M-LSD per-frame table

| Audit ID | Native dimensions | Proposals | Matched roles | All four within 12 px |
|---|---:|---:|---:|---|
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973` | 1920x1080 | 12 | 0 | no |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785` | 1920x1080 | 27 | 0 | no |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171` | 640x360 | 14 | 0 | no |
| `ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871` | 1920x1080 | 11 | 0 | no |
| `ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925` | 1280x720 | 9 | 0 | no |
| `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920` | 1280x720 | 27 | 0 | no |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760` | 1920x1080 | 23 | 0 | no |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340` | 1920x1080 | 22 | 0 | no |
| `wnba__wnba_01_1080p__s01__f001600` | 1920x1080 | 13 | 1 | no |
| `wnba__wnba_01_1080p__s03__f004062` | 1920x1080 | 25 | 1 | no |
| `wnba__wnba_01_1080p__s06__f007539` | 1920x1080 | 13 | 0 | no |
| `wnba__wnba_02__s11__f021983` | 1280x720 | 12 | 0 | no |
| `wnba__wnba_04__s06__f012223` | 1280x720 | 3 | 0 | no |
| `wnba__wnba_06__s03__f007237` | 1920x1080 | 5 | 0 | no |
| `wnba__wnba_06__s07__f014099` | 1920x1080 | 10 | 0 | no |
| `wnba__wnba_06__s09__f018997` | 1920x1080 | 18 | 0 | no |
| `wnba__wnba_07__s08__f016801` | 1920x1080 | 21 | 0 | no |

The two available roles were `paint_near_free_throw_right_corner` on WNBA 01
frame 001600 (nearest proposal 10.46 px) and
`paint_near_free_throw_left_corner` on WNBA 01 frame 004062 (1.97 px). Neither
frame supplies its other three roles.

## Eye check

The only measured learned candidate is also the closest candidate. Its generic
proposals were rendered at the fixed lexical positions 0, 4, 8, 12, and 16:

- [00 NCAA](g208_zero_shot_corner_probe_learned/renders/mlsd_00_ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg)
- [04 NCAA](g208_zero_shot_corner_probe_learned/renders/mlsd_04_ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg)
- [08 WNBA](g208_zero_shot_corner_probe_learned/renders/mlsd_08_wnba__wnba_01_1080p__s01__f001600.jpg)
- [12 WNBA](g208_zero_shot_corner_probe_learned/renders/mlsd_12_wnba__wnba_04__s06__f012223.jpg)
- [16 WNBA](g208_zero_shot_corner_probe_learned/renders/mlsd_16_wnba__wnba_07__s08__f016801.jpg)

Human inspection agrees with the arithmetic. Cross proposals are sparse rather
than G205-dense, but concentrate on basket apparatus, players, crowd and bench
edges, broadcast-overlay boundaries, and unrelated court geometry. In all five
views, at least three labelled paint corners have no nearby M-LSD intersection.
The few proposals near the paint do not combine into four roles in any frame.

## Reproduction and packages

The measured run used the declared local `basketball_ai` interpreter:

```text
C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe --version
# Python 3.10.20

C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_g208_zero_shot_corner_probe_learned.py -q
# 1 passed in 1.96s

set G208_MLSD_SOURCE=C:\path\to\official\mlsd-453cafa
C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m scripts.platformkit.tracking.g208_zero_shot_corner_probe_learned
```

Measured runtime packages: Python 3.10.20, numpy 1.26.4, OpenCV 4.13.0, torch
2.1.2+cu121, torchvision 0.16.2+cu121, tensorflow-cpu 2.15.1 (Apache-2.0),
tensorflow-intel 2.15.1 (Apache-2.0), keras 2.15.0 (Apache-2.0), tensorboard
2.15.2 (Apache-2.0), and tensorflow-estimator 2.15.0 (Apache-2.0). HAWP 1.0
was installed only for its bounded import check; yacs 0.1.8, kornia 0.7.4, and
kornia-rs 0.1.14 were installed during that failed setup. `easydict` 1.13 was
removed immediately after its LGPL-3.0 metadata was seen.

The harness is 180 LOC, below the 300 LOC rail; no allowlisted module changed.

## NOT VERIFIED

- ELSED, HAWP, DeepLSD, and KpSFR inference on the construct. Each is named
  above with a bounded exclusion; none is a negative measured score.
- Separate weight licences for M-LSD, HAWP, DeepLSD, and KpSFR. M-LSD ran as
  `LICENCE-UNVERIFIED` and cannot ship on this record.
- Any global closure of the zero-shot route, any conclusion about labelling,
  homography/calibration/tracking accuracy, production deployment, or
  generalisation beyond this 17-frame construct.
- Accuracy stricter than the 12-px label-floor feasibility rule.
