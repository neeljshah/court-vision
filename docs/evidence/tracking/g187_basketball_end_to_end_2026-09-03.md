# G187 basketball end-to-end measurement

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A2, A3,
A4, A7, B1-B10, and Q8. This is a measurement only. No production code,
bar, threshold, gate, coordinate contract, corpus file, verdict, daemon, or
keeper was changed. No ledger/register row was written; adjudication remains
with the orchestrator.

## Outcome: rows produced

One isolated WNBA clip completed through the same `scripts/run_clip.py` route
that creates `UnifiedPipeline` and previously reached the failing `_build_court`
call. It exited with code 0 after 125.8 seconds. The prior `cv2.resize` failure
did not recur.

| Field | Measured value |
|---|---|
| Clip | `data/footage_corpus/wnba__wnba_01.mp4` |
| Invocation | `python3 scripts/run_clip.py --video data/footage_corpus/wnba__wnba_01.mp4 --frames 1200 --no-show --skip-features --data-dir /tmp/cx_g187_basketball_20260903` |
| Frame cap and rationale | `--frames 1200`, expressed by this pipeline in source-frame units. At the clip's stride 3 it bounds the attempted gameplay-frame denominator to 400, which is sufficient for an existence check and about two minutes at the known steady-state rate, not a full-clip run. |
| ELIGIBLE denominator | **400 attempted gameplay frames**, independently counted as 400 distinct `frame` values in `ball_tracking.csv`, absolute source frames 180 through 1377 inclusive at stride 3. `Frames processed: 1380` in the runner log is the final absolute frame index, not a count denominator. |
| Player rows | **1,104** rows in `tracking_data.csv` |
| Player-row frame coverage | **394 distinct frames**, absolute source frames 180 through 1377. This is an output count, not the eligible denominator. |
| Coordinate declaration | `coordinate_space=image_px` on all 1,104 rows |
| Process output | `/tmp/cx_g187_basketball_20260903/` on the pod; its `tracking_data.csv`, `ball_tracking.csv`, and other generated files were not copied into the repository. |

The denominator accounting is direct rather than inferred from the log: the
pipeline's `max_frames` is divided by its decode stride before its
`gameplay_frames >= max_frames` stop check. `1200 / 3 = 400`; the independent
CSV recount confirms exactly 400 distinct ball-row frames. The player table
contains 1,104 rows across 394 of those frames.

## Q8 premise-first re-measurement

Before launching the clip, a read-only pod probe executed the formerly failing
OpenCV construction and checked both protected corpus paths.

| Premise | Live result |
|---|---|
| `resources/2d_map.png` | exists; `cv2.imread` shape `(695, 1241, 3)` |
| Exact resize | `cv2.resize(img, (940, 500))` returned shape `(500, 940, 3)` |
| WNBA corpus | `data/footage_corpus/wnba__wnba_01.mp4` exists, 2,931,985,407 bytes |
| NCAA corpus | `data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` exists, 3,580,059,573 bytes |

Both premises held, so the bounded WNBA measurement proceeded. This does not
establish any outcome for the NCAA clip, which was not run.

## GPU utilization while the isolated run was unfinished

The sampler was launched separately with the new runner and sampled every ten
seconds until its exit marker appeared. It did not query, wait on, restart, or
otherwise interact with the daemon or keeper.

| UTC timestamp | Sample | GPU utilization | GPU memory used |
|---|---:|---:|---:|
| 2026-09-03T19:53:28+00:00 | 1 | 0% | 1 MiB |
| 2026-09-03T19:53:38+00:00 | 2 | 0% | 356 MiB |
| 2026-09-03T19:53:48+00:00 | 3 | 0% | 776 MiB |
| 2026-09-03T19:53:59+00:00 | 4 | 0% | 964 MiB |
| 2026-09-03T19:54:09+00:00 | 5 | 0% | 642 MiB |
| 2026-09-03T19:54:19+00:00 | 6 | 0% | 662 MiB |
| 2026-09-03T19:54:29+00:00 | 7 | 0% | 614 MiB |
| 2026-09-03T19:54:39+00:00 | 8 | 0% | 662 MiB |
| 2026-09-03T19:54:49+00:00 | 9 | 0% | 594 MiB |
| 2026-09-03T19:54:59+00:00 | 10 | 0% | 614 MiB |
| 2026-09-03T19:55:09+00:00 | 11 | 2% | 662 MiB |
| 2026-09-03T19:55:19+00:00 | 12 | 0% | 614 MiB |
| 2026-09-03T19:55:29+00:00 | 13 | 0% | 614 MiB |
| 2026-09-03T19:55:40+00:00 | 14 | 0% | 662 MiB |

This is a 14-sample series, all taken before the runner wrote its exit marker.
The peak sampled memory was 964 MiB and the peak sampled utilization was 2%.
Memory allocation alone is not evidence of sustained GPU inference utilization;
this measurement only reports the observed `nvidia-smi` samples.

## Required evenly spaced eye check

The five renders select the 0%, 25%, 50%, 75%, and 100% positions in the sorted
set of 394 player-row frames: 180, 474, 774, 1083, and 1377. Green rectangles
are each row's recorded image bounding box, labelled with its `player_id`.

| Row-frame position | Source frame | Rows | Render |
|---:|---:|---:|---|
| 0% | 180 | 1 | [overlay](g187_basketball_end_to_end_2026-09-03_frame_180_overlay.png) |
| 25% | 474 | 3 | [overlay](g187_basketball_end_to_end_2026-09-03_frame_474_overlay.png) |
| 50% | 774 | 1 | [overlay](g187_basketball_end_to_end_2026-09-03_frame_774_overlay.png) |
| 75% | 1083 | 1 | [overlay](g187_basketball_end_to_end_2026-09-03_frame_1083_overlay.png) |
| 100% | 1377 | 4 | [overlay](g187_basketball_end_to_end_2026-09-03_frame_1377_overlay.png) |

**Eye-check answer:** no, the emitted boxes do not consistently sit on
basketball players on the court. In particular, the sampled boxes include
courtside spectators or staff at frames 474, 1083, and 1377. This is a visual
observation about this one bounded output, not an adjudication, a changed
tracking-quality bar, or a coordinate-contract finding.

## VERIFIER_CONTRACT self-check

### A

- **A1:** No harness or production code was added, so no per-file test applies.
- **A2:** Recomputed from the generated CSVs: `tracking_data.csv` has 1,104
  rows and 394 unique `frame` values; `ball_tracking.csv` has 400 rows and 400
  unique `frame` values, spanning 180..1377.
- **A3:** The five eye-check frames are evenly spaced across the complete sorted
  394-frame player-row decision set, not a head slice.
- **A4:** Row count and unique frame count are both reported. The eligible
  denominator is the distinct 400 attempted gameplay frames, not track IDs.
- **A5:** Evidence-only addition; no schema field or reader changed.
- **A6:** No archive landing, register update, or ledger append was performed:
  the user directed this measurement to remain in `track-a5` and explicitly
  reserved adjudication/ledger ownership to the orchestrator.
- **A7:** Immediately before commit, this memo, the five named render paths,
  `VERIFIER_CONTRACT.md`, and the user-owned `G187_spec.md` are checked for
  existence.

### B

- **B1 CIRCULAR METRIC:** Clear. All generated player rows and all 400 attempted
  ball-row frames are included in their stated counts; no failing rows were
  excluded.
- **B2 NON-ADDITIVE SCHEMA:** Clear. No schema, field, status, or reader changed.
- **B3 FALL-THROUGH LOSS:** Clear. No gate, quarantine, corpus, or queue action
  was taken.
- **B4 RE-CLAIM LOOP:** Clear. No claim, retry, or ownership logic changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. No repository file was copied or
  deployed to the pod. The existing route was invoked as its own process; the
  temporary output and ephemeral visual-render code are measurement artifacts.
- **B6 ORPHANS:** Clear. No module, import, test, or command was moved or retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear. Render positions are 0/25/50/75/100% of the
  sorted row-frame set.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fitted metric or residual is claimed.
- **B9 DEGENERATE DENOMINATOR:** Clear. The denominator is 400 distinct attempted
  decoded gameplay frames, independently counted from the ball table.
- **B10 MOVED BAR:** Clear. No threshold, gate, coordinate contract, or verdict
  changed.

## NOT VERIFIED

- Any result for `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4`; it was
  premise-checked but not run under this one-clip existence measurement.
- Court-coordinate accuracy, player coverage, identity accuracy, or any
  tracking-quality gate. The declared coordinate space is `image_px`, and the
  eye check observed inconsistent on-court player placement.
- Sustained GPU compute utilization. The sampler reports low instantaneous
  utilization with nonzero memory allocation; it does not attribute why.
- A full-clip result, throughput rate, or any production/daemon behavior. The
  process was deliberately capped and ran outside the daemon/keeper.
- Whether the runner's `Frames processed: 1380` presentation is appropriate;
  its value was treated as the final absolute frame index, while the durable
  denominator comes from the independent 400-frame CSV recount.

## Orchestrator eye check at landing: the lane UNDERSTATED this

The memo says the boxes "do not consistently sit on basketball players on the
court". I viewed the renders myself before landing, and the problem is larger
than inconsistency. **The dominant error is MISSES, not misplacements.**

- **Frame 474 (3 rows):** roughly ten WNBA players are clearly visible, well
  separated and well lit. One emitted box is unmistakably a courtside SPECTATOR
  in the foreground crowd; one sits on the sideline edge; only one covers actual
  players. About eight obvious on-court players carry no box at all.
- **Frame 1377 (4 rows):** ten players are again clearly visible on an open
  court. One box is a seated spectator in the near crowd; the other three sit on
  bench or staff figures behind the far baseline. **By direct inspection, not one
  on-court player is detected in this frame.**

The aggregate agrees: 1,104 rows over 394 frames is **2.80 rows per frame against
roughly ten players on court**, so even before asking whether a box is correct,
the detector is emitting well under a third of the people it should.

**This is the same defect class already recorded for tennis in G18** -- "courtside
non-players that `detect_players` picks as the per-half box", where the chair
umpire and a ball kid were emitted while neither real player was. It now has a
second sport, which makes it a cross-sport player-SELECTION problem rather than a
tennis quirk.

**What this does NOT change.** The row's headline stands exactly as measured: the
`_build_court` crash is gone and the route completes end to end, 1,104 rows in
125.8 s, exit 0. That was the question asked. Output QUALITY is a separate matter
and was never claimed here; it is recorded so no reader mistakes "it runs" for
"it works". No bar, gate, verdict or contract is touched by this observation.

**Not claimed:** any detection rate. Two frames were inspected by eye out of five
rendered and 394 with rows. That is an existence observation, not a recall
measurement, and the follow-on row must measure it properly rather than quote
these two frames as a rate.
