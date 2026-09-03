# G198 Prefetch Frame Misalignment

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md). This is a
measurement-only result. No production file was edited or deployed. The
instrumentation existed only in each fresh measurement process, streamed over
standard input; its outputs were written under pod `/tmp` and then retrieved as
evidence. The pod daemon and keeper were neither stopped, restarted, nor
deployed over.

## Verdict

The prefetch cache is **systematically frame-misaligned** on this route. In all
three unchanged, instrumented control processes, all 400 `get_players_pos`
calls were served by the cache, and every served detection came from source
frame `processed + 3`. The pipeline processes this long video at stride 3, so
this is the *next processed frame*, not the current frame. There were zero
unmatched source identities.

This confirms the association-error half of the hypothesis, with a correction
to its raw-frame wording: it is `k+3` rather than `k+1` because adjacent
processed frames are three source frames apart. The measured `peek` return
distributions and cache-served counts were identical across the control runs;
this `n=3` run did **not** exhibit the proposed variable-buffer-size race.

The bypass arm was **not identical** across its three runs despite zero
cache-served frames and `cudnn.benchmark=False`. Therefore the cache path is
not sufficient to explain the residual whole-route non-determinism. Its removal
does not eliminate the remaining cause(s). That does not weaken the direct
misalignment observation above.

## Fixed input, machine, and code identity

| Field | Value |
|---|---|
| Machine | Pod `5a20910184ad`; NVIDIA GeForce RTX 3090, 24,576 MiB |
| Input | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` |
| Input identity | 2,931,985,407 bytes; 1920x1080; 174,430 frames |
| Route arguments | `--frames 1200 --no-show --skip-features` |
| `unified_pipeline.py` SHA-256 | `047dd04e9b12b588c560f68dbab32aa1855f791c2e1a46f19f4e082f50c4f331` |
| `advanced_tracker.py` SHA-256 | `df2ae698ae03e804f67639434d8303638aea9087c3169c016af5a3734dd474d7` |
| Match to G195 recorded hashes? | Yes, both exactly match `g195_cv2_rng_route_determinism_2026-09-03.md`. |

## Method

Each counted row was a separate pod Python process, run serially and exiting
0. The wrapper was process-local:

- `_FramePrefetcher.peek` snapshot the queued `(ok, frame, frame_idx)` items
  under the queue mutex immediately before calling the unmodified `peek`. Its
  own parallel structure retained only the source indices; it did not alter the
  production queue or return values.
- `AdvancedFeetDetector.prefetch_yolo` (the concrete class carrying the named
  methods) associated each prefetch call with that parallel index batch. It
  never attached identity to, read from, or changed `_yolo_result_buf`.
- `AdvancedFeetDetector.get_players_pos` joined the same live prefetch thread
  immediately before the original method would do so, observed whether the
  original cache would be consumed, recorded the corresponding parallel source
  index, and then invoked the original method. No production result was popped
  by the wrapper.

For Part 1, no route setting was changed. For Part 2 only,
`prefetch_yolo` was a process-local no-op and `cudnn.benchmark=False` was
applied after the pipeline initializer, matching G190's established setting.
No seeds, FP32 mode, threshold, confidence, image-size, crop, coordinate, or
feature setting was changed.

`ELIGIBLE denominator: attempted gameplay frames` is the count of distinct
`frame` values in each complete `ball_tracking.csv`; it is not `--frames`.
Survivors are complete player-row sets at the two pre-specified source frames,
ordered by player ID, team, and bbox columns.

## Part 1: instrumented unchanged control

Each control process made 58 `peek` calls: one returned 5 frames and 57
returned 7, for whole-run histogram `{5: 1, 7: 57}`. Every returned source
batch was matched to the prefetch call (`0` unmatched batches).

| Run | Player rows | Distinct player-row frames | ELIGIBLE denominator: attempted gameplay frames | Cache / self | Whole-run served-minus-processed offset | Frame 474 survivors | Frame 1377 survivors |
|---|---:|---:|---:|---|---|---|---|
| C1 | 1,143 | 400 | 400 | 400 / 0 | `{3: 400}` | `(1,green,1296.0,378.0,1434.0,609.0)`; `(7,white,1632.0,763.0,1746.0,919.0)` | `(4,green,1440.0,653.0,1638.0,930.0)`; `(5,green,326.75687,788.7226,476.20407,920.217)`; `(6,white,404.31805,783.2972,559.2364,943.6401)`; `(9,white,659.0,478.0,812.0,770.0)` |
| C2 | 1,266 | 390 | 400 | 400 / 0 | `{3: 400}` | `(5,green,1447.0,366.0,1569.0,649.0)`; `(10,white,1516.0,99.0,1609.0,298.0)` | `(1,green,582.0,655.0,750.0,822.0)`; `(2,green,666.0,317.0,841.0,777.0)`; `(6,white,659.0,478.0,812.0,770.0)`; `(7,white,487.0,264.0,584.0,538.0)` |
| C3 | 1,329 | 400 | 400 | 400 / 0 | `{3: 400}` | `(5,green,1296.0,378.0,1434.0,609.0)`; `(10,white,1633.0,769.0,1753.0,928.0)` | `(1,green,582.0,655.0,750.0,822.0)`; `(4,green,717.0,304.0,840.0,550.0)`; `(6,white,355.0,771.0,518.0,930.0)`; `(8,white,805.0,157.0,907.0,405.0)`; `(9,white,165.0,792.0,323.0,930.0)`; `(10,white,659.0,478.0,812.0,770.0)` |

The cache-served counts, self-inferred counts, `peek` histograms, and offset
histograms are all identical across C1-C3. Complete route outputs are not
identical: their complete tracking and ball CSV SHA-256 values differ (stored
per run below), matching the row-count and survivor differences in the table.

## Part 2: bypass (`prefetch_yolo` no-op, tuner off)

All 400 consumer calls in every bypass run self-inferred on their own frame;
the cache-served count was zero. The offset histogram is empty because nothing
was served from the cache. The complete route outputs are nevertheless not
identical across B1-B3.

| Run | Player rows | Distinct player-row frames | ELIGIBLE denominator: attempted gameplay frames | Cache / self | Frame 474 survivors | Frame 1377 survivors |
|---|---:|---:|---:|---|---|---|
| B1 | 1,366 | 400 | 400 | 0 / 400 | `(5,green,1456.0,362.0,1567.0,642.0)`; `(6,white,1632.0,763.0,1746.0,919.0)` | `(1,green,2575.1938,110.11349,2712.4434,299.79874)`; `(2,green,1074.0616,208.33972,1201.4965,411.07886)`; `(6,white,3860.2292,-405.85956,4017.0872,-188.04938)`; `(9,white,2378.0898,-393.3518,2499.7856,-211.05568)` |
| B2 | 1,314 | 399 | 400 | 0 / 400 | `(1,green,1276.0,399.0,1426.0,611.0)`; `(10,white,1504.0,98.0,1603.0,297.0)` | `(1,green,257.0,744.0,393.0,927.0)`; `(3,green,135.40771,804.6558,288.3781,947.054)`; `(4,green,327.89594,794.0204,479.32355,926.5121)`; `(5,green,165.0,793.0,322.0,928.0)`; `(7,white,162.0,642.0,293.0,864.0)` |
| B3 | 1,320 | 400 | 400 | 0 / 400 | `(5,green,993.0,383.0,1125.0,600.0)`; `(7,white,1729.0,144.0,1870.0,363.0)` | `(2,green,165.0,793.0,322.0,928.0)`; `(5,green,29.0,805.0,179.0,928.0)`; `(8,white,356.0,771.0,510.0,933.0)` |

**Are B1-B3 identical? No.** Both full `tracking_data.csv` and
`ball_tracking.csv` hashes differ across the three records. Since the cache was
empty and every call self-inferred, this arm eliminates the cache path as a
sufficient explanation for the residual variance under this design.

## Per-run and per-frame records (B13/Q9)

The complete unfiltered data, including all 2,400 consumer-frame records, all
58/400 prefetch-batch records per run, whole-run histograms, source-index match
flags, both CSV hashes, denominators, and survivor tuples, is committed beside
this memo: [g198_prefetch_frame_misalignment_2026-09-03_records.json](g198_prefetch_frame_misalignment_2026-09-03_records.json).
Its SHA-256 is `8e14df34bb72ead2e2b01cb3efac904b6ccaf9022de7f482cea9b3f698593490`.

For audit, control output CSV hashes are C1
`9a095200...41bde67` / `7e354856...32e221e`, C2
`ceab13a5...094aac` / `4a6ff1b2...7ded05d`, and C3
`7a528578...39906d` / `6eb23fa1...d9f494` (tracking / ball). Bypass hashes are
B1 `f3120a07...6b4b8e` / `840fa2e8...d233a3`, B2
`174e4329...e2cf07` / `e1cd943e...995cbd`, and B3
`cab842b6...dd46a4` / `31ff5af0...5f60ca`.

## Focused harness test

```text
python -m pytest scripts/platformkit/tracking/test_g198_prefetch_frame_misalignment.py -q
2 passed in 3.08s
```

## VERIFIER_CONTRACT self-check

- **A2/B13/Q9:** Every emitted player/ball row was recounted without filtering,
  and the committed JSON preserves every observed consumer call and prefetch
  batch rather than a first-rows sample.
- **A7/A9/A11:** This memo names the requested evidence path, input identity,
  route arguments, and pod hashes; both route hashes match G195.
- **B2-B6:** No schema, reader, queue, daemon, keeper, production module, or
  pod checkout file changed. The additions are a standalone harness, focused
  test, memo, and retrieved measurement record.
- **B7-B10:** Source frames 474 and 1377 were pre-specified. No threshold,
  confidence, image size, crop, coordinate contract, precision change, seed,
  corpus, flag, bar, daemon, or keeper changed.

## NOT VERIFIED

- Why the bypass arm still varies; it rules out cache use as a sufficient cause
  here but does not identify the remaining source(s).
- Tracking quality, calibration, player coverage quality, or whether removing
  the cache improves any of them. A self-inferred result is not automatically
  a better result.
- The behavior on another video, GPU, decode backend, stride, queue depth, or
  runtime load. This is one fixed video with three fresh processes per arm.
- A cache timing race on this fixed run: `peek` distributions were stable in
  Part 1, so the race mechanism was not observed even though the systematic
  identity offset was.
- Performance comparison. Bypass removes batching and is expected to be
  slower; that expected cost was not treated as a finding.
- Any effect introduced by the measurement wrapper's small timing overhead.
  It joins the same prefetch thread at the same pre-consumption point as the
  original method, but wrapper instrumentation is not a zero-overhead proof.
