# G298 - detector capacity and input resolution

## Verdict

MEASUREMENT COMPLETE; independent verifier acceptance is pending. n=15 frames, 143 eligible located-foot observations, 3 arms, 3 tolerances, 1 clip, 1 span, 1 shot, 1 SINGLE MODEL LOCATOR ground truth. There is no pass bar. This row MEASURES an alternative configuration and ADOPTS NOTHING.

At 100 px, fresh A/B/C recall is 0.174825/0.510490/0.454545 (each eligible denominator 143 located feet), so input resolution contributes +0.335664 (+33.57 percentage points) and added model capacity -0.055944 (-5.59 percentage points); the historical G285b 17/143 = 0.119 uses retained tracking footpoints and is not an interchangeable fresh-A baseline.

## Machine, inputs, and controlled design

Detection: pod RTX 3090, compute-only scratch `/workspace/wt/a6`, because source footage, weights, and GPU are there. Arithmetic and tests: local `C:/Users/neelj/nba-track-a6`, branch `track-a6`.

The ONLY difference between A and B is input resolution; the ONLY difference between B and C is model capacity. All use classes=[0], conf=0.3, CUDA device=0, half=True, verbose=False, batch-one calls, and the same installed Ultralytics defaults. No crop, court subset, augmentation, or downstream box exclusion is introduced.

| Arm | Model | imgsz |
| --- | --- | ---: |
| A | yolov8n | 640 |
| B | yolov8n | 1920 |
| C | yolov8x | 1920 |

The unchanged human-gated `src/tracking/player_detection.py` is IMPORTED and RUN: `FeetDetector([])` and `get_players_pos`. A capture wrapper records the raw model boxes returned by that method's exact inference call, before its downstream color/map/tracking logic. Only the scratch detector instance's input-size value (B/C) and model object (C) change. This is the production detection configuration, not an end-to-end tracking rerun. The source comment says "yolov8x is slower to load and only marginally better for tracking" without citing a measurement. 1920 to 640 is 3x linear / 9x area downscaling; a 150 px player becomes 50 px tall.

Frame list (15 unique frames, derived from the committed located-feet CSV): 19630, 19879, 20190, 20440, 20689, 20938, 21187, 21499, 21686, 21935, 22247, 22496, 22683, 22994, 23368.

Frames were decoded once by OpenCV with zero-based frame seeks and next-frame index assertions, then identical BGR arrays were copied for every inference call. Every decoded-frame SHA-256 is in each arm summary. G278's source-video SHA-256 and 1920x1080 at 30 fps were asserted. The locator originally viewed G278 JPEG derivatives of these source frames; this row uses original-video decodes, with identical pixels across arms.

Input identity: `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2931985407 bytes, 1920x1080, SHA-256 `f361ad7a32ccc6d98ae8e98eee0b090f5e121f9425182e24a31c282ca226c678`.

## Determinism before comparison

A and A_repeat detection CSVs are byte-identical: **True**. The check was recorded before B/C ran and before local recall arithmetic. The CSV preserves box order, coordinates, confidence, frame keys and bottom-centre feet. Both model instances were freshly constructed. Environment and route identities are archived in A_summary.json; both CSV hashes are in determinism.json. G241's 808/1,201 differing tracking records do not establish single-frame detector repeatability; this check measures it directly. B and C each have one draw; their own repeatability is NOT VERIFIED.

## Recall against the committed locator

Footpoint = bottom-centre of each box, using production's integer truncation and image clipping: x=(max(0,int(x1))+min(1920,int(x2)))//2; y=min(1080,int(y2)). A located foot matches if ANY same-frame detection footpoint is within the inclusive tolerance. No one-to-one assignment; no located observation is removed, including zero-detection frames. This row has NO eye labels and NO blind judging: it is arithmetic against committed coordinates, not new visual validation.

| Arm | Tolerance px | Matched / eligible denominator | Recall |
| --- | ---: | --- | ---: |
| A | 25 | 3 / 143 eligible located feet | 0.020979 |
| A | 50 | 8 / 143 eligible located feet | 0.055944 |
| A | 100 | 25 / 143 eligible located feet | 0.174825 |
| B | 25 | 15 / 143 eligible located feet | 0.104895 |
| B | 50 | 36 / 143 eligible located feet | 0.251748 |
| B | 100 | 73 / 143 eligible located feet | 0.510490 |
| C | 25 | 14 / 143 eligible located feet | 0.097902 |
| C | 50 | 30 / 143 eligible located feet | 0.209790 |
| C | 100 | 65 / 143 eligible located feet | 0.454545 |

## Paired exact tests

McNemar's two-sided EXACT conditional binomial test uses the per-foot detected/not indicator. An unpaired two-proportion test would be WRONG because both arms observe the SAME located feet on the SAME frames, so the two samples are dependent. The tests use discordant pairs only. All p-values are nominal; NO multiplicity correction across the three tolerances. Repeated observations within frames/players are not independent population samples, and these nominal per-foot tests do not adjust for that clustering.

| Pair | Tolerance px | Lost | Gained | Discordant | Nominal exact p |
| --- | ---: | ---: | ---: | ---: | ---: |
| A_vs_B | 25 | 1 | 13 | 14 | 0.001831054688 |
| A_vs_B | 50 | 1 | 29 | 30 | 5.774199963e-08 |
| A_vs_B | 100 | 0 | 48 | 48 | 7.105427358e-15 |
| B_vs_C | 25 | 5 | 4 | 9 | 1 |
| B_vs_C | 50 | 7 | 1 | 8 | 0.0703125 |
| B_vs_C | 100 | 10 | 2 | 12 | 0.03857421875 |

All six comparisons contain 143 paired eligible located-foot observations; `paired_feet.csv` archives every nearest distance and detected/not indicator.

## Box volume and nearest distances

| Arm | Total raw person boxes | Mean boxes / 15 frames | Median nearest distance / 143 eligible feet (px) |
| --- | ---: | ---: | ---: |
| A | 112 | 7.466667 | 202.237484 |
| B | 617 | 41.133333 | 96.462428 |
| C | 470 | 31.333333 | 107.837841 |

| Source frame | A boxes | B boxes | C boxes |
| ---: | ---: | ---: | ---: |
| 19630 | 8 | 45 | 36 |
| 19879 | 7 | 61 | 46 |
| 20190 | 3 | 62 | 42 |
| 20440 | 11 | 48 | 42 |
| 20689 | 10 | 28 | 45 |
| 20938 | 9 | 12 | 13 |
| 21187 | 5 | 18 | 15 |
| 21499 | 10 | 61 | 50 |
| 21686 | 11 | 62 | 37 |
| 21935 | 8 | 62 | 37 |
| 22247 | 5 | 80 | 37 |
| 22496 | 6 | 52 | 38 |
| 22683 | 7 | 6 | 6 |
| 22994 | 4 | 8 | 5 |
| 23368 | 8 | 12 | 21 |

A recall gain bought by simply emitting far more boxes is not a better detector. Recall is not precision: a bigger model may also emit more false boxes. These counts expose box-volume changes, but do not measure true precision.

Resolution is the dominant configuration contribution on this fixed sample: at 100 px it gains 48 located feet and loses none (nominal exact p=7.1054273576e-15), while capacity gains 2 and loses 10 (nominal exact p=0.03857421875). B emits 5.51 times A's boxes; C emits fewer boxes than B and has lower agreement recall. Thus the 640 setting is implicated in missed locator agreement; more capacity adds no recall benefit here, and detector quality overall remains unmeasured. No setting is adopted or proposed for production.

## Historical comparison and limitations

G285b recorded 3/143 = 0.021, 7/143 = 0.049, and 17/143 = 0.119 (eligible denominator 143 located feet each time) against 88 retained G270-on-court G267 tracking footpoints. G298 scores all fresh raw person detections as specified. The reconciled G273-VS-G285b ledger row reinstated G285b as a localisation measure, reinterpreted G273's neighbourhood criterion, and withdrew G284's 0.416 bound. None of those counts is changed. A difference between historical G285b and fresh A cannot be attributed to input resolution or model capacity, since neither setting differs between those two baselines.

At 100 px the historical-to-fresh-A difference is 8/143 = +0.055944 (+5.59 percentage points; eligible denominator 143 located feet), kept separate from the A-to-B resolution and B-to-C capacity contributions. It is not a configuration benefit. This preserves G285b's committed 17/143 figure rather than forcing the fresh raw-detection arm to reproduce a retained subset.

The ground truth is 143 foot observations on 15 frames from a SINGLE MODEL LOCATOR, not a human, and it is the same locator whose judgements the programme's other rows rest on -- so this row measures agreement with that locator, and A DETECTOR THAT FINDS PLAYERS THE LOCATOR MISSED WILL BE SCORED AS WRONG. That bounds every recall figure here from above and below. Specifically, unlocated correct detections receive no recall credit; a detector-side unmatched box cannot be certified false by this incomplete reference.

All 15 frames lie inside frames 19599-23399, and G278 measured that span friendlier than its own clip (0.836 vs 0.656, p=0.0078), so nothing may be quoted clip-wide. ONE clip, ONE shot. A bigger model at a higher input size is SLOWER and this row measures NO TIMING, so it cannot say the alternative is practical, only whether it detects more.

## Operational receipts and bytes

GPU gate: free VRAM, not a lane count. Initial exact query read 356 MiB, 24576 MiB: 24,220 MiB free, above the runner's 6,000 MiB operational budget. No process was killed, interrupted, or restarted. No corpus source or bridge partial was deleted. The original `~/bin/pod_run a6 --ship ... --fetch ... -- ...` stalled in its legacy MooseFS du walk. That process was left alone. `g298_wrapper.py` produces the worktree-local `g298_pod_run.sh` from that exact installed wrapper, replacing the disk guard with dd conv=fsync. UNKNOWN is never interpreted as zero. This is an explicit operational adaptation, not an unmodified-wrapper claim. Shipping, scratch execution, and fetching are otherwise preserved. The atomic execution.lock prevents the delayed wrapper from duplicating detection.

The bulk fsync-only wrapper completed staging first and ran all four inference passes successfully (`pod_run_20260904220142.log`, POD_RUN_DONE rc=0). A later minimal staging attempt failed on a missing association import before inference; its corrected launcher and the delayed original wrapper both skipped the already-claimed experiment. Early fetch failures were from those duplicate launchers, before C existed; the successful compute wrapper fetched every final CSV and summary. The outer local launch scripts reported a trailing shell EOF after the commands returned because the recovery revision changed the file while they waited; the current scripts pass bash -n, and the pod computation and complete fetch succeeded.

Code identity caveat: a delayed bulk staging pass copied an import-bootstrap-only revision of the harness while the original process was decoding. The recorded on-disk hash matches runner_live_snapshot.py.txt. runner_launch_version.py.txt reconstructs the exact prelaunch source from this session's patches; route_identity_notes.json records both hashes and their difference. The launch version imports src.tracking.player_detection normally; the recovery version imports the same unchanged file directly to avoid unrelated package initializers. No executed detector call, frame handling, footpoint rule, model setting, or scoring logic changed. The gated player_detection.py and plot_tools.py hashes are unchanged. The live snapshot is a disk identity receipt, not a claim that Python hot-reloaded the bootstrap.

Scratch retained file sizes (not filesystem allocation or whole-volume usage):

```json
{
  "retained_files_bytes": {
    "g298_scratch/yolov8x.pt": 136890692,
    "g298_scratch/fsync_probe.bin": 8388608,
    "g298_scratch/wrapper_fsync_probe.bin": 8388608,
    "g298_scratch/preflight_fsync_probe.bin": 8388608,
    "g298_scratch/matplotlib/fontlist-v3.11.0.json": 29302,
    "g298_scratch/Ultralytics/settings.json": 441
  },
  "retained_bytes": 162086259,
  "bytes_freed_by_harness": 0,
  "nano_unchanged": {
    "path": "/workspace/nba-ai-system/yolov8n.pt",
    "bytes": 6549796,
    "sha256": "f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36"
  }
}
```

The original wrapper wrote then freed its own 8,388,608-byte quota probe; the detection harness freed 0 bytes. Whole-volume net growth is UNKNOWN because there is no reliable before/after MooseFS census; re-staging the existing Python tree must not be counted as wholly new data. The scratch manifest reports the exact retained new weights, fsync probes and config/cache bytes. Additional task output and local artifact byte sizes are in artifact_inventory.json.

Every captured GPU/disk probe is pasted below; status receipts also retain intermediate GPU readings. Empty du output is UNKNOWN, never 0, and never grounds for stopping.

Task-owned retained additions: **162,286,343 bytes** (including the 162,086,259-byte model/probe/cache scratch subtotal); bytes freed: **8,388,608**, solely the original wrapper's quota probe. `pod_owned_bytes.json` lists every counted file. This excludes unknown net changes from the broad restaging of pre-existing Python files.

`docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/earlier_probes.txt` (GPU/disk and run-status lines; full raw receipt archived)

```text
Earlier probe stdout/stderr preserved from tool receipts before the recovery launcher reused preflight.log.

Initial exact query:
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
356 MiB, 24576 MiB

First preflight dd if=/dev/zero of=/workspace/wt/a6/g298_scratch/preflight_fsync_probe.bin bs=1M count=8 conv=fsync:
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.202646 s, 41.4 MB/s

Original installed pod_run's legacy non-fsync quota probe (its tail output):
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.296593 s, 28.3 MB/s

Second preflight, same exact GPU query and dd conv=fsync command:
356 MiB, 24576 MiB
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.293816 s, 28.6 MB/s

Third preflight, same exact GPU query and dd conv=fsync command:
356 MiB, 24576 MiB
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.20667 s, 40.6 MB/s

Fourth preflight is in preflight.log. Wrapper fsync probes are in pod_run_fsync.log,
attempt_import_failure.txt and pod_run_minimal.log; the inference runner's probes
are in probes.json and compute_complete.log. Intermediate exact GPU queries all
read 356 MiB, 24576 MiB; retained status receipts are status.txt,
status_staging.txt and status_running.txt. No query was used to wait on a lane.

```

`docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/preflight.log` (GPU/disk and run-status lines; full raw receipt archived)

```text
356 MiB, 24576 MiB
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.288919 s, 29.0 MB/s

```

`docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/pod_run.log` (GPU/disk and run-status lines; full raw receipt archived)

```text
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.296593 s, 28.3 MB/s
POD /workspace 43386 MB used of 50000; /workspace/wt 7457 MB
WARNING /workspace/wt above 3 GB -- ping the tracking session and clean old pod_run logs
SHIPPED
__init__.py
__pycache__
_pts_oof_harness.py
POD_PID=3294971
== pod log tail (/workspace/wt/a6/pod_run_20260904215838.log)
G298 already claimed; no duplicate detection run launched
POD_RUN_DONE rc=0

scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/C.csv: No such file or directory
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/C_summary.json: No such file or directory
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/scratch_bytes.json: No such file or directory
```

`docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/pod_run_fsync.log` (GPU/disk and run-status lines; full raw receipt archived)

```text
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.205921 s, 40.7 MB/s
POD /workspace UNKNOWN; /workspace/wt UNKNOWN (MooseFS walk omitted; successful fsync is the disk gate)
SHIPPED
__init__.py
__pycache__
_pts_oof_harness.py
POD_PID=3291601
== pod log tail (/workspace/wt/a6/pod_run_20260904220142.log)
ARM A_repeat: 112 detections, 15 frames
A byte-identical repeat: True; checked before B/C
ARM B: 617 detections, 15 frames

ARM C: 470 detections, 15 frames
POD_RUN_DONE rc=0

```

`docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/pod_run_minimal.log` (GPU/disk and run-status lines; full raw receipt archived)

```text
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.291967 s, 28.7 MB/s
POD /workspace UNKNOWN; /workspace/wt UNKNOWN (MooseFS walk omitted; successful fsync is the disk gate)
SHIPPED
__init__.py
__pycache__
_pts_oof_harness.py
POD_PID=3292435
== pod log tail (/workspace/wt/a6/pod_run_20260904221053.log)
G298 already claimed; no duplicate detection run launched
POD_RUN_DONE rc=0

scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/A.csv: No such file or directory
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/A_summary.json: No such file or directory
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/A_repeat.csv: No such file or directory
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/A_repeat_summary.json: No such file or directory
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/B.csv: No such file or directory
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/B_summary.json: No such file or directory
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/C.csv: No such file or directory
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/C_summary.json: No such file or directory
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/determinism.json: No such file or directory
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/scratch_bytes.json: No such file or directory
nd_input_resolution_artifact/determinism.json: No such file or directory
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/scratch_bytes.json: No such file or directory
```

`docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/attempt_import_failure.txt` (GPU/disk and run-status lines; full raw receipt archived)

```text
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.291681 s, 28.8 MB/s
POD /workspace UNKNOWN; /workspace/wt UNKNOWN (MooseFS walk omitted; successful fsync is the disk gate)
SHIPPED
__init__.py
__pycache__
_pts_oof_harness.py
POD_PID=3291962
== pod log tail (/workspace/wt/a6/pod_run_20260904220933.log)
Traceback (most recent call last):
  File "/workspace/wt/a6/g298_code/scripts/platformkit/tracking/g298_detect.py", line 14, in <module>
    from scripts.platformkit.tracking.g298_compare import bottom_centre, read_locations, sha256, write_csv
  File "/workspace/wt/a6/g298_code/scripts/platformkit/tracking/__init__.py", line 3, in <module>
    from .association import Track, Tracker, apply_motion, associate
ModuleNotFoundError: No module named 'scripts.platformkit.tracking.association'
POD_RUN_DONE rc=1

RSS_PEAK_KB=VmHWM: 2075356 kB
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/A.csv: No such file or directory
FETCH FAILED docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/A.csv
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/A_summary.json: No such file or directory
FETCH FAILED docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/A_summary.json
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/A_repeat.csv: No such file or directory
FETCH FAILED docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/A_repeat.csv
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/A_repeat_summary.json: No such file or directory
FETCH FAILED docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/A_repeat_summary.json
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/B.csv: No such file or directory
FETCH FAILED docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/B.csv
scp: /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/B_summary.json: No such file or directory

```

`docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/status.txt` (GPU/disk and run-status lines; full raw receipt archived)

```text
356 MiB, 24576 MiB
-rw-rw-rw- 1 root root    702 Sep  5 02:42 /workspace/wt/a6/pod_run_20260904212418.log
-rw-rw-rw- 1 root root 361327 Sep  4 23:24 /workspace/wt/a6/pod_run_20260904162327.log
-rw-rw-rw- 1 root root 361327 Sep  4 23:22 /workspace/wt/a6/pod_run_20260904161928.log
3288426     264 bash -c du -sm /workspace 2>/dev/null | cut -f1
3288427     264 du -sm /workspace
3288756     180 bash -c du -sm /workspace/wt 2>/dev/null | cut -f1
3288757     180 du -sm /workspace/wt
3289115      78 bash -c du -sm /workspace/wt 2>/dev/null | cut -f1
3289116      78 du -sm /workspace/wt
3289341      37 du -sm /workspace

```

`docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/status_staging.txt` (GPU/disk and run-status lines; full raw receipt archived)

```text
356 MiB, 24576 MiB
-rw-rw-rw- 1 root root    702 Sep  5 02:42 /workspace/wt/a6/pod_run_20260904212418.log
-rw-rw-rw- 1 root root 361327 Sep  4 23:24 /workspace/wt/a6/pod_run_20260904162327.log
-rw-rw-rw- 1 root root 361327 Sep  4 23:22 /workspace/wt/a6/pod_run_20260904161928.log
    PID     ELAPSED STAT WCHAN  COMMAND
3288161       07:29 Ss   reques tar -x --no-same-owner
3288210       07:21 Rs   -      tar -x --no-same-owner
3288357       06:38 Rs   -      tar -x --no-same-owner
3288576       05:45 Rs   -      tar -x --no-same-owner
3289097       03:17 Ss   -      tar -x --no-same-owner
3290071       00:39 Ss   -      tar -x --no-same-owner
3290092       00:38 Rs   -      tar -x --no-same-owner
3289115     196 bash -c du -sm /workspace/wt 2>/dev/null | cut -f1
3289116     196 du -sm /workspace/wt
3289341     154 du -sm /workspace
3289837      87 bash -c du -sm /workspace 2>/dev/null | cut -f1
3289838      87 du -sm /workspace
3290013      49 bash -c du -sm /workspace/wt 2>/dev/null | cut -f1
3290014      49 du -sm /workspace/wt

```

`docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/status_running.txt` (GPU/disk and run-status lines; full raw receipt archived)

```text
356 MiB, 24576 MiB
-rw-rw-rw- 1 root root     76 Sep  5 03:11 /workspace/wt/a6/pod_run_20260904221053.log
-rw-rw-rw- 1 root root    749 Sep  5 03:10 /workspace/wt/a6/pod_run_20260904220142.log
-rw-rw-rw- 1 root root    509 Sep  5 03:09 /workspace/wt/a6/pod_run_20260904220933.log
    PID     ELAPSED STAT WCHAN  COMMAND
3291434       04:48 Ss   reques tar -x --no-same-owner
3293462       01:05 Rs   reques tar -x --no-same-owner
3293803       00:36 Ss   reques tar -x --no-same-owner
3291601     257 bash -c cd /workspace/wt/a6 && nohup bash -c 'cd /workspace/wt/a6 && PYTHONPATH=/workspace/wt/a6:/workspace/wt/_pylib PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=298 YOLO_CONFIG_DIR=/workspace/wt/a6/g298_scratch MPLCONFIGDIR=/workspace/wt/a6/g298_scratch/matplotlib python -m scripts.platformkit.tracking.g298_detect --video /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 --located-feet /workspace/wt/a6/docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv --output /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact; echo POD_RUN_DONE rc=$?' > /workspace/wt/a6/pod_run_20260904220142.log 2>&1 & echo POD_PID=$!
3291602     257 bash -c cd /workspace/wt/a6 && PYTHONPATH=/workspace/wt/a6:/workspace/wt/_pylib PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=298 YOLO_CONFIG_DIR=/workspace/wt/a6/g298_scratch MPLCONFIGDIR=/workspace/wt/a6/g298_scratch/matplotlib python -m scripts.platformkit.tracking.g298_detect --video /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 --located-feet /workspace/wt/a6/docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv --output /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact; echo POD_RUN_DONE rc=$?
3291604     256 python -m scripts.platformkit.tracking.g298_detect --video /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 --located-feet /workspace/wt/a6/docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv --output /workspace/wt/a6/docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact

```

`docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact/probes.json` (GPU/disk and run-status lines; full raw receipt archived)

```text
[
  {
    "command": [
      "nvidia-smi",
      "--query-gpu=memory.used,memory.total",
      "--format=csv,noheader"
    ],
    "returncode": 0,
    "stdout": "356 MiB, 24576 MiB\n",
    "stderr": ""
  },
  {
    "command": [
      "dd",
      "if=/dev/zero",
      "of=/workspace/wt/a6/g298_scratch/fsync_probe.bin",
      "bs=1M",
      "count=8",
      "conv=fsync"
    ],
    "returncode": 0,
    "stdout": "",
    "stderr": "8+0 records in\n8+0 records out\n8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.206576 s, 40.6 MB/s\n"
  }
]

```

## Reproduction, identity and verifier self-check

```text
bash scripts/platformkit/tracking/g298_run.sh
python -m scripts.platformkit.tracking.g298_compare --located-feet docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv --output docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact
python -m pytest scripts/platformkit/tracking/test_g298_compare.py -q -p no:cacheprovider
..... [100%]
5 passed in 1.93s
python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
. [100%]
1 passed in 1.62s
```

Independent recomputation: `python -m scripts.platformkit.tracking.g298_audit` returned PASS for SciPy distances, counts, medians and all six exact binomial p-values, plus arm settings, input hashes and decoded-pixel equality.

The pod command is already complete; the execution lock deliberately prevents an accidental extra draw. Local arithmetic is rerunnable from the committed CSVs. Route files, weights, library versions, settings and input path/bytes/resolution are in each arm's summary. Local input/route identities are in artifact_inventory.json. No allowlisted file grew (A12).

Against `docs/evidence/tracking/VERIFIER_CONTRACT.md`: B1/B9 retain all 143 distinct (frame, player_id) observations and all 15 frames; B2 adds artifacts without schema changes; B3/B4 no production queue/lifecycle changes; B5 uses the explicit compute-only scratch exception, never the deployed tree; B6 no module move; B7 uses the complete prescribed frame set; B8 fits nothing and names the single-locator reference; B10 changes no bar; B11 reports A's actual repeat check and limits B/C to single draws. A7 evidence paths checked; A9/A11 exact sources and route hashes archived. Q is for S-register rows and does not apply to G298. The RESULTS_LEDGER row and this memo are in the same commit. TRACKING_GAPS_2026-09-01.md and the user-owned spec edit are untouched by this landing.

## NOT VERIFIED

- Human ground truth, locator completeness, independent-rater agreement, unique-player recall, true precision.
- Clip-wide, second-shot, second-clip or population generalisation.
- B/C repeatability or the historical tracking route's repeatability.
- Why fresh A differs from historical retained tracking footpoints, if it does.
- Runtime, throughput, practical cost, tracking identities, homography quality or downstream benefit.
- Whole-volume disk usage/net growth, production adoption, or any filter, threshold, gate or retrain.

## Focused test source (pasted)

```python
"""Pin G298's immutable denominator, conventions, and paired arithmetic."""
from pathlib import Path
import json

import pytest

from scripts.platformkit.tracking.g298_compare import (
    ELIGIBLE_FEET, FRAME_COUNT, TOLERANCES, bottom_centre, exact_mcnemar, read_locations,
    compare, write_csv,
)


def test_committed_denominator_and_frames() -> None:
    path = Path(__file__).resolve().parents[3] / (
        "docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv")
    rows = read_locations(path)
    assert len(rows) == ELIGIBLE_FEET == 143
    assert FRAME_COUNT == 15
    assert sorted({int(r["source_frame"]) for r in rows}) == [
        19630, 19879, 20190, 20440, 20689, 20938, 21187, 21499,
        21686, 21935, 22247, 22496, 22683, 22994, 23368]
    assert TOLERANCES == (25, 50, 100)


def test_bottom_centre_matches_production_integer_clipping() -> None:
    assert bottom_centre([10, 20, 30, 90]) == (20, 90)
    assert bottom_centre([10.9, 20.2, 31.8, 90.9]) == (20, 90)
    assert bottom_centre([-10, 20, 2000, 1100]) == (960, 1080)


def test_exact_paired_discordance() -> None:
    result = exact_mcnemar([False] * 10, [True] * 10)
    assert result == {"lost": 0, "gained": 10, "discordant": 10, "nominal_p": 2 / 1024}
    assert exact_mcnemar([True, False], [True, False])["nominal_p"] == 1
    assert exact_mcnemar([True, False], [False, True])["nominal_p"] == 1


def test_missing_foot_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "incomplete.csv"
    path.write_text("source_frame,player_id,foot_x_px,foot_y_px\n19630,p01,10,20\n")
    with pytest.raises(AssertionError, match="143"):
        read_locations(path)


def test_empty_detection_frame_keeps_all_143_eligible(tmp_path: Path) -> None:
    located = Path(__file__).resolve().parents[3] / (
        "docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv")
    feet = read_locations(located)
    frames = sorted({int(r["source_frame"]) for r in feet})
    for arm in ("A", "A_repeat", "B", "C"):
        detections = [{"source_frame": r["source_frame"], "foot_x_px": r["foot_x_px"],
                       "foot_y_px": r["foot_y_px"]} for r in feet
                      if arm not in ("A", "A_repeat") or int(r["source_frame"]) != frames[0]]
        write_csv(tmp_path / f"{arm}.csv", detections)
        (tmp_path / f"{arm}_summary.json").write_text(json.dumps(
            {"frames": frames, "total_detections": len(detections)}))
    result = compare(located, tmp_path)
    assert result["A_byte_identical"] is True
    assert result["arms"]["A"]["counts_per_frame"][frames[0]] == 0
    for tolerance in TOLERANCES:
        assert result["arms"]["A"]["recall"][tolerance] == {
            "matched": 133, "eligible_denominator": 143, "recall": 133 / 143}
        assert result["arms"]["B"]["recall"][tolerance]["matched"] == 143
        assert result["paired_tests"]["A_vs_B"][tolerance]["gained"] == 10

```
