# G200 Pod Concurrency Headroom - 2026-09-03

## Verdict

For this route on the shared S1 pod, schedule **two concurrent jobs**, not one
and not four.  N=2 produced the best observed throughput: **0.567 jobs/minute**
(1.33x N=1).  Per-job time was already 1.52x the N=1 baseline at N=2; the
throughput benefit disappears decisively at N=4 and worsens further at N=8.

The first observed practical constraint is a **shared route execution path,
most consistent with video decode/storage or another shared pipeline stage**.
It is not host core count, host RAM capacity, or GPU-memory capacity in these
measurements: N=8 averaged only 24.12 route CPU-cores on a 256-core host,
peaked at 109.15 GiB host-used RAM on a 1007 GiB host, and peaked at 6506 MiB
(26.5%) of 24576 MiB GPU memory.  Direct decode-engine and storage-I/O counters
were not collected, so this is an attribution from the resource series rather
than proof that NVDEC or disk is the exact sub-stage.

This is a shared-machine result, not an idle-pod capacity claim.  G203 was
active before and after every arm and unrelated daemon children changed during
the run.  The full snapshots and five-second resource samples are in the
[machine-readable record](g200_pod_concurrency_headroom_2026-09-03_records.json).

## Fixed route and controls

All 15 jobs used exactly:

```text
/usr/local/bin/python /workspace/nba-ai-system/scripts/run_clip.py \
  --video /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 \
  --frames 1200 --no-show --skip-features --data-dir /tmp/g200_<token>_n<N>_job<J>_data
```

The clip was the supplied A9 input: 2,931,985,407 bytes, 1920x1080, 174430
frames.  No thread count, batch size, image size, confidence threshold,
precision, coordinate contract, production code, daemon, or keeper was changed.
Each job had a unique `--data-dir`; the harness removed only its exact
`/tmp/g200_*_data` directories after each completed arm.  No corpus data was
deleted.

Before every arm, the harness made and removed a 4 MiB `dd` test file and
recorded `du -sm /workspace/nba-ai-system/data`.  All four guards passed.
The recorded data-directory sizes were 28855/29331 MiB (N=1 before/after),
29339/29957 MiB (N=2), 29973/33092 MiB (N=4), and 33124/28851 MiB (N=8).
`df` was deliberately not used as a quota check.

Pod source hashes (A11):

```text
047dd04e9b12b588c560f68dbab32aa1855f791c2e1a46f19f4e082f50c4f331  src/pipeline/unified_pipeline.py
df2ae698ae03e804f67639434d8303638aea9087c3169c016af5a3734dd474d7  src/tracking/advanced_tracker.py
```

## Throughput and resource result

`Aggregate route CPU` is the mean sum of the per-job process-tree CPU samples;
one hundred percent equals one logical core.  GPU and host-memory metrics are
global pod samples, therefore include the concurrently running pod workload.
Wall time is from job process start to finish; arm wall brackets the full
concurrent launch through final job completion.

| N | Arm wall (s) | Jobs/min | Mean job wall (s) | Mean slowdown vs N=1 | Mean aggregate route CPU | Peak host-used RAM | Peak GPU memory | Peak GPU util |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 140.40 | 0.427 | 137.95 | 1.00x | 1131.04% (11.31 cores) | 81.50 GiB | 2553 MiB (10.4%) | 91% |
| 2 | 211.58 | 0.567 | 210.11 | 1.52x | 1773.79% (17.74 cores) | 74.05 GiB | 2182 MiB (8.9%) | 77% |
| 4 | 816.36 | 0.294 | 807.88 | 5.86x | 2373.07% (23.73 cores) | 91.57 GiB | 3584 MiB (14.6%) | 54% |
| 8 | 3203.72 | 0.150 | 3011.32 | 21.83x | 2411.73% (24.12 cores) | 109.15 GiB | 6506 MiB (26.5%) | 77% |

N=2 is 32.7% faster in aggregate throughput than N=1.  N=4 is 48.3% slower
than N=1, and N=8 is 64.9% slower than N=1.  Thus the first per-job degradation
appears at N=2; the usable throughput ceiling on this measured shared pod is
N=2.

## Per-job timing records (B13/Q9)

`Peak RSS` and `mean CPU` are per-job process-tree measurements, rather than
row counts.  Every route exited zero.

| N | Job | Wall (s) | Slowdown vs N=1 | Mean CPU | Peak RSS (GiB) | Exit |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 137.95 | 1.000x | 1131.04% | 3.13 | 0 |
| 2 | 1 | 209.18 | 1.516x | 876.44% | 3.16 | 0 |
| 2 | 2 | 211.03 | 1.530x | 897.35% | 3.09 | 0 |
| 4 | 1 | 815.82 | 5.914x | 617.35% | 3.41 | 0 |
| 4 | 2 | 808.24 | 5.859x | 585.70% | 3.35 | 0 |
| 4 | 3 | 807.71 | 5.855x | 585.66% | 3.19 | 0 |
| 4 | 4 | 799.76 | 5.797x | 584.36% | 3.19 | 0 |
| 8 | 1 | 3196.74 | 23.173x | 309.39% | 3.34 | 0 |
| 8 | 2 | 3189.44 | 23.120x | 310.62% | 3.24 | 0 |
| 8 | 3 | 3192.80 | 23.144x | 315.29% | 3.31 | 0 |
| 8 | 4 | 3196.92 | 23.174x | 316.44% | 3.34 | 0 |
| 8 | 5 | 3048.53 | 22.099x | 303.21% | 3.35 | 0 |
| 8 | 6 | 2249.33 | 16.305x | 280.14% | 3.27 | 0 |
| 8 | 7 | 2828.73 | 20.505x | 266.71% | 3.31 | 0 |
| 8 | 8 | 3188.04 | 23.110x | 309.92% | 3.29 | 0 |

## Load context beside each timing

The pod had 256 cores in every before/after snapshot.  The daemon and keeper
were neither restarted nor killed.  The daemon's own supervisor PID used about
0.2% CPU throughout; its worker activity and other pod work remain in the raw
top-process snapshots.  `G203` denotes the bounded independent route work.

| N | Timing interval (UTC) | G203 before -> after | Daemon / keeper before -> after |
|---:|---|---|---|
| 1 | 01:27:36 -> 01:29:57 | route PID 1671314: 78.4%, 2.92 GiB -> route PID 1946737: 42.7%, 0.79 GiB | daemon 0.2%, 308.6 MiB -> 0.2%, 308.6 MiB; keeper 0.0%, 3.4 MiB both |
| 2 | 01:30:00 -> 01:33:32 | route PID 1946737: 44.8%, 0.79 GiB -> 30.4%, 0.83 GiB | daemon 0.2%, 293.6 MiB -> 0.2%, 293.6 MiB; keeper 0.0%, 3.4 MiB both |
| 4 | 01:33:34 -> 01:47:11 | route PID 1946737: 31.1%, 0.83 GiB -> 50.4%, 2.02 GiB | daemon 0.2%, 293.6 MiB -> 0.2%, 293.6 MiB; keeper 0.0%, 3.4 MiB both |
| 8 | 01:47:13 -> 02:40:38 | route PID 1946737: 50.5%, 2.02 GiB -> route PID 2355192: 173%, 2.82 GiB | daemon 0.2%, 293.6 MiB -> 0.2%, 271.1 MiB; keeper 0.0%, 3.4 MiB both |

The full pre/post `ps` output, core and memory snapshots, GPU samples, data
directory sizes, per-job process series, and exact timestamps are retained in
the companion JSON.  The N=8 arm also overlapped a daemon-owned WNBA route and
other changing daemon children by its final snapshot.  This is why the result
is properly a shared-machine scheduling number rather than an isolated hardware
benchmark.

## Binding-constraint attribution

The resource pattern rejects the simple capacity explanations at the tested
range:

- Route CPU rose from 11.31 to only 24.12 mean cores while per-job wall time
  rose 21.83x at N=8.  CPU-core capacity was not approached.
- Peak host-used RAM was 109.15 GiB, with roughly 931 GiB available at the N=8
  after-snapshot.  There was no memory-pressure or swap signal.
- Peak GPU allocation was 6506 MiB of 24576 MiB, and sampled utilization never
  exceeded 77% at N=8.  VRAM capacity was not approached.

The remaining observed limitation is a heavily contended shared execution
resource.  All jobs simultaneously decode the same 2.93 GB broadcast and the
route's CPU consumption per job falls as N increases; with CPU/RAM/VRAM headroom
still large, video decode/storage (or a shared pipeline resource near it) is the
leading explanation.  That explanation is intentionally qualified because
NVDEC utilization, decoder queue time, disk throughput, and per-stage traces
were not sampled.

## Non-determinism and not verified

G189/G193/G195 establish that this route is non-deterministic.  Per-job row
counts were expected to differ and were deliberately neither collected nor used
as concurrency evidence.  This row makes a wall-time and resource claim only.

Not verified:

- Exact culprit within the shared path: NVDEC, storage I/O, decoder contention,
  a library lock, or another pipeline stage.
- Idle-pod limit or the next saturation point beyond N=8.  The next useful test
  is N=2 and N=4 on a quiet pod with direct disk and decode-engine counters,
  followed by N=16 only if N=2 remains the operational choice.
- Generalization to another clip, model revision, GPU, or daemon workload.
- Tracking quality, row counts, determinism, or any betting/edge outcome.

## Harness and verification

The measurement-only SSH harness is
`scripts/platformkit/tracking/g200_pod_concurrency.py`; it only wraps the pod
route and writes this evidence record.  It does not modify the pod checkout.

```text
python -m pytest scripts/platformkit/tracking/test_g200_pod_concurrency.py -q
1 passed in 1.63s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q
1 passed in 2.29s
```

The harness is under the 300-LOC rail, so no LOC allowlist change was required.
