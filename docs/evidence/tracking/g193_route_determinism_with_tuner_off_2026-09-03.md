# G193 Route Determinism With Tuner Off

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md). This is a measurement
only. No production file was edited, deployed, or copied into the pod checkout.
The six G193 jobs were launched one at a time. The tuner-off change was an
in-memory measurement-process wrapper only.

## Verdict: tuner off is NOT sufficient for the whole route

The three tuner-off executions are **not identical**: they emitted 1,246,
1,348, and 1,268 player rows respectively, and their survivor sets differ at
both source frames 474 and 1377. This is a full-success negative result under
the acceptance rule. It establishes residual non-determinism in the whole
route after the isolated G190 detector fix; it does not causally prove that the
stateful tracker, rather than another downstream or environmental component,
is the remaining source.

The unmodified tuner-on control also varied: 1,400, 1,342, and 1,322 player
rows. This reproduces G189's route-level non-determinism in the same table.

## Fixed input, pod identity, and code identity

| Field | Value |
|---|---|
| Pod | `5a20910184ad`; NVIDIA GeForce RTX 3090, 24,576 MiB |
| Source opened | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` |
| Source identity | 2,931,985,407 bytes; 1920x1080; 174,430 frames |
| Route cap | `--frames 1200` |
| `unified_pipeline.py` SHA-256 | `047dd04e9b12b588c560f68dbab32aa1855f791c2e1a46f19f4e082f50c4f331` |
| `advanced_tracker.py` SHA-256 | `df2ae698ae03e804f67639434d8303638aea9087c3169c016af5a3734dd474d7` |
| Controls deliberately not used | seeds, FP32, threshold changes, `conf` changes, `imgsz` changes, crop changes |

Tuner-on controls used this unchanged route command, substituting each table's
fresh directory:

```text
python3 scripts/run_clip.py --video data/footage_corpus/wnba__wnba_01.mp4 --frames 1200 --no-show --skip-features --data-dir <fresh>
```

For tuner-off, the measurement process imported
`src.pipeline.unified_pipeline`, saved `UnifiedPipeline.__init__`, installed a
replacement which called the original and then set
`torch.backends.cudnn.benchmark = False` before returning. It then set the
same `sys.argv` route arguments shown above and invoked
`runpy.run_path("scripts/run_clip.py", run_name="__main__")`. The wrapper was
passed to `python3 -` over SSH standard input; it wrote no file on the pod and
was not deployed. This is required because the original initializer sets the
tuner to `True` internally. No seed or precision setting was changed.

## Six-run result and per-run records

`ELIGIBLE denominator: attempted gameplay frames` is the distinct `frame`
count in that run's `ball_tracking.csv`. It is not the `--frames` argument.
Every table metric was directly recounted from the retained output CSVs using
the read-only G193 extractor.

| Arm / run | Pod output directory | Player rows | Distinct player-row frames | ELIGIBLE denominator: attempted gameplay frames | Frame 474 survivors | Frame 1377 survivors |
|---|---|---:|---:|---:|---|---|
| Tuner on 1 | `/tmp/cx_g193_route_determinism_20260903_tuner_on_run1` | 1,400 | 400 | 400 | `(5, green, 1447, 366, 1569, 649)`; `(6, white, 1719, 135, 1869, 364)` | `(3, green, 256, 744, 391, 921)`; `(6, white, 355, 771, 518, 930)` |
| Tuner on 2 | `/tmp/cx_g193_route_determinism_20260903_tuner_on_run2` | 1,342 | 400 | 400 | `(4, green, 1447, 366, 1569, 649)`; `(9, white, 1633, 769, 1753, 928)` | `(1, green, 495.3203, 291.38226, 612.16284, 551.09607)`; `(5, green, 717, 304, 840, 550)`; `(6, white, 165, 792, 323, 930)`; `(9, white, 355, 771, 518, 930)` |
| Tuner on 3 | `/tmp/cx_g193_route_determinism_20260903_tuner_on_run3` | 1,322 | 400 | 400 | `(4, green, 1296, 378, 1434, 609)`; `(10, white, 1710, 762, 1869, 930)` | `(2, green, -646.64154, 1136.5715, -494.41946, 1276.2136)`; `(3, green, 1476, 371, 1608, 617)`; `(6, white, 355, 771, 518, 930)`; `(7, white, 482.07562, -1699.4529, 623.99786, -1483.4875)`; `(10, white, 1437, 104, 1527, 330)` |
| Tuner off 1 | `/tmp/cx_g193_route_determinism_20260903_tuner_off_run1` | 1,246 | 400 | 400 | `(5, green, 1276, 399, 1426, 611)`; `(7, white, 90.418076, 96.806366, 198.9775, 309.27072)`; `(9, white, 1042.2572, 680.5686, 1193.1053, 843.13257)` | `(2, green, 502, 304, 637, 555)`; `(3, green, 1440, 653, 1638, 930)`; `(4, green, 159.11664, 792.1035, 315.28333, 927.3535)`; `(10, white, 1503.8336, 362.36334, 1632.6102, 607.95123)` |
| Tuner off 2 | `/tmp/cx_g193_route_determinism_20260903_tuner_off_run2` | 1,348 | 400 | 400 | `(3, green, 1447, 366, 1569, 649)`; `(10, white, 1719, 135, 1869, 364)` | `(4, green, 1440, 653, 1638, 930)`; `(6, white, 165, 792, 323, 930)`; `(7, white, 356, 771, 518, 930)` |
| Tuner off 3 | `/tmp/cx_g193_route_determinism_20260903_tuner_off_run3` | 1,268 | 400 | 400 | `(5, green, 1296, 378, 1434, 609)`; `(9, white, 1633, 769, 1753, 928)` | `(1, green, 165, 793, 322, 928)`; `(4, green, 717, 304, 840, 550)`; `(8, white, 165, 792, 323, 930)`; `(9, white, 757, 485, 975, 732)` |

All six player-row and attempted-gameplay frame ranges were `180..1377`.
The direct post-run recensus returned the same row counts and 400 eligible
frames per directory.

## Required tuner-off comparison

| Required field | Tuner-off run 1 | Tuner-off run 2 | Tuner-off run 3 | Identical across all three? |
|---|---:|---:|---:|---|
| Player rows | 1,246 | 1,348 | 1,268 | No |
| Frame 474 survivor set | 3 tuples | 2 tuples | 2 tuples | No |
| Frame 1377 survivor set | 4 tuples | 3 tuples | 4 tuples | No |

Therefore the answer to the G193 deliverable is **no**: turning the cuDNN
tuner off does not make the whole `run_clip.py` route deterministic under this
three-run measurement.

## Focused harness test

The new non-production extractor is
`scripts/platformkit/tracking/g193_route_determinism.py`; its per-file test
was run locally:

```text
python -m pytest scripts/platformkit/tracking/test_g193_route_determinism.py -q
2 passed in 0.83s
```

The same extractor was streamed to the pod over standard input to recount every
run directory; it did not write into the pod checkout.

## VERIFIER_CONTRACT self-check

- **B1 CIRCULAR METRIC:** Clear. Every row in each `tracking_data.csv` and
  every distinct `frame` in each `ball_tracking.csv` was recounted.
- **B2 NON-ADDITIVE SCHEMA / B3 FALL-THROUGH / B4 RE-CLAIM:** Clear. No schema,
  reader, gate, queue, daemon, or keeper behavior changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. The wrapper and extractor were sent on
  standard input only; no repository file was copied to or deployed in the pod
  checkout.
- **B6 ORPHANS:** Clear. The new harness and its focused test are evidence-only
  additions under `scripts/platformkit/tracking/`.
- **B7 HEAD-SLICE EVIDENCE:** Clear. The two named source frames are the
  acceptance-rule frames, not a quality sample.
- **B8 SELF-FIT / B9 DEGENERATE DENOMINATOR:** Clear. No fit is claimed; the
  denominator is the direct ball-table frame count.
- **B10 MOVED BAR:** Clear. No threshold, crop, coordinate contract, seed,
  precision mode, detector invocation, or verdict bar moved.

## NOT VERIFIED

- The causal source of the residual tuner-off route variance. The stateful
  tracker remains a plausible downstream location, not a proven cause.
- An isolated-idle pod condition for every G193 start. An unrelated G191 route
  lane was observed on the pod before and during the opening G193 work; it was
  never killed, restarted, or otherwise touched. G193's own six jobs did not
  overlap one another.
- Per-run wall times and shell exit statuses. The host's SSH capture ended at
  30 seconds while the remote route process continued; completed CSVs were
  directly parsed after every process had exited, but no exit-code record was
  retained.
- Any distributional rate, tracking quality, identity quality, coordinate
  accuracy, production daemon/keeper behavior, or result beyond this one video
  and `n = 3` per arm.

## Evidence-path check

At commit time this memo, its new extractor, and its focused test exist in this
worktree. The pre-existing user modification to `specs/G193_spec.md` was not
included in this change.

## Orchestrator verification and what this changes

**A2, recounted independently from the surviving pod CSVs:** tuner-on 1,400 /
1,342 / 1,322; tuner-off 1,246 / 1,348 / 1,268. All six reproduce exactly.

### The one-line fix would NOT have unblocked quality measurement

G190 showed `cudnn.benchmark = False` makes the DETECTOR bit-exact. This row shows
it does **not** make the ROUTE deterministic. So the human-gated change in
`PROPOSED_determinism_mode_2026-09-03.md` remains correct and worth applying -- a
reproducible detector is strictly better than a non-reproducible one -- but
**applying it would not have made a single quality row trustworthy**, and I should
not have implied otherwise. Anyone reading G190 alone would have drawn that wrong
conclusion; this row is the correction and they must be read together.

### The next candidate is already named, and G190 does not rule it out

Fable's review flagged `src/tracking/color_reid.py:77-79`: `cv2.kmeans(...,
cv2.KMEANS_PP_CENTERS)` with **no `cv2.setRNGSeed`**. `KMEANS_PP_CENTERS` is a
randomised initialisation, and OpenCV's RNG is separate from torch's.

**G190's finding that "seeds add nothing" does NOT cover this.** That test ran the
DETECTOR in isolation on one frame; it never reached the re-identification path
where the k-means runs. An unseeded OpenCV RNG inside the tracker is exactly the
shape of defect that survives a detector-only fix, and it is the leading candidate
for the residual variance measured here.

### An observation neither this row nor G189 has chased

Several survivor tuples in the table above are far outside the 1920x1020
post-crop frame -- `(-646.6, 1136.6, -494.4, 1276.2)` and `(482.1, -1699.5,
624.0, -1483.5)` among them, with coordinates below zero and beyond 1,700 px
above the frame. G189 saw the same shape (x1 = 2979, y1 = -35) and it was flagged
unresolved there too. It has now appeared in two independent rows and deserves its
own, rather than another mention in a NOT VERIFIED list.

**Not claimed:** that the k-means is the cause. It is a named, code-grounded
candidate that the next row tests, and "seeding OpenCV changes nothing either" is
an equally full result.
