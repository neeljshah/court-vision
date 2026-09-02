# Soccer S1 detector determinism -- 2026-09-01

## Finding

The 27/100 fresh-versus-sealed count differences are not reproduced as
run-to-run detector nondeterminism. The original packet builder wrote a JPEG
from a `VideoCapture` frame but counted that in-memory, pre-JPEG frame. All
subsequent role-filter work instead decoded the saved packet JPEG. Those are
different detector inputs. The original source videos are no longer present in
this worktree, so the exact pre-JPEG pixels cannot be rerun; the source path
and the frozen-JPEG experiments establish the input-boundary cause.

## Checks

The detector call is `get_box_detector` reached through `SoccerAdapter` in the
original packet builder. With the current pinned `yolov8n.pt` at
`C:/Users/neelj/nba-track-a4/yolov8n.pt` (SHA-256
`f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`):

| check | result |
|---|---:|
| three fresh model loads on the same first 20 packet JPEGs | 0/20, 0/20 count differences |
| two independent pinned runs on all 100 packet JPEGs | 0/100 count differences |
| OpenCV BGR decode versus PIL RGB converted to BGR, first 20 JPEGs | 0/20 count differences |
| fresh JPEG counts versus immutable sealed CSV | 27/100 differences |

No unseeded inference randomness was observed. Fixed JPEG input also makes
preprocessing order irrelevant because calls are serial. The deterministic
Torch settings and a single OpenCV thread eliminate ordinary CPU/GPU and
thread scheduling variation; no NMS tie difference was observed in the repeat
experiments. The old model path was relative to the current working directory;
the new path is resolved from the repository module (or from an explicitly set
`CV_DETECTOR_MODEL`) before loading. Detection profile settings, including the
confidence threshold, are unchanged.

## Fix

`scripts.platformkit.detection.deterministic` now configures fixed Python,
NumPy, OpenCV, and Torch seeds; deterministic Torch/CuDNN behavior; one OpenCV
thread; disabled OpenCL; and a fixed BGR JPEG decoder. The packet builder now
writes each frame and runs the detector on that saved JPEG, so a newly sealed
packet and its later measurement use byte-identical decoded input. The role
filter uses the same helper.

The before/after 100-frame mismatch measure is therefore: **27/100** for the
immutable old seal compared with fresh packet-JPEG input, and **0/100** between
two fresh runs through the repaired deterministic packet path. The sealed CSV
was not changed or reissued.

`scripts/platformkit/test_soccer_detector_determinism.py` loads the pinned
detector and counts five packet frames twice, asserting identical counts.

## Limits

This proves repeatability for frozen packet JPEGs and this installed weight
file. It does not recreate the unavailable source-video frames, prove a prior
weight-file hash, or retroactively make the old sealed CSV comparable to the
new packet-JPEG count statistic.
