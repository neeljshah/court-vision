# G189 route determinism reproduction

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), self-checked against
section B. This is a measurement only. No code, threshold, seed, crop, detector
setting, coordinate contract, gate, verdict, daemon, or keeper was changed.

## Measurement verdict: NON-DETERMINISTIC

The three fresh executions of the unchanged `run_clip.py` route do **not** agree
with each other. They produced 1,246, 1,360, and 1,247 player rows respectively
on the same authoritative file and cap. This is an existence check with `n = 3`,
not an estimate of a variation rate. Therefore every measurement made through
this route, including G187's landed counts, is one sample of a distribution until
the source of variation is settled.

This result does not guess at the cause of the G187/G188 difference. The earlier
mid-flight-deploy explanation remains disproved by its recorded timing.

## Fixed input and invocation

| Field | Value |
|---|---|
| Pod source path opened | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` |
| Runner-relative source path | `data/footage_corpus/wnba__wnba_01.mp4` |
| Byte size | 2,931,985,407 |
| Decoded resolution | 1920x1080 |
| Cap | `--frames 1200` |
| Exact command, run 1 | `python3 scripts/run_clip.py --video data/footage_corpus/wnba__wnba_01.mp4 --frames 1200 --no-show --skip-features --data-dir /tmp/cx_g189_route_determinism_20260903_run1` |
| Exact command, run 2 | `python3 scripts/run_clip.py --video data/footage_corpus/wnba__wnba_01.mp4 --frames 1200 --no-show --skip-features --data-dir /tmp/cx_g189_route_determinism_20260903_run2` |
| Exact command, run 3 | `python3 scripts/run_clip.py --video data/footage_corpus/wnba__wnba_01.mp4 --frames 1200 --no-show --skip-features --data-dir /tmp/cx_g189_route_determinism_20260903_run3` |
| Deliberately different item | Only the mandatory isolated `--data-dir` path per run |

The 1080p pod source above is authoritative. The distinct 1280x720
`g130_recensus/` file was not opened.

`attempted gameplay frames` is the eligible denominator in every row below: the
distinct `frame` values in that run's `ball_tracking.csv`, not the `--frames`
argument, player rows, or player-row frames. All three fresh runs have 400 such
frames, source frames 180 through 1377 inclusive at stride 3.

## Historical and fresh results

Boxes use the emitted tuple `(player_id, team, x1, y1, x2, y2)` from the
post-TOPCUT image-pixel route. `NOT ARCHIVED` is an explicit absence, not an
empty survivor set.

| Record | Player rows | Distinct player-row frames | ELIGIBLE denominator: attempted gameplay frames | Frame 474 survivors | Frame 1377 survivors |
|---|---:|---:|---:|---|---|
| G187 (historical run 0) | 1,104 | 394 | 400 | 3; exact tuples NOT ARCHIVED | 4; exact tuples NOT ARCHIVED |
| G188 v2 (historical run 0b) | 1,549 | 400 | 400 | 2: `(5, green, 567, 654, 690, 820)`; `(10, white, 1516, 99, 1609, 298)` | 6: `(2, green, 165, 792, 323, 930)`; `(5, green, 256, 744, 391, 921)`; `(6, white, 805, 157, 907, 405)`; `(8, white, 355, 771, 518, 930)`; `(9, white, 1500, 361, 1623, 607)`; `(10, white, 612, 142, 707, 356)` |
| Fresh run 1 | 1,246 | 400 | 400 | 2: `(5, green, 1296, 378, 1434, 609)`; `(8, white, 2979, 1012, 3113, 1180)` | 2: `(5, green, 717, 304, 840, 550)`; `(6, white, 474, 280, 602, 543)` |
| Fresh run 2 | 1,360 | 400 | 400 | 3: `(2, green, 497, -35, 624, 214)`; `(4, green, 706, 652, 855, 819)`; `(8, white, 1515, 99, 1611, 298)` | 6: `(3, green, 256, 744, 391, 921)`; `(4, green, 582, 655, 750, 822)`; `(5, green, 717, 304, 840, 550)`; `(7, white, 659, 478, 812, 770)`; `(8, white, 355, 771, 518, 930)`; `(9, white, 612, 142, 707, 356)` |
| Fresh run 3 | 1,247 | 390 | 400 | 2: `(5, green, 706, 652, 855, 819)`; `(8, white, 1719, 135, 1869, 364)` | 2: `(2, green, 582, 655, 750, 822)`; `(6, white, 659, 478, 812, 770)` |

G187's committed memo records the premise-frame survivor counts and links
renders, but it does not archive the underlying tuple lists. The table preserves
that limitation rather than deriving boxes from a render. G188 v2's tuple lists
are transcribed from its committed per-frame table.

## Per-run records

| Field | Fresh run 1 | Fresh run 2 | Fresh run 3 |
|---|---|---|---|
| Pod output directory | `/tmp/cx_g189_route_determinism_20260903_run1` | `/tmp/cx_g189_route_determinism_20260903_run2` | `/tmp/cx_g189_route_determinism_20260903_run3` |
| Start UTC | 2026-09-03T20:37:30Z | 2026-09-03T20:39:52Z | 2026-09-03T20:42:05Z |
| Start GPU query `utilization.gpu,memory.used` | `0, 352` | `0, 352` | `0, 352` |
| Inference device | GPU: device `0`, FP16 enabled | GPU: device `0`, FP16 enabled | GPU: device `0`, FP16 enabled |
| `run_clip.py` exit | 0 | 0 | 0 |
| Runner elapsed time | 115.8 s | 115.0 s | 113.9 s |
| `tracking_data.csv` rows, direct recount | 1,246 | 1,360 | 1,247 |
| Distinct player-row frames, direct recount | 400 | 400 | 390 |
| ELIGIBLE denominator: distinct attempted gameplay frames, direct recount | 400 | 400 | 400 |
| Player-row frame range | 180..1377 | 180..1377 | 180..1377 |
| Attempted-gameplay frame range | 180..1377 | 180..1377 | 180..1377 |

Each runner printed the standard CUDA/FP16 (`half`) path. The post-run bounded
raw-detector check below independently instantiated the route detector on GPU
device 0 with FP16 enabled. No run used a CPU inference fallback. The GPU values
are mandatory run-start snapshots, not a sustained-utilization claim.

## One bounded location step: raw detector at frame 474

Because the three full-route outputs disagree, one additional bounded step ran
the existing raw person detector three times, each in a fresh pod Python process,
on source frame 474 after the existing `TOPCUT=60` crop. It used the route's
unchanged default invocation: `classes=[0]`, `conf=0.22`, `imgsz=640`,
`half=True`, and `device=0`. This is a diagnostic observation; none of those
values was set or changed in the pipeline.

Each invocation emitted 15 raw person boxes, but its raw coordinates and/or
confidence values were not byte-identical. Thus detector-level variation is
observed at frame 474. This bounded result does not establish how much of the
full-route survivor variation comes from detector output versus subsequent
stateful tracker processing.

Raw boxes are `(x1, y1, x2, y2, confidence)` on the 1920x1020 post-TOPCUT frame:

```text
raw invocation 1
(1308.000,403.500,1416.000,594.750,0.68945) (1471.500,377.250,1552.500,627.750,0.68701) (1647.000,778.500,1731.000,904.500,0.46289) (1744.500,159.656,1855.500,348.000,0.43872) (459.000,582.750,568.500,807.000,0.35229) (1519.500,113.625,1588.500,282.000,0.34326) (712.500,666.750,832.500,801.750,0.33203) (1008.750,398.250,1110.750,585.750,0.32764) (1186.500,697.875,1323.000,811.500,0.32422) (581.625,667.500,665.625,805.500,0.28223) (505.500,518.250,602.250,755.250,0.25977) (175.969,531.000,275.625,685.500,0.24365) (82.500,526.500,165.562,683.250,0.24146) (1716.000,772.500,1848.000,913.500,0.24146) (1518.000,721.875,1623.000,916.500,0.22949)

raw invocation 2
(1308.000,403.500,1416.000,594.000,0.68945) (1471.500,377.250,1552.500,627.750,0.68701) (1647.000,778.500,1731.000,904.500,0.46289) (1744.500,159.656,1855.500,348.000,0.43970) (459.000,582.750,568.500,807.750,0.35229) (1519.500,113.625,1588.500,282.000,0.34326) (712.500,666.750,832.500,801.750,0.33203) (1008.750,398.250,1110.750,585.750,0.32764) (1186.500,697.875,1323.000,811.500,0.32520) (581.625,667.500,665.625,805.500,0.28223) (505.500,518.250,602.250,755.250,0.26050) (175.969,531.000,275.625,685.500,0.24438) (82.500,526.500,165.562,683.250,0.24219) (1716.000,772.500,1848.000,913.500,0.24146) (1518.000,721.875,1623.000,916.500,0.22949)

raw invocation 3
(1308.000,403.500,1416.000,594.000,0.68945) (1471.500,377.250,1552.500,627.750,0.68701) (1647.000,778.500,1731.000,904.500,0.46289) (1744.500,159.656,1855.500,348.000,0.43872) (459.000,582.750,568.500,807.000,0.35303) (1519.500,113.625,1588.500,282.000,0.34253) (712.500,666.750,832.500,801.750,0.33203) (1008.750,398.250,1110.750,585.750,0.32764) (1186.500,697.875,1323.000,811.500,0.32520) (581.625,667.500,665.625,805.500,0.28149) (505.500,518.250,602.250,755.250,0.26050) (175.969,531.000,275.625,685.500,0.24365) (82.453,526.500,165.375,683.250,0.24219) (1716.000,772.500,1848.000,913.500,0.24146) (1515.750,723.000,1623.000,909.000,0.22888)
```

## VERIFIER_CONTRACT self-check: section B

- **B1 CIRCULAR METRIC:** Clear. Every row in each `tracking_data.csv` and
  every distinct frame in each `ball_tracking.csv` participates in the direct
  recount. No output was excluded.
- **B2 NON-ADDITIVE SCHEMA:** Clear. No schema, field, reader, or status changed.
- **B3 FALL-THROUGH LOSS:** Clear. No gate, queue, quarantine, or selection path
  changed.
- **B4 RE-CLAIM LOOP:** Clear. No claim, retry, ownership, daemon, or keeper
  behavior changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. No repository file was copied or
  deployed to the pod. The pre-existing pod route ran only into isolated `/tmp`
  data directories.
- **B6 ORPHANS:** Clear. No module, import, test, or command was moved or retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear. This is the required reproduction row; the
  named premise frames are mandated by the acceptance rule, not a sampled quality
  claim.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fitted metric or residual is claimed.
- **B9 DEGENERATE DENOMINATOR:** Clear. The denominator is the 400 distinct
  attempted gameplay frames per fresh run, independently recounted from the ball
  table; it is not a track ID or player-row count.
- **B10 MOVED BAR:** Clear. No threshold, seed, crop, backend default, bar,
  coordinate contract, or verdict was changed.

## NOT VERIFIED

- The precise mechanism behind the full-route non-determinism, or whether one
  mechanism explains both the historical and fresh differences.
- The causal contribution of the observed frame-474 detector variation to the
  much larger survivor and aggregate variation after stateful tracking.
- A distributional variation rate, any stability statistic, or behavior beyond
  this capped `n = 3` reproduction on this one authoritative file.
- G187's exact emitted survivor tuples at frames 474 and 1377; only its counts
  and renders were committed.
- Sustained GPU utilization. Only the required GPU state at each fresh-run start
  is reported here.
- Tracking quality, player coverage, identity quality, coordinate accuracy, or
  any production daemon/keeper outcome.

## Evidence-path check (A7)

At commit time this memo and its cited verifier contract exist in this worktree:
`docs/evidence/tracking/g189_route_determinism_2026-09-03.md` and
`docs/evidence/tracking/VERIFIER_CONTRACT.md`.

## Orchestrator verification and analysis at landing

**A2, recounted independently from the pod CSVs rather than from the lane's
table:** run 1 = 1,246 rows / 400 distinct player-row frames / 400 ball frames;
run 2 = 1,360 / 400 / 400; run 3 = 1,247 / 390 / 400. All reproduce exactly.

**The full spread across five runs of one command on one file:**
1,104 (G187), 1,246, 1,247, 1,360, 1,549 (G188 v2). Min to max is **40 pct**.

### The mechanism is visible in this row, and it is coherent

The lane's bounded location step is the important part. Three fresh raw detector
invocations on frame 474 each emitted **exactly 15 boxes**, but not byte-identical
ones -- coordinates and confidences differ in low digits (`594.750` vs `594.000`;
`0.24365` vs `0.24438` vs the third invocation's values).

Every run reports `device 0, FP16 enabled`. **FP16 GPU inference is not
bit-reproducible** -- algorithm selection and reduction order vary between
processes. So the chain is: tiny numeric differences at the detector, a
confidence threshold at `conf=0.22` that near-threshold boxes flip across, and a
STATEFUL tracker downstream that amplifies a single flipped detection into a
different track, a different id, and a different row count for the rest of the
clip. Small input noise, large output variance. That is consistent with
everything measured here, and it is **a hypothesis about the cause, not a proven
one** -- proving it needs a deterministic-mode rerun, which this row did not do
and deliberately did not force.

### A correction to my own earlier reading

I reported the RTX 3090 as effectively unused after sampling 0 pct utilization
with memory allocated. **That was wrong about the device and right about the
symptom.** These runs are explicitly on GPU device 0 with FP16, so inference does
reach the GPU. What the 0 pct sampling actually shows is that inference is a
small fraction of wall time: 400 evaluated frames in ~115 s is about 3.5 fps,
which for YOLO FP16 on a 3090 means the pipeline is bottlenecked in decode,
tracking or re-ID, not in the detector. The GPU is idle because there is little
for it to do, not because it is unused.

### An observation the lane did not flag

Some survivor tuples fall OUTSIDE the 1920x1020 post-TOPCUT frame: run 1 frame
474 carries `(8, white, 2979, 1012, 3113, 1180)` with x1 = 2979 on a 1920-wide
frame, and run 2 carries `(2, green, 497, -35, 624, 214)` with a negative y1.
Either these tuples are in a different coordinate space than the raw boxes, or
out-of-bounds rows are being emitted. **Not resolved here and not claimed as a
defect** -- but G18 previously recorded an `oob_pct` failure class in tennis, so
it is worth a dedicated check rather than leaving it in a table unremarked.

### What this invalidates

- **G187's counts are one sample of a distribution**, formally now, not as a
  suspicion. So are G188 v2's.
- **My own eye-check on G187's renders is one sample too.** I viewed those images
  and drew conclusions about the detector from them; a different run of the same
  command would have produced different boxes to look at. The observation stands
  as a record of that run and nothing more.
- **Any future quality measurement through this route must either establish a
  deterministic mode first, or report a distribution over repeats.** A single run
  is not evidence about this pipeline.

This row is the check that should have preceded the quality work, not followed it.
