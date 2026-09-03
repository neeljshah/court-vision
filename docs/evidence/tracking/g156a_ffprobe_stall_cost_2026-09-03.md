# G156a: what the synchronous ffprobe in the daemon poll loop actually costs

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), sections A (including A2
and A7) and B. **This is the MEASUREMENT half of G156 only.** The fix is not
landed and is not claimed. Nothing here changes a threshold, a gate, the
decoded-frame denominator, the coverage definition, or any verdict.

## Why this memo exists and who wrote it

G156 was dispatched to a codex lane. The codex backend began returning
`404 Not Found` from `chatgpt.com/backend-api/codex/responses` partway through
and killed the lane after roughly 126,000 tokens. The lane had a coherent
partial fix in its worktree, uncommitted. Rather than lose it or land it
unverified, the diff was preserved as a patch outside the repository and the
worktree was cleaned. **The orchestrator then took the measurement half
directly**, because A2 requires the orchestrator to recompute a headline metric
independently in any case, and because the fix cannot be judged without knowing
what it is worth.

## The defect, restated from the live observation

The daemon's poll loop calls, synchronously, in its own process:

    tick()  ->  _finish()  ->  verdict()          track_daemon.py:115
            ->  adjudicate()                      track_daemon_done.py:117-133
            ->  decoded_frame_count()             decode_manifest.py:88-107
            ->  ffprobe -count_frames ...

`-count_frames` fully decodes the video to count frames exactly. While it runs,
`tick` cannot reap another job and cannot claim a new one.

Two direct observations on the live pod, both by `ps -eo pid,etimes,args` and
`/proc/<pid>/wchan` rather than by `pgrep -f`, which matches the ssh command line
running the check itself:

- `/proc/33064/wchan` read `do_poll.constprop.0` while the daemon's only child
  was `ffprobe -v error -count_frames -select_streams v:0 ...` on a staged mp4.
- Later, **zero** tracking jobs live with **two** `ffprobe -count_frames`
  processes at 129 s and 85 s elapsed. The box was doing no tracking at all.

## Measured cost

`decoded_frame_count` was timed directly on four real local videos. Eligible
denominator: the four reference clips over 20 MB, timed once each, wall clock.

| Video | Size (GB) | Seconds | Sec per GB | Decoded frames | Frames per second decoded |
|---|---:|---:|---:|---:|---:|
| `kbo.mp4` | 0.0326 | 4.87 | 149.5 | 28,800 | 5,914 |
| `football.mp4` | 0.0808 | 12.59 | 155.9 | 28,771 | 2,285 |
| `handball.mp4` | 0.7663 | 173.91 | 227.0 | 79,500 | 457 |
| `baseball.mp4` | 0.4006 | 96.75 | 241.5 | 49,079 | 507 |

**149.5 to 241.5 seconds per gigabyte.** Sec-per-GB is the weaker unit here
because it varies with codec and resolution; the frames-per-second column shows
the same spread from a different angle. The two larger, more broadcast-like clips
sit at 227 and 241 sec/GB and around 460-510 frames decoded per second.

## What that means at production scale

The footage bridge delivers full broadcasts of roughly 2.0-3.7 GB. At the
measured 227-241 sec/GB for broadcast-like content, one such game costs the
daemon roughly **450 to 900 seconds of complete poll-loop stall** per completed
job.

Set that against the jobs the daemon actually completed today. All four ledger
rows on the new pod:

| Game | Rows | Decoded frames | Job seconds | coverage_pct |
|---|---:|---:|---:|---:|
| `mlb_2026-08-30_10893dca` | 32,380 | 39,035 | 296 | 0.1565 |
| `kbo_01` | 63,497 | 69,170 | 791 | 0.1573 |
| `mlb_2026-08-30_0f36e8cc` | 54,537 | 49,079 | 368 | 0.1607 |
| `mlb_2026-08-30_7e8080e5` | 48,816 | 41,029 | 301 | 0.1567 |

Tracking a game takes 296-791 seconds. The stall that follows each completion is
of the **same order as the job's own runtime**, and unlike the job it is global:
the ten worker slots are configured but nothing can be claimed into them while it
runs. The observed `ffprobe` on the first mlb game had already reached 237
seconds against that job's 296-second runtime when it was sampled, and it was not
sampled to completion, so 237 s is a LOWER BOUND on that instance.

That is the mechanism behind the standing observation of one live job at a time
and GPU utilisation at 0 pct on a 256-core box.

## What is NOT claimed

- **No fix is landed.** The preserved patch runs `verdict()` on a daemon thread
  and excludes adjudicating jobs from the worker budget so new jobs can be
  claimed. It is unreviewed, unmeasured before/after, and NOT in the repository.
  One gap is already visible in it: an adjudication thread that hangs has no
  timeout, so its job would never finish. That must be resolved before it lands.
- **The exact count is not the problem and must not be changed.** It is the
  denominator G147 needs and the field G149 wanted persisted. Replacing
  `-count_frames` with `nb_frames`, with duration times fps, or with any sample
  would be a moved bar (B10, Q3).
- **Sec-per-GB is not a stable constant.** It varies by codec, resolution and
  container across a 149.5-241.5 range on four clips. Treat it as an order of
  magnitude, not a coefficient.
- The per-game stall figures for 2.0-3.7 GB broadcasts are an EXTRAPOLATION from
  four smaller local clips, labelled as such. No broadcast-sized file was timed
  end to end.

## Bonus result: `decoded_frames` reaches the ledger on every real row

G153 answered G149's producer question with one local reproduction, and the
orchestrator confirmed it with one pod row. It is now **4 of 4**: every daemon
ledger row written on the new pod carries both `decoded_frames` and
`coverage_pct`. The eligible denominator is 4 completed jobs, all baseball-family
and none tennis, so this says the producer works and says nothing yet about
tennis coverage.

## NOT VERIFIED

- Any before/after demonstration that the daemon claims a new job during an
  in-flight adjudication. The fix is not landed.
- The A5 reader survey over the ledger row, the verdict sidecar and the decode
  manifest, which G156's spec requires before any concurrency change lands.
- Timing of `decoded_frame_count` on a full 2-3.7 GB broadcast.
- Whether ordering of ledger appends and verdict sidecars is preserved under the
  preserved patch when two jobs finish together.
- Any claim about supply versus pod capacity; that is G159b's row and it is
  currently blocked by the same codex outage.
