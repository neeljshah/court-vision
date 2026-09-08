# G311 -- Apache-stack detector arm on the pod: PREMISE FALSE

**VERDICT: PREMISE FALSE at 1,736 s of the pre-declared 1,800 s (30-minute) clock.** No Apache-2.0 RTMDet person detector could be made
to RUN on the pod inside the box, so neither arm executed and NO proxy was computed -- a pre-declared valid outcome (spec
`specs/G311_spec.md`; prereg `g311_prereg_2026-09-07.md` sealed `df8cfa89e76a05e5bfb5d57ecf9998289761f79efa051a44b4a12619bc145eff`
BEFORE any run). **SCREENING ONLY: no labels, no renders, no eye check; no recall, precision, registration, accuracy or pass claim;
neither detector is said to be better -- they were never compared.**

**Premise output (clock 2026-09-07T22:09:55Z -> verdict read 22:38:51Z).** Base pod env, printed: `python 3.12.3`, `torch 2.8.0+cu128` (cuda 12.8), `cv2 4.14.0`, `numpy 2.1.2`. Constraints file used for every
install: `opencv-python-headless<5`, `opencv-python<5`, `opencv-contrib-python<5`, `numpy<3`, `setuptools<81`. Everything went to
`--break-system-packages --target /workspace/wt/a2/g311/pylib`, so the daemon's system environment was never modified; `cv2 4.14.0`
re-confirmed after every step. Logs: `g311_premise_artifact/`.

**Route (i) mmdet/mmengine/mmcv -- INSTALLED, NOT IMPORTABLE.** Resolved `mmdet 3.3.0`, `mmengine 0.10.7`, `mmcv 2.2.0`. Two
independent measured blockers: (1) `import mmdet` -> `AssertionError: MMCV==2.2.0 is used but incompatible. Please install
mmcv>=2.0.0rc4, <2.2.0.`; (2) pip resolved the **pure-Python** wheel (`mmcv-2.2.0-py2.py3-none-any.whl`), so `import mmcv._ext` ->
`ModuleNotFoundError: No module named 'mmcv._ext'` and `from mmcv.ops import batched_nms` fails identically -- RTMDet's head needs that
op, so a version-compatible mmcv without compiled ops would still not have run. A first attempt died at `ModuleNotFoundError: No
module named 'pkg_resources'` (setuptools >= 81), which `setuptools<81` in the constraints fixed. The compatible `mmcv==2.1.0` was
then built from source with `--no-build-isolation`, `MMCV_WITH_OPS=1 FORCE_CUDA=1 MAX_JOBS=96` and was **still compiling when its
780 s box expired** (`route_i3_mmcv210_build.log`: nine consecutive "Building wheel for mmcv: still running...", no wheel produced).
Compiling mmcv CUDA ops against torch 2.8/cu128 does not fit a 30-minute box.

**Route (ii) ONNX + onnxruntime -- INSTALLS IN 152 s, SHIPS NO PERSON RTMDet.** Resolved `rtmlib 0.0.16`, `onnxruntime-gpu 1.29.0`,
`onnxruntime 1.29.0`. The only RTMDet ONNX rtmlib references is `rtmdet_nano_8xb32-300e_hand-267f9c8f.zip`, a **hand** detector; its
person detectors are YOLOX and RTMO, different architectures. Four plausible person-RTMDet ONNX URLs under
`download.openmmlab.com/mmpose/v1/projects/{rtmpose,rtmposev1}/onnx_sdk/` were probed and **all four returned 404**.

**The checkpoint IS obtainable; only the runtime is missing.** Fetched and hashed:
`rtmdet_m_8xb32-300e_coco_20220719_112220-229f527c.pth`, 224,299,609 bytes, SHA-256
`229f527ca88498e8894a778a62a878a322b4a3ea2cae09ea537d34b7e907792b`, from
`https://download.openmmlab.com/mmdetection/v3.0/rtmdet/rtmdet_m_8xb32-300e_coco/rtmdet_m_8xb32-300e_coco_20220719_112220-229f527c.pth`
(HTTP 200), Apache-2.0 as mmdetection code and weights: `https://github.com/open-mmlab/mmdetection/blob/main/LICENSE` (mmcv
`https://github.com/open-mmlab/mmcv/blob/main/LICENSE`, mmengine `https://github.com/open-mmlab/mmengine/blob/main/LICENSE`). No GPL
mmyolo copy, no TVCalib/Sportlight/KaliCalib, **no new AGPL dependency.**

**Proxy table: NONE, and the probes.** The row stopped at the premise, so there is no per-game table, no ms/frame and no VRAM for either arm. The three games were selected
and ffprobe-confirmed native 1920x1080 before the stop -- `wnba_01_1080p` 30/1 18,060 frames 600.07 s,
`ncaa_basketball_IB-_u4gW3ds_1080p` 30000/1001 18,115 frames 600.10 s, `wnba_06` 30/1 28,674 frames 960.03 s -- and 9 of 16 corpus
clips were rejected as 1280x720 by measurement, not by filename.

GPU before `3302 MiB, 24576 MiB` used/total with 7 compute apps at ~470 MiB each (the `track_daemon` workers, never signalled) =
21,274 MiB free, above the 8,192 MiB gate -- which was never spent, because no detection ran. GPU after `5255 MiB, 24576 MiB`, 11
compute apps: the daemon took more workers on its own; nothing of ours ran. Disk `du_workspace_mb=UNKNOWN` (empty output treated as
UNKNOWN, never 0, per the rail); the `dd conv=fsync` probe passed. `/workspace/wt/a2/g311` grew to 2,072 MB, then 398 MB were freed
(unused route-(ii) target dir + pip cache) leaving 1,674 MB; `/workspace/wt` 8,371 MB. Pod SHA-256 before AND after, both identical:
`src/tracking/player_detection.py` `c3bc2f7d4c4fda366f83523dd0aac86e47a40fecaf26e36b490d5a8c73ca5cc7`, `yolov8n.pt`
`f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36` (a copy went to `/workspace/wt/a2/` so no auto-download could
reach the deployed one).

**Tests.** `tests/platformkit/test_g311_proxies.py` -- **7 passed in 1.09 s**, synthetic boxes only: pins `IOU_MATCH == 0.5`, greedy ONE-TO-ONE
matching (a second overlapping candidate is not consumed), a 1/3-IoU pair rejected, both-way agreement asymmetry (1.0 vs 0.5 on one
frame pair), a zero-box frame kept in every denominator, the evenly-spaced frame index formula.
`tests/platformkit/test_loc_rail_scope.py` -- **1 passed**; harness 256 LOC, under the 300 cap.

**NOT VERIFIED.**
- **Whether RTMDet would run once mmcv 2.1.0 finishes compiling.** The measured claim is "does not fit 30 minutes", NOT "cannot be
  built". A follow-up row with an hours-long build box is the honest next attempt.
- `rtmlib`'s own licence was never read; moot, since it ships no person RTMDet.
- The `.pth` was never loaded: only its bytes, size and SHA-256 are pinned, not that it works. Nothing here says anything about
  detection quality, either arm: `scripts/platformkit/tracking/g311_apache_detector_arm.py` has never been run against video and only
  its arithmetic is tested. `ncaa_basketball_WFl3V7ZY4ss` reports two video streams to ffprobe; not selected, not investigated.
