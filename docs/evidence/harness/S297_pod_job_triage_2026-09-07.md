# S297 pod job triage (2026-09-07)

VERDICT: LEAVE RUNNING. Pod pid 407364 is progressing and is projected to finish
roughly 40 to 50 minutes after this triage, inside the 3-hour budget. No takeover,
no kill, no re-plan of the grain. The codex lane for a19 was left untouched.

## What was observed (no interference with the job)

- Job: `python scripts/platformkit/s297_minutes_dnp_distribution.py`, pid 407364,
  cwd `/workspace/wt/a19/jobs/S297_20260907_r2`, parent bash pid 407363.
- Elapsed at triage: 2 h 49 m. State `R (running)`, `wchan 0`, 134 threads,
  VmRSS 855,816 kB. Not blocked, not swapping (`pswpin 0`, `pswpout 0`;
  pod has 1007 GB total, 869 GB available).
- `py-spy` could not be used: the pod container lacks `SYS_PTRACE`
  ("Permission Denied ... started your container with the SYS_PTRACE capability").
  Diagnosis therefore used `/proc/407364/{stat,io,status,wchan,fd}` sampling
  plus cost measurement of the real inner loop on the pod itself.
- `/proc/407364/io` is `rchar 36,029,730`, `syscr 2928`, `wchar 98`, `syscw 3`,
  `read_bytes 0`, `write_bytes 0`. The 98 written bytes are the two flushed
  startup prints (`RSS_MB before`, `S297_PREMISE`), so the process is past
  `_load()` and inside the CPCV scoring loop.
- `pod_run.log` reads as 0 bytes and `cat` returns nothing even though the
  process recorded 98 bytes written to it (fd 1 and fd 2 both point at that
  file). This is an overlay-filesystem metadata artifact on the job directory,
  NOT evidence that the job produced no output. The log is unusable as a
  progress meter; CPU accounting was used instead.

## Progress is real, not a hang

Two `/proc/407364/stat` samples:

| Window | utime delta | CPU seconds | Share of one core |
|---|---:|---:|---|
| 60 s  | 604 ticks  | 6.04 s  | 10.1 pct |
| 240 s | 2,274 ticks | 22.74 s | 9.5 pct |

Lifetime average is 13.2 pct of one core. `nonvoluntary_ctxt_switches` 196,669
against `voluntary_ctxt_switches` 845: the process is being preempted, not
waiting on I/O. The pod is carrying eleven `run_clip.py` tracking jobs at about
one core each plus `s287_sim_full_pod` at about eleven cores, loadavg 95 on 256
cores, so a single-threaded Python job is handed roughly a tenth of a core.
Total consumed at triage: utime 131,253 ticks = 1,312.5 CPU seconds.

## Where the time goes, and how much is left

The shared evaluator is NOT the problem here. `cpcv_evaluate_vector_distributional`
calls `fit_predict(train, views)` once per fold with the whole test list, so it
carries no per-state train construction. The cost is entirely in the lane's own
`_forecast`, which for every test row rebuilds the full as-of history:

    history  = train[:cutoff]                       # O(cutoff) slice
    positive = [(s["outcome_vector"][0], s["stable_key"]) for s in history ...]
    p_league = sum(s["outcome_vector"][1] for s in history) / len(history)

Three passes over `cutoff` elements per test row. Replaying the real split
geometry (5 groups, 1 test group, 1-day embargo) over the real corpus of
78,767 player-games / 3,645 games gives the exact per-pass work:

| Fold | Train | Test | Sum of cutoffs |
|---|---:|---:|---:|
| 0 | 61,813 | 16,705 | 0.000e+00 |
| 1 | 60,965 | 17,522 | 2.884e+08 |
| 2 | 62,156 | 16,088 | 5.463e+08 |
| 3 | 61,568 | 16,624 | 8.315e+08 |
| 4 | 66,687 | 11,828 | 7.888e+08 |
| TOTAL | | 78,767 | 2.4551e+09 |

Measured on the pod, separating CPU time from scheduler starvation
(`process_time` against `perf_counter`), the per-history-element CPU cost is
slice 5.5 ns, positive-comprehension 413.2 ns, sum-generator 107.2 ns, so
525.9 ns per element. The measured CPU share in that same benchmark was 0.055
to 0.137 of a core, independently reproducing the job's observed 13.2 pct.

Budget:

- history passes: 2.4551e9 x 525.9 ns = 1,291 CPU seconds
- per-row constants (100 draws, two CRPS, quantiles, sorts), measured at
  1.586 ms per row x 78,767 rows = 125 CPU seconds
- load, state build, deepcopy, per-fold blocked-index construction: about 60 CPU seconds
- TOTAL to end of scoring: about 1,476 CPU seconds

Consumed 1,312.5, so about 164 CPU seconds of scoring remain, which at the
observed 9.5 pct share is about 29 minutes. `_write` then costs an estimated
60 to 100 CPU seconds (two 78,767-row CSVs plus per-row quantiles), about 11 to
18 minutes at the same share. Projected remaining wall time: about 40 to 50
minutes, i.e. a total of roughly 3 h 30 m against a 3 h decision budget measured
from the triage moment.

## Decision

LEAVE RUNNING. The job is demonstrably advancing (utime climbing steadily,
never blocked), memory is bounded and flat at 855 MB, and the remaining work is
under an hour. Killing it here would discard about 1,313 CPU seconds of
completed scoring to save nothing. The a19 codex lane (local pid 14724) is alive
and polling the same pid on a 25-second cadence and will fetch outputs and seal
the result memo itself; it was deliberately not disturbed.

## NOT VERIFIED

- No result, verdict, or calibration number is claimed here. This memo is a
  scheduling triage only; the S297 acceptance rule is adjudicated by the lane's
  own result memo against its sealed preregistration.
- The remaining-time projection is a model built from measured per-element CPU
  cost and exact split geometry, not from a progress counter emitted by the job.
  The harness prints nothing between `S297_PREMISE` and `RSS_MB after`, and the
  overlay filesystem hid even those bytes, so no direct progress read exists.
- `py-spy` was never able to attach, so the interpreter stack was not sampled;
  the location of execution is inferred from the io counters and the cost model.

## Standing defect worth fixing later (not fixed now)

`_forecast` is quadratic in corpus size by construction. Hoisting the as-of
history into a single forward scan (running DNP count, and an append-only
positive list reused across test rows in timestamp order) would make it linear
and cut the run from about 25 CPU minutes to well under one. That change alters
no sampled distribution and would need its own sealed supplement, so it was not
attempted mid-flight.

## Outcome (appended after the job finished; projection corrected)

The leave-running decision was correct: the job completed on its own with no
takeover, no kill and no re-plan of the grain.

    S297_COMPLETE rows=78767 games=3645 verdict=ACCEPT rss_mb=866.76 wall_seconds=14065.81
    POD_RUN_DONE

Total wall time 14,065.81 s = 3 h 54 m 26 s. Peak RSS 866.76 MB, far under the
8 GB ceiling. Triage was taken at 2 h 49 m elapsed, so the job ran 65 more
minutes after the decision, against a 3-hour decision budget.

HONEST CORRECTION: the projection above said "about 40 to 50 minutes". The true
remaining time was about 65 minutes, so the point estimate was low by roughly
30 percent. The structural finding was right (2.4551e9 history-element visits,
three passes, quadratic `_forecast`) and the exact split geometry was right; the
per-element CPU constant was the low term. The microbenchmark used 2-key dicts,
while the real states carry nine keys including two nested dicts, so real
iteration touches more memory per element and costs roughly 25 percent more than
the measured 525.9 ns. Scoring ended near 1,790 CPU seconds rather than the
projected 1,476.

Progress series used to hold the decision accountable (elapsed, utime ticks, RSS kB):

    2:38:51  125,940  804,640      3:19:18  153,545  874,660
    2:49:15  131,253  855,756      3:28:16  161,051  881,768
    3:01:43  140,172  862,740      3:37:16  167,723  888,552
    3:10:33  146,632  868,724      3:46:54  174,657  894,080
    3:54:11  179,712  993,468  <- write phase, wchar 98 -> 10,175,811

The write phase was detected exactly as predicted, by `wchar` in
`/proc/407364/io` jumping off 98 bytes when the first CSV landed.

## Interpretation caveat for the verifier (declared, not a violation)

Fold 0 contributes 16,705 of the 78,767 scored rows (21.2 percent) with a
measured sum of cutoffs of exactly 0.000e+00. CPCV builds contiguous date
blocks, so for fold 0 every training row is dated later than every test row and
the strictly-earlier as-of filter leaves an empty history. Both arms then fall
to the same zero point mass, so all 21.2 percent of those rows contribute a
delta of exactly zero to every metric. This is preregistered ("Empty strictly
earlier histories use the same zero point mass in both arms and are retained,
not dropped"), so it is a declared design choice, not a defect. It does mean the
pooled improvement is diluted by those structurally null rows and understates
the separation on rows that actually had history.

Two secondary metrics moved the wrong way and should not be read as supporting
the primary result: nominal q10-q90 coverage improvement is negative, and DNP
log loss improvement is negative with a CI that straddles zero. The sealed
acceptance bar is minutes CRPS only.

The focused test `tests/platformkit/test_s297_minutes_dnp_distribution.py`
passes locally (1 passed in 1.42 s); it revalidates the preregistration seal and
holds a future-row plant of 99.0 minutes that must never supply a draw.

## NOT VERIFIED (outcome section)

- No second corpus, no walk-forward beyond this single window, no promotion.
- No claim of any market or monetary benefit is made or implied; the ACCEPT is a
  calibration verdict against the sealed CRPS bar only.
- The artifact fetch, result memo, commits and ledger row are owned by the a19
  codex lane, which was left running throughout and picked up POD_RUN_DONE.
