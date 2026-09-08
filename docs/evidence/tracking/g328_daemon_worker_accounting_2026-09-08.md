VERDICT: DONE -- premise TRUE (7 of 21 active prints above `--workers 8` on the one instance whose workers value is verifiable; n=327 prints over 7 instances), and the row question gets a measured NULL: adjudication costs 1.076 CPU-seconds per completion (n=21) on a 27.2-core quota, so the over-commit is real but is NOT why 8 workers matched 16.
G328 | daemon worker accounting vs adjudication | 2026-09-08 | worktree a6 | spec VERSION 2026-09-08 | prereg sealed and committed ALONE first: `docs/evidence/tracking/g328_prereg_2026-09-08.md`. Eye check: NONE.
Pod READ-ONLY throughout: `track_daemon` (pid 1168432) and `vol_guard.py` (pid 1039858) were never stopped, signalled, restarted or reconfigured, and nothing was written on the pod. Pod runs PRE-G329 code. Diffed: the deployed `track_daemon.py` differs from master at exactly 3 lines (26, 326, 328), all of them the G329 `mark_degenerate` wiring, and `track_daemon_ledger.py` lacks the whole G329 block. Every accounting line cited below is BYTE-IDENTICAL on the pod and on master.

## PREMISE -- active prints reporting active > workers (n = every print in every pod daemon log)
instance      prints  over  workers       max  median
2026-09-07        34     0  unverified      6     3.0
2026-09-07b       13     0  unverified     11     7.0
2026-09-07c       38     0  unverified     19    17.0
2026-09-07d       18     0  unverified     13     9.0
2026-09-07e      115     0  unverified     20    17.0
2026-09-08a       88     0  unverified     11     9.0
2026-09-08b       21     7  8 (from ps)    10     5.0
TOTAL            327     7
The daemon does not record `--workers` in its log and the pod keeps no shell history for the ssh launches, so only the LIVE instance has a verifiable value. On it the premise is TRUE: 7 prints of 21 report 9 or 10 active at `--workers 8`.

## TRACE (master; byte-identical on the pod)
`track_daemon.py:350-351` tracking exits: `proc.poll()` is not None -> `_begin_adjudication(job)`.
`track_daemon.py:247` `_prepare_adjudication` runs SYNCHRONOUSLY in the poll loop (rows, timebase stamp, ball-telemetry declaration).
`track_daemon.py:250-261` the verdict then runs in a `threading.Thread` INSIDE the daemon process.
`track_daemon_done.py:180-248` that thread does: fsync, `pd.read_csv`, decode manifest, `_with_frame_denominator` `pd.concat` (`:95`), frozen-harness `evaluate`.
`track_daemon_slots.py:31` THE DEFECT: `sum(... if "adjudication" not in job)` -- an adjudicating job is not counted against `--workers`, so its slot is handed to the next clip.
`track_daemon.py:388` the print reports `len(active)`, which DOES include adjudicating jobs, so the cap and the printed number disagree by exactly the adjudication count.
`track_daemon.py:338-349` adjudication ends (or times out at 1800 s) and the job is reaped; `track_daemon.py:323` then writes the ledger row via `_record_loudly(mark_degenerate(...))`.

## TIMING (every cell with its n and its method)
method A (ledger rows, exhaustive over 2026-09-08): per-clip adjudication wall is NOT directly recoverable -- rows carry `evaluated_at` (adjudication END) but no adjudication START field. method B (log timestamps): NOT AVAILABLE -- the daemon log lines carry no timestamp at all.
method C (`/proc` transient-thread sample, 61 samples at 10 s, span 601 s): ZERO adjudication threads were alive at any sampling instant, so no wall was timed directly (`adjudication_threads.csv` is header-only); thread count held at 255 across all 61 samples; tracking children max 3, median 0.
DERIVED wall (method A, n=190 rows carrying `evaluated_at`): a finished verdict is reaped at the first tick after it ends, so wall ~= interval - reap latency at `--interval 20`.
  reap latency s               n=190  min 1   p10 11  median 20.0   p90 21   max 27
  implied adjudication wall s  n=190  min 0   p10 0   median 0.0    p90 9    max 19
  job wall s                   n=209  min 92  median 1874.0         p90 3357 max 5423 ; csv rows n=209 median 3811.0 max 6739 ; decoded frames n=190 median 3961.0
CPU (method C, `/proc/1168432/stat`, exhaustive over the live instance): 28.05 CPU-s over 3762.8 s uptime; idle baseline 0.1448 ticks/s from the 601 s window that held zero adjudications -> poll loop 5.45 CPU-s, leaving 22.60 CPU-s over n=21 completions = 1.076 CPU-seconds per completion. Mean daemon occupancy 0.00745 cores of the 27.2-core quota.
CONCURRENCY: max concurrent adjudications observed = 0 over n=61 samples; 190 of 209 rows were reaped within one poll interval of their own verdict, so adjudications rarely overlap.

## CAP (additive, opt-in, default OFF)
Shipped `--adjudication-holds-slot` (store_true, default False): the spec's SECOND option, counting adjudicating jobs against `--workers`.
The semaphore option was NOT shipped -- it bounds adjudication concurrency but leaves `len(active)` above `--workers`, and a job blocked waiting for a slot would hold its active entry LONGER, worsening the reported over-count instead of removing it.
New module `scripts/platformkit/track_daemon_slots.py` (31 lines) holds `slots_in_use`; `track_daemon.py` gained 2 wiring lines and its import block was reflowed (same 5 names, same module), so the allow-listed file went 440 -> 438 lines and did NOT grow. The default path returns the identical expression as before, and no flag, default, ledger field, status or printed line changed name or meaning (B2). The per-file test pins both modes and the unchanged ledger row.

## ESTIMATE FROM MEASURED PER-CLIP CPU (an ESTIMATE, never a result)
T = 1874.0 s median job wall, D = 0.0 s median implied adjudication wall, W = 8, quota 27.2 cores.
3600*W/T = 15.37 clips/hour; 3600*W/(T+D) = 15.37 clips/hour. At the measured D the cap moves the estimate by less than the resolution of the derivation, and the adjudication CPU it would bound is 0.006 cores of 27.2. The real before/after needs a deployment this row does NOT perform.

## NOT VERIFIED
- `--workers` for 6 of the 7 instances (not in the log, no shell history). The spec's "'17 active' / '18 active' at `--workers 16`" for 2026-09-07 is consistent with the observed distribution (median 17, max 20) but could not be confirmed from any artifact readable on the pod.
- Per-clip adjudication wall is DERIVED from reap latency, not directly timed (method C timed none); and the 1.076 CPU-s figure is per COMPLETION -- it includes `_prepare_adjudication`, `tracking_rows`, `_fresh_solve_summary` and the whole-ledger read in `_previous_sport_entry`, not adjudication alone.
- The idle baseline is one 601 s window on a cgroup shared with other lanes, CPU attributed to the daemon only where `/proc` says so; and the cap is UNDEPLOYED and unmeasured in production, with no clips-per-hour result claimed.
- DEVIATION from the prereg: its section 3 named the semaphore variant and the flag `--adjudication-slots`. The shipped cap is the spec's other option, for the reason given above; the prereg is left exactly as sealed.

Wall time: about 75 minutes, of which 601 s was the read-only pod sample. SHA-256 (LF-normalised) -- prereg whole file 61757a5e95d6c0ecde7993a8eff3c4e770f276f00f8e5ba8b7feb0fc57418186 (its embedded SEAL covers the body only: cd96127d5ba8da858ff9c2ab0214e51cc85e40270a589434210e39ab48ee90e5)
timing.csv e62530d6c2fe0c9d391b287c50a0d9dd8f490eac56597c32f25c0ac548ab208b ; tick_table.csv cb7196b2e58c22ae6b157ee9a128f42801d6cc78d99d04cd4b55beca2c85c434 ; adjudication_threads.csv f27ae6f939764d7806a1d5f422514a6612d1e5526dd2c5947d896a3ee06d4a33
track_daemon_slots.py af6437ddff84d9ff015f7f5478d931593fac1d483b24e284ee06a1b9dee58a7c ; track_daemon.py c17ae81dd9de120845a16aa0b0b2240456a2a09e5bf4b7c3d2ac07cec3a2d4fe ; test_g328_daemon_worker_accounting.py e3ac3130542e0c1b4ded58155e953c92b094549af34e6a4a8030fc8f388ebc2c

## Corrections applied at landing 2026-09-08 (verifier codex-sol)
TRACE refs above were stale against the landed file and now read 350-351/247/250-261/track_daemon_slots.py:31/388/323 (was 353-354/250/262-264/363/391/326); each was re-verified against the landed master file at landing and the verifier's numbers held exactly. The lander additionally moved 341-352 -> 338-349, the same -3 import-reflow shift, which the verifier's list did not name. The RESULTS_LEDGER row's 363/391 refs became track_daemon_slots.py:31/388.
DIGEST: the test-file sha256 above was refreshed to the landed file after fix 1b fef013ff9 (was 06903fbb743e0298bf5e4a728b50d33224798737f09d2e34446ddc4664762729); the other five digests reproduce unchanged.
NEW GAP: pre-existing importer failure -- the stale test double at test_g149_persist_decoded_denominator.py:32 lacks the `publish` keyword used by track_daemon.py:275; both lines predate G328.
NEW GAP: digest freshness is not pinned -- fef013ff9 changed the spec test without updating the digest recorded in this memo, and nothing fails when they diverge.
Vocabulary follows contract Q6; automated scan required.
