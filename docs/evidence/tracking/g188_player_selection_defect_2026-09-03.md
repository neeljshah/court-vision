# G188 player-selection defect: Q8 premise falsified on the authoritative pod source

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), especially Q8 and
section B. This is diagnosis only. No production source, selection rule,
detector setting, coordinate contract, gate, threshold, daemon, keeper, or
feature flag was changed.

## Result: STOPPED before the requested two-sport delta

Q8 requires an independent reproduction of G187 frames 474 and 1377 before a
broader measurement, and requires a stop if the survivor box set differs from
the committed renders. The authoritative input was reachable on the pod, but
the current existing route did not reproduce G187.

| Source metadata | Measured value |
|---|---|
| Full path opened on pod | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` |
| Byte size | 2,931,985,407 |
| Decoded resolution | 1920x1080 |
| Video frame rate / frame count | 30/1 / 174,430 |
| Pod GPU at launch | NVIDIA GeForce RTX 3090, 24,576 MiB total, 352 MiB used |
| Invocation | `python3 scripts/run_clip.py --video data/footage_corpus/wnba__wnba_01.mp4 --frames 1200 --no-show --skip-features --data-dir /tmp/cx_g188_q8_20260903` |
| Exit / elapsed | 0 / 120.3 s |
| Fresh output | 1,549 player rows across 400 distinct player-row frames; `ball_tracking.csv` has 400 distinct attempted gameplay frames |
| G187 output for the same cap | 1,104 player rows across 394 player-row frames; 400 attempted gameplay frames |

### TOPCUT route check

G187 used `scripts/run_clip.py`, which constructs `UnifiedPipeline`. That route
applies `frame = frame[TOPCUT:]` before gameplay, YOLO, and player tracking;
`TOPCUT` is 60. The fresh Q8 run used that unchanged existing route, so its
detector/tracker input is a 1920x1020 post-crop image. No alternate crop was
introduced for this measurement.

### Required premise frames

The eligible denominator is **400 distinct attempted gameplay frames** in this
bounded route, source frames 180 through 1377 at stride 3. The frame rows below
are direct records from the pod-generated `tracking_data.csv`; coordinates are
the route's post-TOPCUT image-pixel bounding boxes. `raw person boxes` and a
fresh human on-court count are deliberately `NOT MEASURED`: the Q8 stop fired
before the required raw-versus-surviving sample could validly begin.

| Source frame | Eligible denominator | Fresh survivor count | G187 committed survivor count | Fresh surviving boxes `(player_id, team, x1, y1, x2, y2)` | Raw person boxes / human on-court count | Q8 comparison |
|---:|---|---:|---:|---|---|---|
| 474 | 400 distinct attempted gameplay frames | 2 | 3 | `(5, green, 567, 654, 690, 820)`; `(10, white, 1516, 99, 1609, 298)` | NOT MEASURED after Q8 stop | DIFFERENT count and box set |
| 1377 | 400 distinct attempted gameplay frames | 6 | 4 | `(2, green, 165, 792, 323, 930)`; `(5, green, 256, 744, 391, 921)`; `(6, white, 805, 157, 907, 405)`; `(8, white, 355, 771, 518, 930)`; `(9, white, 1500, 361, 1623, 607)`; `(10, white, 612, 142, 707, 356)` | NOT MEASURED after Q8 stop | DIFFERENT count and box set |

The first required decision point is already decisive at frame 474: the
authoritative-source rerun retains two rows, not G187's three non-court
survivors. Frame 1377 independently differs as well (six rather than four).
The aggregate differs too (1,549 rather than 1,104 rows). Therefore this is
not a reproducible G187 output and the requested 20-frame WNBA table, WNBA
dual-colour renders, tennis clip, and tennis table were not run.

The current pod checkout is not a Git worktree, so its exact revision cannot
be named. Its `player_detection.py` and `advanced_tracker.py` MD5s also differ
from this `track-a5` worktree, while its detector shim MD5 matches. G187 did
not archive source hashes. This makes a route/version difference plausible,
but the evidence does not attribute the non-reproduction to any one cause.

## Cause verdict

**Cannot separate on valid evidence.** The current authoritative-source pod
route does not reproduce G187's survivor set. Consequently, the evidence cannot
say whether the underlying detector found on-court players and selection dropped
them, or whether the detector did not find them. It also cannot measure the
cross-sport claim. This non-reproducibility is the Q8 finding; no fix is
proposed.

## Focused harness test

The existing additive evidence helper remains
`scripts/platformkit/tracking/g188_player_selection_defect.py`; no harness or
production code was changed in this re-dispatch.

```text
python -m pytest scripts/platformkit/tracking/test_g188_player_selection_defect.py -q
..                                                                       [100%]
2 passed in 0.98s
```

## VERIFIER_CONTRACT self-check: section B

- **B1 CIRCULAR METRIC:** Clear. The only counts are direct full-output counts
  and specified-frame survivor counts; no rows were excluded. No recall or
  precision rate is claimed.
- **B2 NON-ADDITIVE SCHEMA:** Clear. No schema, field, status, reader, or
  production file changed.
- **B3 FALL-THROUGH LOSS:** Clear. No gate, quarantine, queue, or selection
  behaviour changed.
- **B4 RE-CLAIM LOOP:** Clear. No claim, retry, ownership, daemon, or keeper
  behaviour changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. No repository file was copied into the
  pod checkout. The pre-existing `run_clip.py` route ran as an isolated process
  and only its generated CSV was pulled back for inspection.
- **B6 ORPHANS:** Clear. No module, import, test, or command was moved or
  retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear. No sampled performance claim is made. The
  two named premise frames are mandated Q8 checks, not a head-slice sample; the
  required even sample was correctly not started after the stop condition.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fitted metric or residual is
  claimed.
- **B9 DEGENERATE DENOMINATOR:** Clear. The stated denominator is 400 distinct
  attempted gameplay frames, not track IDs or a recycled unit.
- **B10 MOVED BAR:** Clear. No threshold, constant, backend default, crop,
  coordinate contract, bar, or verdict changed.

## NOT VERIFIED

- Per-frame raw detector boxes, confidences, and human on-court counts on the
  1080p WNBA source. Q8 stopped before that measurement began.
- The constructed 20-frame evenly spaced WNBA sample and its five dual-colour
  renders.
- Any tennis source, 20-frame tennis sample, dual-colour renders, or measured
  cross-sport comparison.
- Whether G187's underlying person detector found on-court players, its
  selection logic discarded them, or both.
- Whether the output difference is caused by an unarchived pod code/version
  difference, runtime state, model artifact, or another route condition.
- Any detection recall or precision rate. None is inferable from this Q8 stop.

## Orchestrator analysis at landing: what this actually means, and one hypothesis disproved

Verified in master: `test_g188_player_selection_defect.py` 2 passed.

**The headline is not the selection defect. It is that G187 does not reproduce.**
Same pod file, same byte size, same invocation, same 1200-frame cap, same
`run_clip.py` route with the same `TOPCUT=60` crop:

| | G187 | G188 rerun |
|---|---:|---:|
| player rows | 1,104 | **1,549** |
| player-row frames | 394 | **400** |
| frame 474 survivors | 3 | **2** |
| frame 1377 survivors | 4 | **6** |

That is a **40 pct difference in row count on identical input**, and neither
named frame matches. G187's own numbers are therefore not a stable measurement of
anything.

**A hypothesis I formed and then disproved, recorded so nobody re-runs it.** I
suspected my own mid-flight deploy: I pushed 4,327 `.py` files to the pod while
the G187 lane was alive. The timing rules it out. My tarball was built at
**14:44:47** and deployed immediately after; G187's measured run window, from its
own committed GPU sample timestamps, is **14:53:28 to 14:55:40**. The deploy
PRECEDED the run, and both G187 and this rerun executed against the same
`scripts/platformkit` and `domains` trees. `src/` was never deployed by me at all
(human-gated), so it is constant across both. **My deploy is not the explanation
and should not be cited as one.**

**What this costs.** Two landed statements are now weaker than they read:

- G187's `1,104 rows / 394 frames / 2.80 rows per frame` describes ONE run of a
  route that produces a materially different answer on the next run. It is not
  retracted as a record of what happened, but it must not be quoted as a property
  of the pipeline.
- My own eye-check correction on G187, in which I viewed the renders and said the
  detector misses nearly every on-court player, rests on THAT run's boxes. The
  rerun retains 6 survivors at frame 1377 where the render showed 4 non-court
  ones. **I withdrew the generalisation once already on G188's first stop; this
  withdraws the specific frame claims too.** What I saw in those images was real;
  what it says about the system is not established.

**The open question is now upstream of player selection: is this route
deterministic at all?** Until that is answered, no measurement taken through
`run_clip.py` on this pipeline can be trusted, including any future selection
study. That is the next row, and it is cheap: run the same clip twice more with a
fixed cap and compare row counts.

**Not claimed:** that the route IS non-deterministic. Two runs differing is
consistent with non-determinism, with an uncontrolled input difference nobody has
found yet, or with state carried between runs. Three data points and a controlled
repeat would separate those; this row has two and does not.
