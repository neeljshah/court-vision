# G155 pod readiness census -- 2026-09-03

## Scope and verdict

This is the read-only measurement required by
[`G155_spec.md`](specs/G155_spec.md).  The only pod mutation was the single
five-byte quota probe `/workspace/.cx_g155_quota_probe_33645`, created and
deleted in the same captured command; deletion is confirmed in the raw output.
No package was installed, no code was deployed, and no process was started,
stopped, restarted, or inspected.

**Verdict: ACCEPT -- timestamped census complete; this is not a standing
readiness claim.** The orchestrator was concurrently bootstrapping the pod, so
each finding below is true only at its printed UTC observation time. No field
was rechecked after the snapshot.

The census began at **2026-09-03T14:14:47Z** and ended at
**2026-09-03T14:15:02Z**. The census host reported its container hostname as
`5a20910184ad`.

## Headline census

| Observed at (UTC) | Item | Observation |
|---|---|---|
| 2026-09-03T14:14:47Z | GPU | NVIDIA GeForce RTX 3090, 24,576 MiB VRAM |
| 2026-09-03T14:14:47Z | CPU | 256 logical CPUs |
| 2026-09-03T14:14:47Z | RAM | 1.0 TiB total; 939 GiB available |
| 2026-09-03T14:14:47Z | Python | Python 3.12.3 |
| 2026-09-03T14:14:47Z | setup package imports | 11/13 importable; `torchreid` failed because `gdown` is absent and `paddleocr` is absent |
| 2026-09-03T14:14:53Z | direct tennis runtime imports | `cv2`, `numpy`, and `torch` importable |
| 2026-09-03T14:14:56Z | workspace quota breakdown | `du -sh /workspace/*` measured the repository at 2.5G and all other listed paths at 400K or less |
| 2026-09-03T14:14:58Z | decisive quota probe | five-byte probe create succeeded and its deletion succeeded |
| 2026-09-03T14:15:01Z | detector weights | 0 matching `.pt`, `.pth`, `.onnx`, or `.engine` files; default `yolov8n.pt` absent |
| 2026-09-03T14:15:02Z | tennis input/output inventory | 0 eligible staged MP4s, 0 corpus files, 0 tracking CSVs, absent ledger and reports directory |

## Pipeline packages from `scripts/setup_pod_optimized.sh`

The denominator is the complete, exhaustive 13-package install list in
`setup_pod_optimized.sh`; hyphenated distribution names are paired with their
actual import names. This table does not substitute packages that were not in
that script.

| Observed at (UTC) | Declared package | Import name | Status |
|---|---|---|---|
| 2026-09-03T14:14:47Z | ultralytics | ultralytics | PRESENT / importable (8.4.138) |
| 2026-09-03T14:14:47Z | decord | decord | PRESENT / importable (0.6.0) |
| 2026-09-03T14:14:47Z | av | av | PRESENT / importable (18.1.0) |
| 2026-09-03T14:14:47Z | pandas | pandas | PRESENT / importable (3.0.5) |
| 2026-09-03T14:14:47Z | xgboost | xgboost | PRESENT / importable (3.4.1) |
| 2026-09-03T14:14:47Z | scikit-learn | sklearn | PRESENT / importable (1.9.0) |
| 2026-09-03T14:14:47Z | nba_api | nba_api | PRESENT / importable (1.11.4) |
| 2026-09-03T14:14:47Z | easyocr | easyocr | PRESENT / importable (1.7.2) |
| 2026-09-03T14:14:47Z | scipy | scipy | PRESENT / importable (1.18.1) |
| 2026-09-03T14:14:47Z | torchreid | torchreid | ABSENT / import fails: missing `gdown` |
| 2026-09-03T14:14:47Z | kornia | kornia | PRESENT / importable (0.8.3) |
| 2026-09-03T14:14:47Z | onnxruntime-gpu | onnxruntime | PRESENT / importable (1.29.0) |
| 2026-09-03T14:14:47Z | paddleocr | paddleocr | ABSENT / module missing |

The current tennis adapter also directly imports `cv2`, `numpy`, `pandas`, and
uses `scipy`; its ball module imports `torch` when its TrackNet implementation
is selected. `cv2` 5.0.0, `numpy` 2.1.2, and `torch` 2.8.0+cu128 imported at
2026-09-03T14:14:53Z. `pandas` and `scipy` are already counted in the exhaustive
setup-package denominator above.

## Quota and inventory

`df` was deliberately not used for headroom: the spec identifies it as a
cluster-level number that is not decisive for this volume. The literal
`du -sh /workspace/*` breakdown and the create-delete probe are reproduced in
the raw transcript.

| Observed at (UTC) | Inventory unit and eligible denominator | State |
|---|---|---|
| 2026-09-03T14:14:58Z | repository: `/workspace/nba-ai-system` | PRESENT, 2.5G, 17,271 files, 1,565,390,665 apparent file bytes; `.git` metadata absent |
| 2026-09-03T14:15:01Z | model root: all files in `data/models` | PRESENT, 46 files, 107,759 bytes (1.1M apparent size); 0 matching detector/engine weight files under the repo |
| 2026-09-03T14:15:02Z | footage corpus: all files in `data/footage_corpus` | PRESENT but empty: 0 files, 0 bytes |
| 2026-09-03T14:15:02Z | daemon stage: complete top-level `*.mp4`, with eligible defined exactly as size >= 1,000,000 bytes | PRESENT but 0 complete MP4 / **0 eligible of 0**; 0 `.part` files |
| 2026-09-03T14:15:02Z | setup overlay: all files in `/root/nba_videos` | ABSENT |
| 2026-09-03T14:15:02Z | tracking tables: all `*.csv` files in `data/tracking` | PRESENT but **0 CSV of 0**, 0 bytes |
| 2026-09-03T14:15:02Z | ledger: `/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl` | ABSENT; therefore no ledger-row denominator exists |
| 2026-09-03T14:15:02Z | reports: `data/tracking_reports` | ABSENT |

The detector configuration observed in this census shell was
`CV_DETECTOR=unset` and `CV_DETECTOR_MODEL=unset`. Following the current
`detection/shim.py`, that selects the default Ultralytics backend and its
default `yolov8n.pt` relative to the repository working directory. That file
was absent at 2026-09-03T14:15:02Z. The alternate YOLOX path is not selected by
this environment and would require an explicit model path as well as
onnxruntime.

## Exhaustive one-tennis-job prerequisite list

The construct denominator is **12 prerequisites**, enumerated exhaustively from
`track_daemon.build_command()` through `adapter_run` and
`domains.tennis.tracking.adapter`. The command is
`python -m scripts.platformkit.adapter_run tennis <video> <game_id>` from the
repository root. `PRESENT` means observed at the timestamp, not validated by a
job run; `NOT VERIFIED` identifies a requirement that would require a forbidden
write or tracking process to prove.

| # | Observed at (UTC) | Prerequisite | State at census | Basis |
|---:|---|---|---|---|
| 1 | 2026-09-03T14:14:58Z | repository checkout at `/workspace/nba-ai-system` | PRESENT | directory and all 16 named entry-path source modules present; revision unavailable because `.git` is absent |
| 2 | 2026-09-03T14:14:47Z | `python3` interpreter | PRESENT | Python 3.12.3 |
| 3 | 2026-09-03T14:14:53Z | OpenCV, NumPy, pandas, SciPy, and Torch runtime imports | PRESENT | cv2/NumPy/Torch direct import check; pandas/SciPy above |
| 4 | 2026-09-03T14:14:47Z | default Ultralytics detector package | PRESENT | `ultralytics` imported |
| 5 | 2026-09-03T14:15:02Z | selected detector artifact | ABSENT | default backend selected but `yolov8n.pt` absent; no matching weight/engine file found |
| 6 | 2026-09-03T14:15:02Z | complete staged tennis source video | ABSENT | eligible denominator is 0 complete >=1,000,000-byte `.mp4` files of 0 complete MP4 files |
| 7 | 2026-09-03T14:15:02Z | readable/decodeable staged tennis source | NOT VERIFIED | no eligible source exists; no decoder run was started |
| 8 | 2026-09-03T14:15:02Z | output parent `data` and tracking directory | PRESENT | both directories exist, mode `drwxrwxrwx` |
| 9 | 2026-09-03T14:15:02Z | writable creation of tracking/report output | NOT VERIFIED | the daemon creates these paths, but no write probe beyond the quota probe was permitted; reports directory is absent |
| 10 | 2026-09-03T14:15:02Z | tracking harness/report source and report destination | source PRESENT; destination ABSENT | `tracking_harness.py` and dependencies present; `data/tracking_reports` absent and would be created only by a run |
| 11 | 2026-09-03T14:15:02Z | retained source corpus/ledger paths used by daemon lifecycle | corpus PRESENT but empty; ledger ABSENT | daemon paths exist only in part; neither holds a job artifact |
| 12 | 2026-09-03T14:14:47Z | setup-declared package environment | INCOMPLETE: 11/13 importable | `torchreid` and `paddleocr` are unavailable; neither is directly imported by the current tennis path, but both belong to the required pipeline package census |

Result: a tennis job cannot run end to end at this census moment because the
selected detector artifact and eligible staged input are absent. The missing
ledger, corpus contents, reports directory, and two setup package imports are
also recorded rather than replaced with any old-pod substitute.

## NOT VERIFIED

- GPU execution by an actual detector was not run; doing so would instantiate a
  tracking job rather than measure readiness.
- A staged tennis video cannot be decoded because the eligible denominator was
  zero; no fixture or substitute was copied to the pod.
- Output-directory writability and report creation were not probed, because the
  one permitted pod write was reserved for quota headroom.
- Whether concurrently-installed packages, models, video, or daemon assets
  appeared after 2026-09-03T14:15:02Z is not asserted. This memo makes no
  standing claim about the moving pod.

## Reproduction commands and raw output

The remote shell was invoked exactly once as:

```sh
ssh -F "$HOME/.ssh/config.pod" -T pod 'printf %s <base64-encoded-payload> | base64 -d | /bin/sh'
```

The decoded payload below is quoted in full. `PYTHONDONTWRITEBYTECODE=1` and
`python3 -B` prevent Python bytecode writes during the package checks. The
named probe is the only write/delete operation in the payload.

```sh
set -u
stamp() { printf '\n===== %s | %s =====\n' "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; }
status_path() {
  label="$1"; path="$2"; stamp "PATH $label"
  if [ -e "$path" ] || [ -L "$path" ]; then
    printf 'PRESENT path=%s\n' "$path"
    du -sh "$path" 2>&1
    if [ -d "$path" ]; then
      find "$path" -type f -printf '%s\n' 2>/dev/null | awk '{n+=1; b+=$1} END {printf "files=%d bytes=%d\n", n+0, b+0}'
    fi
  else
    printf 'ABSENT path=%s\n' "$path"
  fi
}
probe=/workspace/.cx_g155_quota_probe_33645
trap 'rm -f "$probe"' 0 1 2 3 15
stamp CENSUS_START
printf 'host='; hostname
printf 'cwd='; pwd
stamp HARDWARE
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>&1
printf 'cpu_count='; nproc 2>&1
free -h 2>&1
printf 'python3='; python3 --version 2>&1
stamp REQUIRED_PACKAGE_IMPORTS
PYTHONDONTWRITEBYTECODE=1 python3 -B - <<'PY'
import importlib
packages = [
    ('ultralytics', 'ultralytics'), ('decord', 'decord'), ('av', 'av'),
    ('pandas', 'pandas'), ('xgboost', 'xgboost'), ('scikit-learn', 'sklearn'),
    ('nba_api', 'nba_api'), ('easyocr', 'easyocr'), ('scipy', 'scipy'),
    ('torchreid', 'torchreid'), ('kornia', 'kornia'),
    ('onnxruntime-gpu', 'onnxruntime'), ('paddleocr', 'paddleocr'),
]
for declared, module_name in packages:
    try:
        module = importlib.import_module(module_name)
        print(f'{declared}\t{module_name}\tIMPORTABLE\t{getattr(module, "__version__", "imported")}')
    except Exception as exc:
        print(f'{declared}\t{module_name}\tNOT_IMPORTABLE\t{type(exc).__name__}: {exc}')
PY
stamp DIRECT_RUNTIME_IMPORTS
PYTHONDONTWRITEBYTECODE=1 python3 -B - <<'PY'
import importlib
for name in ('cv2', 'numpy', 'torch'):
    try:
        module = importlib.import_module(name)
        print(f'{name}\tIMPORTABLE\t{getattr(module, "__version__", "imported")}')
    except Exception as exc:
        print(f'{name}\tNOT_IMPORTABLE\t{type(exc).__name__}: {exc}')
PY
stamp QUOTA_DU_WORKSPACE_GLOB
LC_ALL=C du -sh /workspace/* 2>&1
stamp QUOTA_PROBE
if (umask 077; printf 'G155\n' > "$probe"); then
  printf 'CREATE_OK path=%s bytes=' "$probe"; wc -c < "$probe"
  rm -f "$probe"
  if [ -e "$probe" ]; then printf 'DELETE_FAILED path=%s\n' "$probe"; else printf 'DELETE_OK path=%s\n' "$probe"; fi
else
  printf 'CREATE_FAILED path=%s\n' "$probe"
fi
trap - 0
status_path REPOSITORY /workspace/nba-ai-system
stamp REPOSITORY_REVISION
if [ -d /workspace/nba-ai-system/.git ]; then git -C /workspace/nba-ai-system rev-parse HEAD 2>&1; else echo ABSENT_GIT_METADATA; fi
status_path MODEL_ROOT /workspace/nba-ai-system/data/models
stamp MODEL_WEIGHT_FILES
find /workspace/nba-ai-system -type f \( -iname '*.pt' -o -iname '*.pth' -o -iname '*.onnx' -o -iname '*.engine' \) -printf '%s %p\n' 2>/dev/null | sort -n
stamp DETECTOR_ENVIRONMENT
printf 'CV_DETECTOR=%s\n' "${CV_DETECTOR-unset}"
printf 'CV_DETECTOR_MODEL=%s\n' "${CV_DETECTOR_MODEL-unset}"
status_path YOLOV8_DEFAULT_CWD_MODEL /workspace/nba-ai-system/yolov8n.pt
status_path FOOTAGE_CORPUS /workspace/nba-ai-system/data/footage_corpus
status_path DAEMON_STAGE /workspace/nba-ai-system/data/footage_bridge
stamp DAEMON_STAGE_ELIGIBILITY
printf 'complete_mp4_total='; find /workspace/nba-ai-system/data/footage_bridge -maxdepth 1 -type f -name '*.mp4' -printf '.' | wc -c
printf 'complete_mp4_eligible_bytes_ge_1000000='; find /workspace/nba-ai-system/data/footage_bridge -maxdepth 1 -type f -name '*.mp4' -size +999999c -printf '.' | wc -c
printf 'partial_uploads='; find /workspace/nba-ai-system/data/footage_bridge -maxdepth 1 -type f -name '*.part' -printf '.' | wc -c
status_path SETUP_OVERLAY_VIDEOS /root/nba_videos
status_path TRACKING_TABLES /workspace/nba-ai-system/data/tracking
stamp TRACKING_TABLES_CSV
find /workspace/nba-ai-system/data/tracking -type f -name '*.csv' -printf '%s\n' 2>/dev/null | awk '{n+=1; b+=$1} END {printf "csv_count=%d csv_bytes=%d\n", n+0, b+0}'
status_path TRACKING_LEDGER /workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl
stamp LEDGER_ROWS
if [ -f /workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl ]; then wc -l /workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl; else echo LEDGER_ABSENT; fi
stamp TENNIS_PATH_SOURCE_PREREQUISITES
for path in /workspace/nba-ai-system/scripts/platformkit/track_daemon.py /workspace/nba-ai-system/scripts/platformkit/adapter_run.py /workspace/nba-ai-system/domains/tennis/tracking/adapter.py /workspace/nba-ai-system/scripts/platformkit/detection/shim.py /workspace/nba-ai-system/scripts/platformkit/calibration/keypoint_calib.py /workspace/nba-ai-system/domains/tennis/tracking/ball.py /workspace/nba-ai-system/domains/tennis/tracking/camera_lock.py /workspace/nba-ai-system/domains/tennis/tracking/court_lines.py /workspace/nba-ai-system/domains/tennis/tracking/frame_manifest.py /workspace/nba-ai-system/domains/tennis/tracking/identity.py /workspace/nba-ai-system/domains/tennis/tracking/rally_features.py /workspace/nba-ai-system/domains/tennis/tracking/segmenter.py /workspace/nba-ai-system/scripts/platformkit/coordinate_provenance.py /workspace/nba-ai-system/scripts/platformkit/tracking_harness.py /workspace/nba-ai-system/scripts/platformkit/tracking_schema.py /workspace/nba-ai-system/scripts/platformkit/tracking_media_inventory.py /workspace/nba-ai-system/scripts/platformkit/tracking_timebase.py; do
  if [ -f "$path" ]; then printf 'PRESENT %s\n' "$path"; else printf 'ABSENT %s\n' "$path"; fi
done
stamp OUTPUT_PATH_METADATA
for path in /workspace/nba-ai-system/data /workspace/nba-ai-system/data/tracking /workspace/nba-ai-system/data/tracking_reports; do
  if [ -e "$path" ]; then stat -c 'PRESENT mode=%A owner=%U:%G path=%n' "$path" 2>&1; else printf 'ABSENT path=%s\n' "$path"; fi
done
stamp CENSUS_END
```

Raw output (stderr was included for every command):

```text
===== CENSUS_START | 2026-09-03T14:14:47Z =====
host=5a20910184ad
cwd=/root

===== HARDWARE | 2026-09-03T14:14:47Z =====
NVIDIA GeForce RTX 3090, 24576
cpu_count=256
               total        used        free      shared  buff/cache   available
Mem:           1.0Ti        67Gi       221Gi       174Mi       729Gi       939Gi
Swap:             0B          0B          0B
python3=Python 3.12.3

===== REQUIRED_PACKAGE_IMPORTS | 2026-09-03T14:14:47Z =====
ultralytics ultralytics IMPORTABLE 8.4.138
decord decord IMPORTABLE 0.6.0
av av IMPORTABLE 18.1.0
pandas pandas IMPORTABLE 3.0.5
xgboost xgboost IMPORTABLE 3.4.1
scikit-learn sklearn IMPORTABLE 1.9.0
nba_api nba_api IMPORTABLE 1.11.4
easyocr easyocr IMPORTABLE 1.7.2
scipy scipy IMPORTABLE 1.18.1
torchreid torchreid NOT_IMPORTABLE ModuleNotFoundError: No module named 'gdown'
kornia kornia IMPORTABLE 0.8.3
onnxruntime-gpu onnxruntime IMPORTABLE 1.29.0
paddleocr paddleocr NOT_IMPORTABLE ModuleNotFoundError: No module named 'paddleocr'

===== DIRECT_RUNTIME_IMPORTS | 2026-09-03T14:14:53Z =====
cv2 IMPORTABLE 5.0.0
numpy IMPORTABLE 2.1.2
torch IMPORTABLE 2.8.0+cu128

===== QUOTA_DU_WORKSPACE_GLOB | 2026-09-03T14:14:56Z =====
2.0K /workspace/bootstrap.log
0 /workspace/keep_track_daemon.log
2.0K /workspace/keep_track_daemon.sh
512 /workspace/keepalive.log
2.5G /workspace/nba-ai-system
399K /workspace/pod_md5.txt
400K /workspace/pod_md5n.txt
0 /workspace/track_daemon.log
512 /workspace/track_daemon.pid

===== QUOTA_PROBE | 2026-09-03T14:14:58Z =====
CREATE_OK path=/workspace/.cx_g155_quota_probe_33645 bytes=5
DELETE_OK path=/workspace/.cx_g155_quota_probe_33645

===== PATH REPOSITORY | 2026-09-03T14:14:58Z =====
PRESENT path=/workspace/nba-ai-system
2.5G /workspace/nba-ai-system
files=17271 bytes=1565390665

===== REPOSITORY_REVISION | 2026-09-03T14:15:01Z =====
ABSENT_GIT_METADATA

===== PATH MODEL_ROOT | 2026-09-03T14:15:01Z =====
PRESENT path=/workspace/nba-ai-system/data/models
1.1M /workspace/nba-ai-system/data/models
files=46 bytes=107759

===== MODEL_WEIGHT_FILES | 2026-09-03T14:15:01Z =====

===== DETECTOR_ENVIRONMENT | 2026-09-03T14:15:02Z =====
CV_DETECTOR=unset
CV_DETECTOR_MODEL=unset

===== PATH YOLOV8_DEFAULT_CWD_MODEL | 2026-09-03T14:15:02Z =====
ABSENT path=/workspace/nba-ai-system/yolov8n.pt

===== PATH FOOTAGE_CORPUS | 2026-09-03T14:15:02Z =====
PRESENT path=/workspace/nba-ai-system/data/footage_corpus
512 /workspace/nba-ai-system/data/footage_corpus
files=0 bytes=0

===== PATH DAEMON_STAGE | 2026-09-03T14:15:02Z =====
PRESENT path=/workspace/nba-ai-system/data/footage_bridge
512 /workspace/nba-ai-system/data/footage_bridge
files=0 bytes=0

===== DAEMON_STAGE_ELIGIBILITY | 2026-09-03T14:15:02Z =====
complete_mp4_total=0
complete_mp4_eligible_bytes_ge_1000000=0
partial_uploads=0

===== PATH SETUP_OVERLAY_VIDEOS | 2026-09-03T14:15:02Z =====
ABSENT path=/root/nba_videos

===== PATH TRACKING_TABLES | 2026-09-03T14:15:02Z =====
PRESENT path=/workspace/nba-ai-system/data/tracking
512 /workspace/nba-ai-system/data/tracking
files=0 bytes=0

===== TRACKING_TABLES_CSV | 2026-09-03T14:15:02Z =====
csv_count=0 csv_bytes=0

===== PATH TRACKING_LEDGER | 2026-09-03T14:15:02Z =====
ABSENT path=/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl

===== LEDGER_ROWS | 2026-09-03T14:15:02Z =====
LEDGER_ABSENT

===== TENNIS_PATH_SOURCE_PREREQUISITES | 2026-09-03T14:15:02Z =====
PRESENT /workspace/nba-ai-system/scripts/platformkit/track_daemon.py
PRESENT /workspace/nba-ai-system/scripts/platformkit/adapter_run.py
PRESENT /workspace/nba-ai-system/domains/tennis/tracking/adapter.py
PRESENT /workspace/nba-ai-system/scripts/platformkit/detection/shim.py
PRESENT /workspace/nba-ai-system/scripts/platformkit/calibration/keypoint_calib.py
PRESENT /workspace/nba-ai-system/domains/tennis/tracking/ball.py
PRESENT /workspace/nba-ai-system/domains/tennis/tracking/camera_lock.py
PRESENT /workspace/nba-ai-system/domains/tennis/tracking/court_lines.py
PRESENT /workspace/nba-ai-system/domains/tennis/tracking/frame_manifest.py
PRESENT /workspace/nba-ai-system/domains/tennis/tracking/identity.py
PRESENT /workspace/nba-ai-system/domains/tennis/tracking/rally_features.py
PRESENT /workspace/nba-ai-system/domains/tennis/tracking/segmenter.py
PRESENT /workspace/nba-ai-system/scripts/platformkit/coordinate_provenance.py
PRESENT /workspace/nba-ai-system/scripts/platformkit/tracking_harness.py
PRESENT /workspace/nba-ai-system/scripts/platformkit/tracking_schema.py
PRESENT /workspace/nba-ai-system/scripts/platformkit/tracking_media_inventory.py
PRESENT /workspace/nba-ai-system/scripts/platformkit/tracking_timebase.py

===== OUTPUT_PATH_METADATA | 2026-09-03T14:15:02Z =====
PRESENT mode=drwxrwxrwx owner=root:root path=/workspace/nba-ai-system/data
PRESENT mode=drwxrwxrwx owner=root:root path=/workspace/nba-ai-system/data/tracking
ABSENT path=/workspace/nba-ai-system/data/tracking_reports

===== CENSUS_END | 2026-09-03T14:15:02Z =====
```

## Verifier-contract self-check

Contract: [`VERIFIER_CONTRACT.md`](VERIFIER_CONTRACT.md). Q8 premise first is
satisfied by this initial timestamped census; the initial state was not assumed.

| Section B condition | Self-check |
|---|---|
| B1 circular metric | Not applicable: no filtered metric or exclusion; every listed inventory unit is counted. |
| B2 non-additive schema | No schema or code change. |
| B3 fall-through loss | No gate or workflow change. |
| B4 re-claim loop | No claim or lifecycle change. |
| B5 pre-verification deploy | No file was copied or deployed to the pod. |
| B6 orphans | No module moved or retired. |
| B7 head-slice evidence | Not applicable: the construct census exhaustively enumerates its 12 prerequisite categories and all package/inventory units. |
| B8 self-fit as independent | No fitted result or comparison. |
| B9 degenerate denominator | Denominators are explicit: 13 setup packages, 12 constructed prerequisites, and the applicable zero-count inventory populations. |
| B10 moved bar | No threshold, gate, coordinate contract, or verdict was changed. |

A7: every evidence path named by this memo existed at pre-commit verification
time and is staged in this evidence commit:
`docs/evidence/tracking/g155_pod_readiness_census_2026-09-03.md`,
`docs/evidence/tracking/specs/G155_spec.md`, and
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. No external or pod-only artifact
is cited as evidence. Q7 applies the construct exception: all 12 prerequisite
categories, their 16 source-module members, and all 13 declared package members
are enumerated; reproduction replaces render sampling. No test was run because
this landing changes no code.
