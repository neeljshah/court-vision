# G211b Per-Frame Cost Attribution - 2026-09-04

## Verdict

NOT VALIDATED. The required 1,200-frame-budget retry reached the process-local
collector 400 times, but no call reached `crops_step3`, `osnet`, `assign_state`,
or `render`. The route emitted zero tracking rows and exited 3. Therefore there
is no per-frame tracking-cost distribution, no exhaustive numeric attribution,
and no percentage. The zero-stage rows are not a cost result.

## Input, code identity, and disk guard

Machine: pod `5a20910184ad`, 256 cores. Input opened:
`/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`,
2,931,985,407 bytes, 1920x1080, 174430 frames. Pod SHA-256 values were
`scripts/run_clip.py` `7aec5d57e0357ff4585deabeb7a18bbc5bcb2c197cefe5fad591c16ca3bc761b`,
`src/pipeline/unified_pipeline.py` `047dd04e9b12b588c560f68dbab32aa1855f791c2e1a46f19f4e082f50c4f331`,
and `src/tracking/advanced_tracker.py` `df2ae698ae03e804f67639434d8303638aea9087c3169c016af5a3734dd474d7`.

Before temporary output was created, the wrapper ran a 1 MiB `dd conv=fsync`
probe successfully and recorded `du -sm /workspace/nba-ai-system/data` in each
floor snapshot. It removed 79,105 bytes of wrapper output and 10,816 bytes of
temporary route data (89,921 bytes total); no corpus source was deleted.

## Bounded route and shared-machine floor

Command semantics were unchanged: `run_clip.py --frames 1200 --no-show
--skip-features`, executed only through an additive, off-by-default wrapper in
the launched process. It ran for 100.483 seconds, processed 1,380 source
frames, made 400 collector calls, and exited 3 after Stage 1 produced zero
rows. The collector-call premise is confirmed, but the calls stopped before the
tracking-state buckets, so the decomposition never partitions a tracking frame.

These are shared-machine figures, not clean-machine capacity; absolute times
would be upper bounds even if a valid sample existed. The immediate floor was
load 19.12/18.21/16.83 before and 20.22/19.04/17.29 after, GPU 0 percent and
354 MiB of 24,576 MiB at both snapshots. The permanent floor included tennis
`adapter_run` (about 82 percent CPU), `foundry_runner` (about 22 percent),
`inplay_capture_runner` (about 13 percent), the scheduler, `track_daemon`, and
`keep_track_daemon.sh`. The load shift was below the declared material-change
cutoff; zero timings were discarded in this final run. No daemon, keeper,
adapter job, capture process, foundry process, or pod-checkout file was stopped,
restarted, changed, or deployed.

One preliminary cleanup-accounting retry was discarded and repeated because its
load-1 changed from 15.51 to 22.90. It is not timing evidence; the final raw
record is the unchanged-floor repeat described above.

The raw, recomputable route data, contexts, code hashes, cleanup accounting,
and all 400 collector rows are in
`docs/evidence/tracking/g211b_per_frame_cost_attribution_2026-09-04_records.json`.

## Decomposition and static attribution

The reused wrapper has seven mutually exclusive buckets: `pre_yolo`, `yolo`,
`post_yolo`, `crops_step3`, `osnet`, `assign_state`, and `render`. Its reducer
uses their sum as total and names any remainder. The legacy overlapping intervals
remain unsuitable as shares because the old `assign_render` interval spans the
separately timed OSNet block. No wrapper bucket or route threshold was changed.

Static reading from the prior G211 analysis still identifies `assign_state` as
track matching, slot activation and loss aging, gallery eviction and re-ID,
free-slot assignment, freeze and Kalman handling, batched optical flow,
same-team duplicate comparisons, periodic calibration, and pose-field updates;
the duplicate-comparison loop is quadratic in active same-team slots. There is
no drawing in that legacy block. `crops_step3` creates detection crops, HSV and
classification inputs, homography coordinates, and color-tracker updates.
OSNet batches appearance embeddings for moved detections. Removing crops or
OSNet can change surviving players, so neither is avoidable for a coverage run.

Human-gated proposal only: once a route emits valid tracking rows, profile
exclusive time inside assignment and consider batching duplicate comparisons
only after survivor equivalence is demonstrated. No `src/` change is applied.

## Verification and NOT VERIFIED

`python -m pytest scripts/platformkit/tracking/test_g211_per_frame_cost.py -q`
passed (3 passed). `python -m pytest tests/platformkit/test_loc_rail_scope.py -q`
passed (1 passed). The wrapper remains below the 300 LOC rail, so no allowlist
change is required. The wrapper was minimally repaired to use the configured
SSH host, probe disk before temporary output, account for cleanup bytes, and
discard a materially shifted attempt before considering its exit status; its
seven timing buckets were unchanged.

NOT VERIFIED: tracking-frame median/p90/max; an exhaustive numeric attribution;
stage proportions; clean-machine capacity; repeatability; any optimization
saving; and why this pod route still emits no tracking rows despite the proven
frame budget. Contract self-check: A7 paths exist; B1-B10 are not triggered
(no metric, schema, threshold, route deployment, or survivor set was changed).
