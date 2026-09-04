# G216 Local Staging Concurrency - 2026-09-03

## Verdict

Local staging **did not remove G200's end-to-end concurrency collapse**. It made
the direct file read path much faster, but N=4 and N=8 route throughput still
collapsed while CPU, RAM, and VRAM remained far from host capacity. Network
filesystem bandwidth is therefore eliminated as the primary explanation for
this route's collapse; a shared route stage after (or independent of) raw file
read remains the leading unverified explanation.

## Controls and staged-copy integrity

The G200 arm generator and reducer were reused unchanged; only `g200.VIDEO`
was bound to `/root/g216_stage_1788490550/wnba__wnba_01.mp4`. Every job retained
`--frames 1200 --no-show --skip-features` and a unique `/tmp/g200_*_data`
directory. No source, route setting, daemon, keeper, or corpus file changed.

| Item | Result |
|---|---:|
| `/` free before stage | 50,045,440,000 B (46.61 GiB) |
| Safety margin | 5 GiB in addition to source size |
| Source / staged size | 2,931,985,407 B / 2,931,985,407 B |
| Source / staged MD5 | `c33dce4fafd1be85fec41f7b2d896297` / same |
| Copy wall time | 10.16 s |
| `/` free after copy | 47,113,453,568 B (43.88 GiB) |
| Cleanup | exact staged file removed; 2,931,985,407 B reported freed; file absent |

`findmnt` during the run recorded `/workspace` as `mfs#eu-cz-1.runpod.net:9421[...]` (`fuse`) and `/` as `overlay`.

## Direct sequential reads

Each condition used `dd if=<file> of=/dev/null bs=16M iflag=direct status=none`.
The raw record contains pre/post shared-pod snapshots for every condition.

| Storage | Readers | Aggregate wall (s) | Aggregate MiB/s |
|---|---:|---:|---:|
| `/workspace` network mount | 1 | 3.561 | 785.3 |
| local overlay stage | 1 | 0.727 | 3,844.5 |
| `/workspace` network mount | 4 | 7.162 | 1,561.6 |
| local overlay stage | 4 | 0.727 | 15,389.0 |

Thus the local file was 4.9x faster for the single reader and 9.9x faster in
aggregate for four readers. This verifies a substantial read-path difference,
not that it is the route's limiting stage.

## End-to-end comparison

Mean slowdown is relative to each row's N=1 baseline. CPU is mean aggregate
route process-tree CPU; RAM and GPU are global pod peaks and include shared
workload.

| N | Network jobs/min (G200) | Local jobs/min | Network slowdown | Local slowdown | Local mean CPU | Local peak RAM | Local peak GPU memory |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.427 | 0.463 | 1.00x | 1.00x | 1,129.50% | 76.32 GiB | 1,384 MiB |
| 2 | 0.567 | 0.597 | 1.52x | 1.54x | 1,832.84% | 87.29 GiB | 2,162 MiB |
| 4 | 0.294 | 0.278 | 5.86x | 6.62x | 2,415.39% | 89.11 GiB | 4,232 MiB |
| 8 | 0.150 | 0.158 | 21.83x | 22.75x | 2,513.91% | 100.77 GiB | 8,004 MiB |

The full pre/post load context for every arm (UTC timestamp, 256-core count,
`free`, `df`, GPU state, top 40 processes, daemon/keeper/G203 matches, and
route source hashes) is retained under each arm's `load_context_before` and
`load_context_after` in the companion [raw record](g216_local_staging_concurrency_2026-09-03_records.json).
The POD was shared throughout: daemon, keeper, supervisor, other route work,
and peer activity were visible in those snapshots. These are not clean-machine
capacity measurements.

## Copy-cost analysis

This experiment made one copy and reused it within each concurrent arm. Versus
G200 arm wall time, that one-copy setup saved 10.73 s at N=1 and 10.63 s at N=2,
only barely above its 10.16 s copy time; it lost 45.70 s at N=4 and saved 171.40
s at N=8. The N=8 saving does not make staging an operational fix: slowdown was
worse (22.75x vs 21.83x), and throughput stayed below N=1.

If staging must occur independently before every job as stated in the operating
model, the unmeasured lower-bound copy cost is N x 10.16 s (10.16, 20.33,
40.65, and 81.30 s at N=1,2,4,8). It consumes the small N=1/N=2 timing gains,
and cannot rescue N=4. Concurrent-copy contention is NOT VERIFIED.

## Not verified

- The exact shared stage: decoder/NVDEC, a library lock, another shared route
  component, or interaction with pod work.
- Whether `iflag=direct` bypassed every relevant cache layer through overlay and
  FUSE; the command exited zero and measures the observed path, not kernel internals.
- Generalization to another clip, pod, model revision, or an idle machine.
- Any tracking-quality, betting, edge, or capacity claim beyond this timing row.

## Verification

```text
python -m pytest scripts/platformkit/tracking/test_g216_local_staging_concurrency.py -q
2 passed

python -m pytest scripts/platformkit/tracking/test_g200_pod_concurrency.py -q
1 passed
```
