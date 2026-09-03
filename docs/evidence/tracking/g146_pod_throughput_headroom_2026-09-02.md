# G146 Pod Throughput Headroom

Date: 2026-09-02 local / 2026-09-03 UTC sampling

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, section A including A7; section B self-check below.

## Result

**The bottleneck in this 22-minute window was daemon availability/concurrency, not GPU: GPU utilization was 0 percent in all six samples, the daemon had no live tracking job in five of six samples and no daemon process at the last sample, while one complete 2,059,054,697-byte MP4 was waiting.**

The conclusion is deliberately scoped to this window. It does not claim a sustained bridge rate or explain why the daemon exited.

## Read-only method

Every sample used the pod's UTC `date`, `nvidia-smi`, the daemon PID file and `/proc`-backed `ps`, plus a count of complete `data/footage_bridge/*.mp4` files. Nothing was started, killed, restarted, reconfigured, copied to the pod, or written on the pod.

`tracking_jobs_live` counts only live direct children whose command is `scripts/run_clip.py` or the adapter runner. A zombie child and `ffprobe -count_frames` are reported separately rather than counted as tracking work. A staged file is waiting only when no live daemon child command references it. The full six-point source table is [`g146_throughput/samples.csv`](g146_throughput/samples.csv).

## Sampled series

The six timestamps are unique and span 1,338 seconds (22 minutes 18 seconds), exceeding the required 20 minutes.

| UTC sample | GPU util | live tracking jobs | direct child state | complete / waiting stage MP4s |
|---|---:|---:|---|---:|
| 03:01:09 | 0% | 0 | none | 0 / 0 |
| 03:02:24 | 0% | 1 | `run_clip` | 1 / 0 |
| 03:06:15 | 0% | 0 | zombie `run_clip` | 1 / 1 |
| 03:10:39 | 0% | 0 | `ffprobe -count_frames` | 1 / 0 |
| 03:15:10 | 0% | 0 | same `ffprobe` (527 s elapsed) | 1 / 0 |
| 03:23:27 | 0% | 0 | no daemon process | 1 / 1 |

GPU memory used ranged from 1 to 442 MiB of 24,576 MiB. The stage did not grow beyond one complete file: it moved from empty to one claimed WNBA file, then ended as one waiting file after the daemon disappeared. This is not evidence of an upload-bandwidth limit, and it does not establish a sustained acquisition rate.

The two middle source-probe points establish that the daemon's only live child was synchronous `ffprobe -count_frames`, not a tracker, for at least 527 seconds. The post-window read at 03:23:59Z found the former keeper parent still present, an empty 0-byte PID file, no daemon command line, and no ledger completion for `wnba_Ydq4CYkCB3U`; it is contextual read-only evidence, not a seventh sample.

## Ledger concurrency

The current ledger contains 120 parseable terminal-job intervals and 120 distinct `(game_id, finished_at, seconds)` tuples (92 distinct game IDs). Reconstructing every interval as `[finished_at - seconds, finished_at)` yields a historical maximum of 10 concurrent jobs at 2026-09-01T15:18:26Z: football 3, KBO 4, MLB 2, and soccer 1. That equals the daemon's configured `--workers 10` cap. The complete derived interval series is [`g146_throughput/ledger_intervals.csv`](g146_throughput/ledger_intervals.csv); its summary and sweep convention are in [`g146_throughput/ledger_concurrency.csv`](g146_throughput/ledger_concurrency.csv).

This demonstrates that the ledger has historically reached the configured cap. It does not imply the present daemon had headroom: the sampled window had 0.17 live tracking jobs per sample (1 job across 6 samples) and ended with no daemon.

## Recommendation (do not apply)

Do **not** increase `--workers` from 10. First have the responsible operator determine why the daemon ceased to exist and why its PID file became empty, restore daemon availability only through the approved operational path, then repeat this same sampled measurement under a sustained non-empty stage. Raising the worker cap cannot use idle GPU while the daemon is absent or blocked in a synchronous source probe, and it could reintroduce the known multi-context contention risk.

## NOT VERIFIED

- Why the daemon disappeared between 03:15:10Z and 03:23:27Z, including whether the keeper or another operator acted.
- Whether the bridge can sustain incoming complete MP4s faster than the daemon under a longer observation window; this window never held more than one complete file.
- GPU utilization during a sustained multi-job tracking interval; no such interval occurred in this series.
- Whether source probing is the daemon exit cause rather than only the immediately preceding blocked activity.

## Verifier self-check

- A1: no code was added, so the specification's conditional per-file test does not apply.
- A2: the headline is reproducible from `samples.csv`: six GPU values are all zero, five samples have zero live tracking jobs, and the final row has one waiting MP4 and `daemon_present=false`. Ledger maximum is independently recomputable from all 120 archived rows in `ledger_intervals.csv` using the stated half-open interval sweep.
- A3: no render or image sample is claimed.
- A4: six unique sample timestamps; 120 distinct ledger interval tuples are stated alongside the 92 distinct game IDs, so retries are not silently collapsed.
- A5: this lane changes only new evidence documents; no runtime field or reader changed.
- A6: this lane commits explicit evidence paths and appends this RESULTS_LEDGER line and register row. Master archive landing remains verifier work; no master-tree mutation or push was performed.
- A7: all repository evidence paths named in this memo exist in this commit: this memo, `g146_throughput/samples.csv`, `g146_throughput/ledger_intervals.csv`, and `g146_throughput/ledger_concurrency.csv`.
- B1: all six valid timed samples are retained. The partial 03:22:47Z probe is named and excluded only because its daemon PID field was absent and `ps` rejected the empty argument; its zero GPU reading is not used to improve the result.
- B2: no schema or field changed.
- B3/B4: no gate, claim, retention, or lifecycle behavior changed.
- B5: no pod deployment, copy, restart, kill, configuration, timeout, threshold, or coordinate-contract change occurred.
- B6: no module moved or retired.
- B7/B8: no renders, fitted model, or independent-fit claim is made.
- B9: sample timestamps and ledger interval tuples are unique; no recycled identifier is used as a denominator.
- B10: no harness bar, threshold, timeout, worker setting, or gate changed.
