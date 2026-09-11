VERDICT: PARTIAL -- no measured class reaches the sealed 30-distinct-retained-section quota; every delivered-format identity is UNRESOLVED because no digest-bound delivered-format receipt exists. Residual strata are measured UNKNOWN (33 pruned) and actual UNRESOLVED (121 sections, 88 retained); no residual is COMPLETE. The scratch replay remains NOT VALIDATED (zero launches).

Sealed protocol: [prereg.md](g407_live_rendition_boundary_census_2026-09-11/prereg.md), sealed alone at 050d633bc, LF-normalized seal `a411f5905fbce243d2198889752e40c5025a9b1abff74105976bbdd82606978c`. No clause was amended.

## Premise, measured from the pod rather than assumed

Four feeder relaunch boundaries were read from `/workspace/feeder/relaunch.log`: 11:50:51Z fmt720 patch, 13:08:37Z prefer-30fps selector, **17:01:52Z selector 270 -> 232 -> 60fps**, **18:56:17Z probe-aware discovery gate**. The census window runs from the 17:01:52Z boundary to census UTC 2026-09-11T19:13:54Z. Feeder `dc20ec04be5cd3257ea74aec4c09731b877a9cc5d29f633f048686bc659a9b8e feeder_pod.sh` and discovery `83166f063f81db0beb6310102a92291adaeccbfc1231a61e6ee8d48549cff61f discover_sources.py` match the brief; the ledger, feeder log, discovery sidecar and queue digests are sealed in `ops_snapshot.json`. The daemon `python3 -u scripts/platformkit/track_daemon.py --workers 8 --forever` (pid 3177187) ran untouched throughout.

The whole-set population is 121 terminal ORIGINAL sections (111 tracked, 10 thin, zero repeats suppressed) from 2,375 ledger lines. Fetch receipts report requested itag 270 for 109 and 232 for 12, but the feeder wrote no digest-bound delivered-itag receipt; requested itag is not a delivered rendition. The retained bytes define classes only by measured height and fps.

## Rendition supply: a requested itag does not establish a delivered rendition

Of the 109 requested-270 sections, 46 measured 1920x1080, 30 measured 1280x720, and 33 were pruned before retention. All 12 requested-232 sections measured 1280x720. These request counts stay descriptive only: all 121 actual-format ids and actual renditions are UNRESOLVED.

All 88 sources that still existed were retained off-pod (4.36 GB to `C:/Users/neelj/g407_receiver`), rehashed and reprobed independently: **88/88 digests match the pod and 88/88 probes agree** on height and native rate. Measured classes (independently decoded height and rational frame rate, never an itag): 720p30 26, 1080p60 24, 1080p30 22, 720p25 11, 720p60 5, plus 33 UNKNOWN pruned. None reaches 30, so the complete-census bar fails and the row is PARTIAL with the whole retained population measured rather than a post-outcome subset.

## Evaluated boundary, decoded-versus-read, held share

Known schedules reconcile **111/111** (evaluated + suspended = ball-table reads); the 10 `ball_table_absent` sections retain that value in `schedule_reason`, use schedule_status UNKNOWN, and emit UNKNOWN rather than zero for schedule-derived counts/rates. Aggregates use 111 known schedules plus 10 UNKNOWN, never a zero-equals-zero success. The known rows total 100,491 producer reads from 511,485 decoded source frames: 97,065 evaluated and 3,426 suspended.

Held share on known schedules over shared consecutive evaluated ticks, no bridging: **296,072 / 353,842 = 0.836735** full admitted and **3,317 / 3,832 = 0.865605** sealed two-second native-PTS. The 10 schedule-absent rows do not enter either aggregate; these remain two descriptive scopes, not a paired intervention.

## Cap spans against the 100-second target

The raw cap receipts remain 29 of 88 measured sections over 5 s; the schedule-known derived aggregate is 22 of 78, with 10 schedule-absent rows excluded. Derived out-of-window rows: 0; overruns remain separately retained in `raw_traces/`.

## Identity, reproduction, and fixes

Twelve exercised producer assets (six models, six route files) were hashed read-only; all twelve mtimes precede daemon and window starts. Two fresh processes regenerate every table and card from delivered bytes; `repeats.json` records stdout, returncode, per-table digests, and identical status. The field-aware scan returns zero non-opaque hits over **2,251 record fields and 203 delivered file records**.

Fix 1b (2026-09-11): delivered-format binding requires a receipt tied to the source digest; schedule-absent reconciliation is UNKNOWN; the executed even-draw cap is the sealed 180; residual strata are PARTIAL. Measurements, raw census, probes, and retained receipts are unchanged; superseded derived tables remain under `pre_fix1b/`.

Fix 1c (2026-09-11): class summaries keep UNRESOLVED/UNKNOWN PARTIAL and never quota_met; schedule-dependent values are UNKNOWN on all 10 schedule-absent rows with the reason alias retained. Derived schedule aggregates use 111 known + 10 UNKNOWN, the Q6 own scan includes both pre-fix archives, and `pre_fix1c/` preserves superseded tables. Measurements are otherwise unchanged.

## Digests (full inventory in SHA256SUMS, byte domain on line 1)

10991cc76784ad54f937603dd3ec859864ddd08479edd68254d605ba085c122d summary.json
65b993159222de2e3d68674f3de0d0f0669043afbb6ccb4c96434d1aaf1ab114 source_format_join.csv
f14e27d069ea08d249f3641d84570c1165aed60ee64071e6eee70a4c4b96ac20 provenance_counts.csv
224ca0a889ea89448fe9688ba42c24d1f6d537ad2e2ad44e65d377b500180aa2 draw.csv
bf25cf178338a907fcc8ef5e8298c93d5221a5cf1447779c4fa101bd3de0576b coverage.csv
6717e05dc579845faf0bda1e269d707fb704e3e4a3f74557c394fe5a33a517fd held_pairs.csv
3ff789cb0e3a3c0c1ac8e6a61a8bd1088e570223094afdc12292c1f189a08017 window_counts.csv
a73ba03032ab8f33cbf121b192b57c8bb0e0e590b5bd467c552e3cb5adb9f447 class_summaries.csv
eeedceef58e2c7e7198c4d729efc639b3e37caae4b5e9dea88092af52dcc1068 q6_scan.json
234f9cbd472455668cac5d38a4c8048a172bd7473d11f7a6f9a22c0f0217c7ca repeats.json

## NOT VERIFIED

- Any instrumented scratch replay, observer trace, launch receipt or live internal producer event: zero launches in this landing (`launch_receipts.csv`, `runtime_receipts/stage5_no_scratch_replay.log.txt`). The single pod GPU is held by the ORIGINAL daemon and no competing launch or restart was permitted, so the runtime-replay metric is NOT VALIDATED rather than passed.
- Delivered itag identity for all 121 sections: no digest-bound delivered-format receipt exists; requested itags remain requests only.
- Every fact about the 33 sections whose sources the quota guard pruned before retention: their native dimensions, rate, digest, PTS and cap span are UNKNOWN, never zero.
- Any causal attribution of held share, read fraction or cap loss to resolution, native rate, the selector change or the probe-aware gate; the two sampling scopes are not a paired intervention.
- Producer repeatability, determinism, and absent rendition supply (312, 311, 301, 300, and generic fallback).
- Any calibration, market or currency statement: this row measures a producer boundary only.
