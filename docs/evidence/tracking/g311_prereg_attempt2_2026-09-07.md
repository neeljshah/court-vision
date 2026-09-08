# Preregistration: G311 ATTEMPT 2 -- Apache-stack detector arm on the pod (SCREENING)

Registered 2026-09-07, **before any detection was run and before any proxy was
computed**. Spec: `docs/evidence/tracking/specs/G311_spec.md`. Attempt 1 is
`g311_prereg_2026-09-07.md` (seal
`df8cfa89e76a05e5bfb5d57ecf9998289761f79efa051a44b4a12619bc145eff`), landed
PREMISE FALSE at 89bba69fd.

## Why there is an attempt 2

Attempt 1 stopped because `mmcv==2.1.0` was **still compiling when its 780 s
sub-box expired** inside a pre-declared 30-minute premise clock. Its measured
claim was "does not fit 30 minutes", explicitly NOT "cannot be built", and its
NOT VERIFIED list names an hours-long build box as the honest next attempt.
This row is that attempt. **The measurement design does not change**: the games,
the frame list, the proxies, the sign convention and the conclusions barred are
carried over verbatim from attempt 1.

The attempt-1 verifier (codex-sol, contract A/B/Q) returned **REJECT on Q3** --
the premise window effectively ended at 1,736 s of the sealed 1,800 s with an
eligible route unresolved -- and its minimal correction was to rerun route (i)
"through elapsed >= 1,800 s or a terminal error". That is this row. The same
verifier filed **G311-HARNESS-RAILS** against
`scripts/platformkit/tracking/g311_apache_detector_arm.py`, and because that
defect would corrupt the very figures this prereg defines, it is FIXED BEFORE
this seal rather than inherited. Three rail changes, all declared here and none
touching the proxy arithmetic:

1. `WARMUP = 3` detector calls per arm before the clock starts, excluded from
   every `ms_per_frame` figure (attempt 1 timed its warm-up, contradicting
   proxy 4 below).
2. `decode()` RAISES on any failed read instead of silently dropping the frame,
   so the declared denominator cannot shrink unobserved.
3. `agreement()` RAISES if the two arms are not frame-aligned.

Tests grew from 7 to 9 to cover changes 2 and 3. The harness is 271 lines, under
the 300-line rail. NOTHING else in the file is touched.

## Premise, redeclared with a LONG BUILD BOX

Binding before-condition, **3-hour clock, polled every 10 minutes**: on the pod,
an Apache-2.0 RTMDet person detector must IMPORT AND RUN. Route: build
`mmcv==2.1.0` CUDA ops from source with `MMCV_WITH_OPS=1 FORCE_CUDA=1
MAX_JOBS=96` and `TORCH_CUDA_ARCH_LIST=8.6` (the RTX 3090's sm_86 only -- the
one change from attempt 1's build invocation, which compiled every default
architecture), `--no-build-isolation`, against the pod's `torch 2.8.0+cu128` /
Python 3.12, plus `mmengine 0.10.x` and `mmdet 3.3.0`. Success is exactly:

    PYTHONPATH=/workspace/mmlab_env python3 -c "import mmcv, mmdet; from mmcv.ops import batched_nms; print(mmcv.__version__, mmdet.__version__)"

**Full disclosure of ordering**: the build box was launched at
2026-09-07T23:03:55Z, before this file was sealed. It is a PREMISE step -- it
installs a library and computes NO proxy, decodes NO frame and runs NO detector.
This seal is placed before any detection. If the stack does not import within
3 hours, ONE documented alternative is attempted; if that also fails, the row is
BLOCKED with the exact error and that is a VALID RESULT.

Forbidden, unchanged: the mmyolo RTMDet copy (GPL-3.0), TVCalib, Sportlight,
KaliCalib, and any new AGPL dependency. Every licence is pinned by URL.

## Isolation, declared now

All installs go to `--target /workspace/mmlab_env` (build deps to
`/workspace/mmlab_builddeps`, wheels to `/workspace/mmlab_wheels`). The
`track_daemon`'s system `site-packages` is never written, the daemon is never
stopped or signalled, and `cv2` stays 4.x on both sides (constraints file pins
`opencv-python-headless<5`, `opencv-python<5`, `opencv-contrib-python<5`,
`numpy==2.1.2`). `pod_run` hardcodes its own `PYTHONPATH`, so
`/workspace/mmlab_env` is prepended through `env` in argv; no repo code is
edited to reach it.

## Games and frames (fixed now, identical to attempt 1)

`wnba_01_1080p`, `ncaa_basketball_IB-_u4gW3ds_1080p`, `wnba_06` -- all three
ffprobe-confirmed native 1920x1080 in attempt 1 and reconfirmed at run time.
Pod paths `data/footage_corpus/wnba__wnba_01_1080p.mp4`,
`data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4`,
`data/footage_corpus/wnba__wnba_06.mp4`. Frame list per game: 40 frames, evenly
spaced across the whole clip (index `round(i * (nb_frames - 1) / 39)`,
i = 0..39), no head slice. Both arms see the same decoded frames from the same
decode. Wall budget 3,600 s per game, both arms together; a game that exceeds it
is a BUDGET LIMIT for that game and the row continues.

## Arms

- ARM Y (production): the human-gated `src/tracking/player_detection.py` route,
  imported unedited -- `yolov8n`, its own `_infer_imgsz`, `classes=[0]`,
  `conf=0.3`. AGPL-3.0.
- ARM R (Apache): RTMDet-m through `mmdet.apis`, person class only, score 0.3.
  Checkpoint `rtmdet_m_8xb32-300e_coco_20220719_112220-229f527c.pth`, 224,299,609
  bytes, SHA-256
  `229f527ca88498e8894a778a62a878a322b4a3ea2cae09ea537d34b7e907792b`, from
  `https://download.openmmlab.com/mmdetection/v3.0/rtmdet/rtmdet_m_8xb32-300e_coco/rtmdet_m_8xb32-300e_coco_20220719_112220-229f527c.pth`.
  Apache-2.0: `https://github.com/open-mmlab/mmdetection/blob/main/LICENSE`.

The arms differ in model AND input size. This is a DETECTOR-STACK comparison,
not a single-variable ablation.

## Proxies, defined now (all denominators = decoded frames in the list)

1. `boxes_per_frame` = person boxes emitted / decoded frames. Zero-box frames
   stay in the denominator and are counted and reported separately.
2. Agreement, BOTH ways, greedy one-to-one matching on IoU, threshold 0.5:
   `agree_Y_in_R` = matched Y boxes / all Y boxes; `agree_R_in_Y` = matched R
   boxes / all R boxes. Matching is per frame, boxes sorted by descending IoU,
   each box consumed at most once. The two shares differ whenever the arms emit
   different box counts; both are reported.
3. `distinct_ids` and `median_track_length` after the SAME greedy IoU-linking
   tracker applied to both arms' boxes, identical parameters for both arms.
4. `ms_per_frame` = detector call only, warm-up frames excluded.
5. `peak_vram_mb` per arm from `torch.cuda.max_memory_allocated`; both arms are
   torch models, so that is the method for both and it is stated per arm.

## Sign convention, declared now

Higher `boxes_per_frame` is CONSISTENT WITH more detection. Higher agreement in
either direction is CONSISTENT WITH the two stacks seeing the same scene.
Longer `median_track_length` and fewer `distinct_ids` for the same box count
are CONSISTENT WITH steadier detections. CONSISTENCY IS NOT EVIDENCE.

## What this row may not conclude

SCREENING ONLY. There is no ground truth of any kind here: no labels, no
renders, no eye check. More boxes can mean more players found OR more false
boxes and this row cannot tell them apart. Low agreement says the two stacks
disagree and says nothing about which is right. G303 and G296 are the rows that
score recall against labelled frames. No recall, precision, registration,
accuracy or pass claim will be made, and neither arm will be declared better.
This row ADOPTS NOTHING, moves no production default and proposes no cutover.

## Pre-declared outcomes, all of them full successes

BLOCKED with the named versions and the exact error; a completed run in which
the arms agree closely; a completed run in which they disagree strongly; a
per-game BUDGET LIMIT at 3,600 s. The only failure mode is an unmeasured or
unlabelled number.

## Nothing moves

`src/`, `domains/`, `api/`, `kernel/`, `intel/` are read/import only.
`src/tracking/player_detection.py` and the pod `yolov8n.pt` are SHA-256 pinned
before and after. `data/registry/`, `data/tracking/` and the deployed
`/workspace/nba-ai-system` tree are not written. GPU lease: proceed only when
free VRAM >= 8,192 MiB, read and reported verbatim; `track_daemon` is never
stopped or signalled.

--- SEAL 2026-09-07 ---
SHA-256 of the LF-normalized bytes above this seal line:
76e2ebe5f9dfa35805ac40d17ec1b088b50ea101a63a7ee7692f45b4ecdb549c
