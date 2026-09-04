# G211 Per-Frame Cost Attribution - 2026-09-04

## Verdict

NOT VALIDATED. No per-frame cost distribution or percentage is reported. The
required disjoint decomposition was implemented as an additive, off-by-default
streamed wrapper, but the bounded route did not produce a valid instrumented
frame sample before this landing.

## What was measured

Machine: pod `5a20910184ad`, 256 cores. Input opened:
`/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`,
2,931,985,407 bytes, 1920x1080, 174430 frames. Pod route file SHA-256 values:
`scripts/run_clip.py` `7aec5d57e0357ff4585deabeb7a18bbc5bcb2c197cefe5fad591c16ca3bc761b`,
`src/pipeline/unified_pipeline.py` `047dd04e9b12b588c560f68dbab32aa1855f791c2e1a46f19f4e082f50c4f331`,
and `src/tracking/advanced_tracker.py` `df2ae698ae03e804f67639434d8303638aea9087c3169c016af5a3734dd474d7`.

The permanent shared-machine floor immediately before/after the recorded
attempt was load 13.02 to 15.84 (not material under the declared 35% and five
load-unit discard rule), GPU 0% and 354 MiB, with tennis `adapter_run` about
69%, `foundry_runner` about 17%, capture about 13%, scheduler about 6%, and
the daemon and keeper resident. These are shared-machine figures, never
clean-machine capacity. The raw contexts are in
`g211_per_frame_cost_attribution_2026-09-03_records.json`.

The one-source-frame smoke route exited 3 after nine processed source frames,
with no tracking rows and zero calls reaching the instrumented per-frame
collector. A later 360-frame attempt exposed and corrected a wrapper-global
binding defect before it could yield a record. It is not included as timing
evidence. No daemon, keeper, adapter job, capture process, foundry process,
or pod-checkout file was stopped, restarted, changed, or deployed.

## Disjoint decomposition design

The additive wrapper instruments `AdvancedFeetDetector.get_players_pos` in its
own streamed process only. Its mutually exclusive buckets are `pre_yolo`,
`yolo`, `post_yolo`, `crops_step3`, `osnet`, `assign_state`, and `render`; the
reducer asserts the total as their sum and names any remainder. This replaces
the non-additive legacy intervals: legacy `assign_render` begins before OSNet
and therefore cannot be a share. No percentage is printed until a valid frame
sample partitions the total.

## Static attribution and proposal

`assign_render` contains no drawing before its legacy timer stops. Its CPU work
is track matching, slot activation/loss aging, gallery eviction/re-ID, free-slot
assignment, freeze and Kalman handling, batched optical flow, same-team
duplicate comparisons, periodic calibration, and pose-field updates. The
same-team duplicate loop is quadratic in active same-team slots; other loops
are per detection or per configured slot. `crops_step3` creates detection crops,
HSV/classification inputs, homography coordinates, and color-tracker updates.
OSNet batches appearance embeddings for moved detections. Removing either can
change surviving players, so no coverage-measurement shortcut is proposed.

Human-gated proposal only: after a valid partition, profile exclusive time
inside assignment and consider batching/reducing duplicate comparisons only if
survivor equivalence is demonstrated. No `src/` change is applied here.

## Verification and NOT VERIFIED

`python -m pytest scripts/platformkit/tracking/test_g211_per_frame_cost.py -q`
passed (2 passed). `python -m pytest tests/platformkit/test_loc_rail_scope.py -q`
passed (1 passed). The new harness is 76 LOC and needs no allowlist change.

NOT VERIFIED: frame median/p90/max, exhaustive numeric attribution, avoidable
time, clean-machine capacity, repeatability, and any optimization saving. A7
paths named here exist. B5 is satisfied: the wrapper was streamed and only
temporary `/tmp/g211_*` paths were removed; no pod checkout deployment occurred.
