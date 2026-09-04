# G225 Detector Capacity Sweep - 2026-09-04

## Verdict

**ACCEPT (measurement only): capacity changes emitted person volume and resource
use on the required basketball adapter route, but raw/emitted counts are not
on-court-player quality. No production default change is proposed.**

This executes `docs/evidence/tracking/specs/G225_spec.md`, including its
2026-09-04 adapter amendment, and cites
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. No `src/`, `domains/`,
threshold, `imgsz`, confidence, `min_players`, coordinate contract, daemon,
keeper, or production configuration changed. The optional amateur pass was not
run: Baseline A is the required same-clip comparison.

## Machine, hold check, input, and route

The shared RTX 3090 pod at `/workspace/nba-ai-system` was used because the
adapter and source are pod-resident. At 2026-09-04T07:55:51Z, the live check
found keeper/track daemon, foundry runner, and in-play capture runner, but no
G211, G211b, or G225 measurement process. No permanent resident was changed.

| Input opened | Bytes | Resolution | Frames | Use |
|---|---:|---|---:|---|
| `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080 | 174,430 at 30 FPS | Every arm, 6,000 adapter evaluations |

Every valid run used this command shape, varying only `<model>`:

```text
cd /workspace/nba-ai-system
CV_DETECTOR_MODEL=<model>.pt /usr/local/bin/python -m scripts.platformkit.adapter_run basketball \
  data/footage_corpus/wnba__wnba_01.mp4 <game_id> --max-frames 6000
```

The temporary probe only counts/renders raw adapter boxes; it does not alter
adapter inference arguments. The adapter capacity seam is `CV_DETECTOR_MODEL`,
not `src`'s `yolo_model` dictionary. Thus the `src` upgrade branch remains a
small negative: it is not exercised on this mandated adapter route. No `src`
file was modified.

Pod route identities, identical in all arms: `adapter_run.py`
`e4abc2f5e4e4fb2a977ca6beb2fed854e33e829eb0a5d96cef8645680f6181c5`;
basketball `adapter.py`
`1ecf483df26b19c44d1fa25297caed845e5952fbfdd9b704f95a6125f4366c15`;
detection `shim.py`
`a25ef1fb801d3770546711601dcbaacaf599778d01e01bf18d6432140718b6d7`;
`tracking_timebase.py`
`0dc67ff28e40e1c8b1dba9b191ea5f61d3b15f8904167402c54e9e75c2e2300c`;
`tracking_harness.py`
`59f60428c5e82460f13e009a04db05d0b27e4a567aff33a324fb7b40bea87f1d`;
`tracking_schema.py`
`72d21ae1dddded5bc6903dcbbd442de3f47240d5491305c1b6bd933bd007197e`;
and `run_environment.py`
`5129bb37e4e23aba93883239078825292136feb331c82ac85c56ee31298cb931`.

## Disk guard and actual weights

`df` was never used. Preflight `du -sm /workspace/nba-ai-system/data` was
32,393 MB. The preflight and every valid arm ran a 4 MiB `dd ... conv=fsync`
probe: all ten wrote 4,194,304 bytes with SHA-256
`bb9f8df61474d25e71fa00722318cd387396ca1736605e1248821cc0de3d3af8` and
were immediately removed.

| Arm | Actually loaded file | SHA-256 | Status |
|---|---|---|---|
| `yolov8n` | `/workspace/nba-ai-system/yolov8n.pt` | `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36` | Valid |
| `yolov8s` | `/workspace/nba-ai-system/yolov8s.pt` | `1f47a78bf100391c2a140b7ac73a1caae18c32779be7d310658112f7ac9aa78a` | Valid, auto-downloaded |
| `yolov8m` | `/workspace/nba-ai-system/yolov8m.pt` | `5d4a90cdc7a21786cc59cd19778e9eafff836df9e2da32524737c7ee6efe4fe5` | Valid, auto-downloaded |

The auto-downloaded small/medium weights were removed after capture, freeing
22,588,772 and 52,136,884 bytes (74,725,656 total). An earlier invalid draw
ran from `/root`; it was voided and its exact outputs plus downloaded nano
weight were removed, freeing 26,357,828 bytes. No corpus input was deleted.

## n=3 distributions and Baseline A comparison

All entries are three complete 6,000-evaluated-frame runs. The `min / median /
p90 / max` is within each run; bracketed values are r1/r2/r3. Survivors were
independently recomputed from every retained pod table. On this direct
image-space adapter, every valid raw box becomes an emitted row, so raw and
survivor counts match. That is a route property, not on-court correctness.

| Arm | Raw boxes/frame and survivors/frame | Rows/survivors [r1,r2,r3] | Wall s/frame [r1,r2,r3] | 58,143-frame projection, minutes [r1,r2,r3] |
|---|---|---:|---:|---:|
| Baseline A / `yolov8n` | 0 / 11.0 / 16 / 27 | 64,171 / 64,171 / 64,171 | 0.016038 / 0.016030 / 0.016191 | 15.54 / 15.53 / 15.69 |
| `yolov8s` | 0 / 20.0 / 27 / 41 | 113,733 / 113,733 / 113,733 | 0.017953 / 0.017749 / 0.017950 | 17.40 / 17.20 / 17.39 |
| `yolov8m` | 0 / 16.0 / 25 / 35 | 98,979 / 98,979 / 98,979 | 0.018981 / 0.019059 / 0.019509 | 18.39 / 18.47 / 18.91 |

Nano reproduces Baseline A exactly: 64,171 rows, median 11.0 survivors/frame,
and track-length median 205. Independent table statistics are nano 1 / 205 /
730 / 2,270 (207 IDs), small 2 / 283 / 855 / 2,155 (299 IDs), and medium 2 /
277 / 767 / 3,212 (267 IDs); every run has zero duplicate `(frame, track_id)`
rows. Small emits 77.2 percent more rows than nano; medium emits 54.2 percent
more than nano but 13.0 percent fewer than small. Capacity is not monotonic in
raw person volume.

## GPU, memory, CPU, and repeatability

These are 1-second samples. CPU is aggregate adapter-process percent from
`ps`; GPU samples are device-wide `nvidia-smi` readings and include shared pod
load. Per-run pre/post load contexts and full resource series are retained.

| Arm | GPU utilization median [r1,r2,r3] / p90 / max | GPU MiB median [r1,r2,r3] / peak | CPU percent median [r1,r2,r3] |
|---|---|---|---|
| `yolov8n` | 12 / 12 / 12; p90 13; max 14 | 374 / 374 / 374; peak 635 | 470 / 476 / 465 |
| `yolov8s` | 16 / 16 / 16; p90 18; max 20 | 418 / 418 / 418; peak 679 | 411 / 416 / 411 |
| `yolov8m` | 30 / 29 / 29; p90 31; max 35 | 482 / 482 / 482; peak 743 | 395.5 / 406 / 375 |

Each model's three raw-box series, emitted rows, and track statistics are
identical. Timing spreads are nano 1.0 percent, small 1.1 percent, and medium
2.8 percent max/min, below the 11.9 percent nano-to-small and 18.8 percent
nano-to-medium median-time changes. The sweep resolves these count/time
differences; it makes no determinism claim about the legacy `run_clip` route.

## Mandatory eye check: raw boxes are not quality

These evenly spaced replicate-1 renders report raw boxes / single-labeller
visibly on-court basketball players with a raw box. All 27 renders (three per
repetition per arm) are retained; the matching raw series are identical across
the three repetitions.

| Arm | Evaluated index 0 | 2,999 | 5,999 |
|---|---:|---:|---:|
| `yolov8n` | 2 / 0 | 8 / 2 | 6 / 5 |
| `yolov8s` | 6 / 2 | 19 / 2 | 14 / 7 |
| `yolov8m` | 5 / 4 | 9 / 2 | 12 / 7 |

Small's 19 raw boxes at index 2,999 still identify only two visibly on-court
players; the rest are spectators, bench/side-line people, or duplicate boxes.
It also boxes a schedule graphic at index 5,999. Medium has more visibly
on-court boxes in the wide tip frame (4 versus nano's 0) and late frame (7
versus 5), but it also detects non-players. More boxes/rows is therefore not a
quality win; this eye check is a single-labeller observation, not recall.

## Evidence, tests, and self-check

`docs/evidence/tracking/g225_detector_capacity_sweep_valid/` exists before
commit. Its `summary.json` holds all run distributions, contexts, hashes,
weights, and resource series. Each `<arm>_r<1-3>/artifact/` has raw-box JSON,
loaded-weight JSON, resource samples, disk proof, adapter log, and renders at
0/2,999/5,999. All evidence paths named in this memo exist.

```text
python -m pytest scripts/platformkit/tracking/test_g225_detector_capacity_sweep.py -q
3 passed
```

- B1/B9: named 6,000-frame denominator is independent of emitted rows.
- B2-B6/B10: no schema, gate, reader, claim flow, deployment, module, or
  threshold changed.
- B7: evenly spaced render indices, not a head slice. B8: no fitted residual.
- B11: n=3 output and timing distributions are retained, not a single run.
- A7/A9/A11: evidence paths, full input identity, and route hashes are above.
- A12: neither new harness file is in the existing LOC allowlist.

## NOT VERIFIED

- On-court recall/precision, coordinates, identities, ball tracking,
  calibration, or a full-frame manual label set.
- Clean-machine timing/GPU figures; permanent shared-pod residents remained.
- Amateur behavior, a production default, TensorRT behavior, or the legacy
  `run_clip` route.
