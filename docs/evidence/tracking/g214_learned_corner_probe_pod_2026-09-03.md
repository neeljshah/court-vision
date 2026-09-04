# G214 learned corner probe on pod

## Verdict

The pod **reproduced the G208 M-LSD control exactly**: 0 / 17 all-four frames,
2 / 68 corner recall, 2 / 265 proposal hits (0.75 percent), and 15.59
proposals/frame. It therefore fails the fixed >=1 / 17 bar.

This is not a global zero-shot closure. ELSED was blocked by a missing OpenCV
CMake development package without mutating the shared pod image; HAWP was
excluded by its LGPL-3.0 `easydict` dependency; DeepLSD and KpSFR weights have
no separately established licence. KpSFR's 714,819,558-byte checkpoint was not
fetched because the volume's authoritative headroom could not be queried.
These are explicit exclusions, not negative measurements. No training,
fine-tuning, production edit, deployment, daemon/keeper action, or corpus
deletion occurred.

## Fixed construct and scorer contract

- The unchanged G140 target CSV supplied all 68 target rows across all 17
  exhaustive frames, with four named roles per frame. Native dimensions were
  checked for every image: 12 at 1920x1080, four at 1280x720, and one at
  640x360.
- The G214 harness imports `score_frame` directly from G205 without changing
  it. A generic native-pixel proposal is a hit at Euclidean distance <=12 px;
  all four separately named roles are required on the same frame.
- G140 p90 label repeatability is 11.39 px. The 12 px rule is thus a
  label-noise-floor feasibility check, not evidence of production accuracy.
- M-LSD was fixed across all frames: official tiny FP32 TFLite model,
  512x512 input, `score_thr=0.10`, `dist_thr=20.0`, support extension 0 px,
  minimum intersection angle 35 degrees, and 2 px proposal deduplication.
  There was no per-frame tuning or role/homography inference.

## Candidate provenance and exclusions

Code and weight licences are recorded separately. `LICENCE-UNVERIFIED` means
the official source was inspected but no independent grant covering the
released checkpoint was found; it is not a permission inference.

| Candidate | Code licence and establishment | Weight licence and establishment | Checkpoint URL and size | Outcome |
|---|---|---|---|---|
| ELSED | Apache-2.0, official root `LICENSE`, commit `1878213b2f5f06a9261d8b1838f53d48e5fd128d` | N/A; no learned weight | None | Environmental exclusion. GCC 13.3 and CMake were present, but official `pyelsed` build stopped at `find_package(OpenCV)`: no `OpenCVConfig.cmake`/development package. The shared pod image was not changed. |
| M-LSD | Apache-2.0, official root `LICENSE`, commit `453cafa09467d0272760578d35c1fda38e8895a5` | `LICENCE-UNVERIFIED`; root software notice was not a separate checkpoint grant | `https://raw.githubusercontent.com/navervision/mlsd/453cafa09467d0272760578d35c1fda38e8895a5/tflite_models/M-LSD_512_tiny_fp32.tflite`, 2,491,732 bytes | **Run as control**. Exact G208 reproduction; not a licence-clean shipping result. |
| DeepLSD | MIT, official root `LICENSE`, commit `d873fd3619d6e44a9f625bc437ab4786057677e5` | `LICENCE-UNVERIFIED`; official README links Wireframe/MegaDepth archives but gives no separate weight licence | `https://cvg-data.inf.ethz.ch/DeepLSD/deeplsd_wireframe.tar`, previously HEAD-measured 102,898,321 bytes | Licence-based exclusion. No weight downloaded or inference run. |
| HAWP | MIT, official root `LICENSE`, commit `92ae446875ef9296fc95de7313519aabd638ebb5` | `LICENCE-UNVERIFIED`; no separate checkpoint licence found | Official HAWPv3 release URL, previously measured 47,315,279 bytes | Licence-based exclusion. Official `requirement.txt` names `easydict`; G208 established v1.13 as LGPL-3.0. It was not installed or retained. |
| KpSFR | MIT, official root `LICENSE`, commit `3d4b7968e2ab34239bf4c175f17a29efa46a691f` | `LICENCE-UNVERIFIED`; the README's code MIT statement is not an independent grant for the off-repository `.pth` | `https://cgv.cs.nthu.edu.tw/KpSFR_data/model/kpsfr.pth`, 714,819,558 bytes | Licence- and disk-safety exclusion. `quota` is unavailable and `df` is non-authoritative; only the mandated small real write was proven, not 714,819,558-byte headroom. No checkpoint fetched. |

Temporary official source clones remained outside this repository. No
third-party source or GPL-family dependency was vendored or retained.

## Results

| Candidate | All-four frames | Corner recall | Proposal precision | Proposals/frame | Acceptance |
|---|---:|---:|---:|---:|---|
| G205 stable-LSD (before) | 0 / 17 | 22 / 68 | 80 / 32,777 (0.24%) | 1,928.06 | Fail; unusable volume |
| M-LSD pod control | **0 / 17** | **2 / 68** | **2 / 265 (0.75%)** | **15.59** | **Fail**; exact G208 control reproduction |

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

The copied raw scores, summary, and five render files are in
[`g214_learned_corner_probe_pod_artifact`](g214_learned_corner_probe_pod_artifact/).

## Pod safety, packages, and cleanup

- Before any checkpoint-bearing source clone, `du -sm /workspace/nba-ai-system/data`
  was 32,379 MiB. A 4 MiB `dd` with `conv=fsync` to a unique temporary file
  inside that exact `data/` directory succeeded and was removed; `du` remained
  32,379 MiB. The equivalent `/tmp` write also succeeded.
- The post-cleanup data usage was 27,760 MiB. This background change is not
  attributed to G214: G214 only wrote and removed its own 4 MiB guard file in
  `data/`; all source, virtualenv, result, and log paths were under `/tmp`.
- Pod runtime: Python 3.12.3; base torch 2.8.0+cu128, torchvision 0.23.0+cu128,
  NumPy 2.1.2, OpenCV 5.0.0. The isolated deleted control environment used
  TensorFlow CPU 2.16.1, OpenCV headless 4.10.0, and SciPy 1.13.1.
- Before cleanup, temporary G214 paths consumed 2,997,848,602 bytes. All were
  removed after raw outputs were copied. This included **26,049,680 bytes of
  M-LSD TFLite checkpoints**, including the measured 2,491,732-byte tiny FP32
  checkpoint. KpSFR, DeepLSD, and HAWP checkpoints were never downloaded.
- The pod keeper and `scripts.platformkit.track_daemon` were observed but never
  signalled, restarted, or deployed over.

## Eye check and verification

Five evenly spaced lexical frames (0, 4, 8, 12, 16) were rendered for the
closest measured candidate, M-LSD. Inspection shows sparse generic crosses
around apparatus, players, crowd/bench texture, overlays, and unrelated court
markings; no frame has all four target corners covered. The arithmetic agrees:
only the two WNBA frames in the table have one available role.

```text
python -m pytest tests/platformkit/test_g214_learned_corner_probe_pod.py -q
1 passed in 2.04s
```

The G214 harness is 157 LOC, below the 300 LOC rail; no allowlisted file grew.
Artifacts were copied from the completed isolated pod result before pod cleanup.

## NOT VERIFIED

- ELSED, DeepLSD, HAWP, or KpSFR inference on this construct.
- A separate licence grant for any named learned checkpoint.
- Global zero-shot-route closure, labelling closure, calibration/tracking
  accuracy, deployment value, or accuracy beyond the 12 px feasibility bar.
