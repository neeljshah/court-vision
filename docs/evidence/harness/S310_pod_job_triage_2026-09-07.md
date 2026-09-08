# S310 pod job triage, 2026-09-07

Scope: diagnose the stalled S310 pod job, decide run-or-takeover, and record the S308
pod job's state for its owning lane. Measurement only; no calibration claim is made here.

## Verdict

TAKE OVER for S310. Projected remaining wall time 3.8 h at the measured CPU share,
against a 3 h budget, with zero progress observability. Diagnosis only for S308.

## S310 -- pid 98537, /workspace/wt/a16

Command: `python -m scripts.platformkit.s310_tail_beta_offset --output
docs/evidence/harness/S310_tail_beta_offset_2026-09-07`.
Log `/workspace/wt/a16/pod_run_s310_20260907_corrected.log`.

Measured at 2026-09-08 02:29Z through 02:33Z, and again immediately before stop:

| quantity | value |
|---|---|
| elapsed at stop | 04:46:12 |
| CPU consumed at stop | 00:38:02 (utime 227044 ticks, stime 851) |
| lifetime CPU share | 13.2 pct of one core |
| instantaneous CPU share (90 s window) | 1126 ticks / 90 s = 12.5 pct of one core |
| threads | 143 |
| main-thread share of CPU | 227044 of 227895 ticks |
| sibling threads | 142, each 3-8 ticks lifetime, all in `futex_wait_queue` |
| RSS | 1490208 kB (1.49 GB) |
| rchar over 90 s | 37474658, unchanged |
| read_bytes | 0 |
| swap | none configured |
| wchan | 0 (state R) |
| log lines | 2, both the one-shot `_states` line-122 UserWarning emitted at startup |
| output artifacts | none; the output directory was never created |

The job was neither hung nor I/O bound. It was running, single-threaded, at one eighth
of one core. The 142 sibling threads are idle BLAS/OpenMP pools, not workers.

### Root cause 1: container CPU starvation

The pod cgroup quota is `cpu.max = 2720000 100000`, i.e. 27.2 cores for the whole
container, against `nproc` 256. Concurrent demand at sampling time:

- `s287_sim_full_pod` at 1159 pct (11.6 cores, 259 threads)
- ten `scripts/run_clip.py` tracking jobs at 100-229 pct each (~13 cores, ~427 threads each)
- `g302_amateur_resolution_attribution` at 146 pct

Load average 40.39 / 59.11 / 70.37. A single-threaded process competing with 400-thread
jobs inside a saturated quota receives roughly 0.125 core, which is exactly what both
harness jobs were measured at.

### Root cause 2: superlinear cost in the shared evaluator

The shared route `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` calls
`_blocked_indices` once per split. For every test row it executes
`blocked.update(by_day[date + offset])` for offsets -1, 0, +1. The corpus has only 302
distinct game dates and a median 1405 ticks per date, so each test row costs about
3 x 1405 set insertions. The term is O(test_rows x ticks_per_date), i.e. quadratic in
corpus size at fixed date count.

Phase-instrumented local runs on game subsamples of the same corpus (single core):

| rows | total wall | `_blocked_indices` (4 calls) | remainder | `_states` |
|---:|---:|---:|---:|---:|
| 46523 | 140.0 s | 27.63 s | 109.66 s | 2.09 s |
| 94240 | 373.7 s | 102.87 s | 265.63 s | 4.13 s |

Fitted exponents: `_blocked_indices` log(102.87/27.63)/log(2.026) = 1.86; remainder
log(265.63/109.66)/log(2.026) = 1.25. Extrapolated to the full 465249 rows
(factor 4.937): `_blocked_indices` 2006 s, remainder 1955 s, `_states` 20 s, total
about 3981 s of single-core CPU. A pure-N-squared purge term would give 2510 s instead
of 2006 s, so the total spans roughly 3981-4485 s.

`_records` is called twice, once for the candidate arm and once for the baseline arm.
Both passes recompute the same states, the same deep copy, the same splits, the same
purge and the same baseline fits; only the final `_apply_candidate` differs. Half of
the measured cost is therefore duplicated work.

### Projection and decision

Consumed 2279 s of CPU; central estimate of the total is 3981 s, leaving 1702 s. At the
measured 0.125-core share that is 13616 s, or 3.8 h remaining, after 4.8 h already spent.
To finish within the 3 h budget the job would need 1350 s or less of CPU remaining, i.e.
a total of 3629 s or less; the central estimate and the pessimistic purge case both
breach that, and the optimistic case is marginal. The harness emits no progress counter
and writes no partial artifact, so the run could not be bounded from the outside either.

Decision: take over, re-plan the grain, and re-run.

### Takeover actions

- Local codex lane for a16, `codex.exe` pid 25320 (started 2026-09-07 16:50:03,
  `exec --json --skip-git-repo-check --sandbox workspace-write`), stopped first.
- Pod pid 98537 stopped with SIGTERM; it exited within the 30 s grace window, so SIGKILL
  was not needed. Last observed state recorded in the table above.
- S308 pid 105232 was left running and untouched.

## S308 -- pid 105232, /workspace/wt/a18 (diagnosis only, NOT touched)

Command: `python -m scripts.platformkit.eval_gate.s308_band_functional_validity`.
Log `/workspace/wt/a18/s308_pod.log`.

| quantity | value |
|---|---|
| elapsed at last sample | 04:40:55 |
| CPU consumed | 00:36:52 (utime 199257 ticks, stime 736) |
| instantaneous CPU share (90 s window) | 1122 ticks / 90 s = 12.5 pct of one core |
| threads | 22; 21 siblings at 2-8 ticks, all in `futex_wait_queue` |
| RSS | 1871916 kB (1.87 GB) |
| rchar over 90 s | 43389537, unchanged; read_bytes 0 |
| log lines | 0 |
| output artifacts since 22:11Z | none |

Same picture as S310: running, single-threaded, not I/O bound, starved to one eighth of
a core by the same tracking fleet, and emitting no progress signal.

S308 uses the same shared `cpcv_evaluate` route and therefore carries the same
O(states x ticks_per_date) purge term, with a 9x larger structural multiplier. With
`N_BLOCKS = 6`, `nested()` calls `_predict` once for the outer fit (6 splits) and once
per held block for the inner OOF fit (6 x 5 = 30 splits), for 36 `cpcv_evaluate` splits
and therefore 36 full `_blocked_indices` passes over its state list. S310 ran 4.

Projection: bounded below by 36/4 = 9x S310's purge budget for an equal state count.
S308's own state count was not sized here because another lane owns that row. The
actionable findings for that owner are that the job is neither hung nor I/O bound, that
its ceiling is the 0.125-core container share rather than its own algorithm, and that its
36 purge passes are the dominant term.

## NOT VERIFIED

- `py-spy` could not attach: the container lacks `SYS_PTRACE`, so no Python-level stack
  sample was taken. All attribution above comes from `/proc` thread accounting and from
  phase-instrumented local reruns of the same code, not from sampling the live process.
- The full-scale extrapolations are two-point exponent fits on subsamples; they are
  estimates, not measurements of the full corpus.
- Pod and local per-core speeds are assumed comparable; this was not measured.
- S308's state count, total work and finish time were not measured.

---

# Correction, appended after the root cause was found

The diagnosis above is correct about the observed facts and about root cause 1
(container CPU starvation). Root cause 2 is **wrong as stated** and is corrected here.
The correction is appended rather than edited in, so the original reasoning stays visible.

## What was actually wrong

`ts` in `nba_checkpoints_full.parquet` is an int64 column of **epoch seconds**.
`_states` built its evaluator timestamp with `pd.Timestamp(row.ts)`, and `pd.Timestamp`
reads a bare integer as **nanoseconds**. Every state therefore carried a `state_ts` of
1970-01-01, within about 50 ms of every other state in the corpus:

    ts int64 range 1729640162 .. 1781407085  (2024-10-22 .. 2026-06-13 as seconds)
    state_ts range 1970-01-01 00:00:01.729640162 .. 1970-01-01 00:00:01.781407085

Consequences, measured directly against the shared evaluator:

- The whole corpus collapsed onto one calendar day, so `_blocked_indices` blocked
  **every** index on every path: `n_states=117964 n_test=48349 n_blocked=117964`.
- `train_states` was therefore always empty. Both fold audits recorded
  `n_train_ticks: 0` and `beta: [0.0, 0.0, 0.0]`.
- With no train rows, `_predict_baseline(None, raw)` returns the raw market
  probability and `_apply_candidate` takes its zero-beta identity path, so the
  candidate was byte-identical to the baseline everywhere.
- Every reported improvement was exactly `+0.000000000` with a
  `[+0.000000000, +0.000000000]` interval, in all four populations. The screen
  measured nothing. It was a tautological null, not a result.

## What this means for root cause 2

The `_blocked_indices` cost measured above, and the exponent of 1.86 fitted from the
subsample runs, are real timings of the **defective** code. With every state on a single
calendar day, `by_day` held one key listing the entire corpus, so each test row inserted
the whole corpus into the blocked set: that is the quadratic term, and it was caused by
the timestamp bug, not by any inherent property of the shared evaluator. With correct
per-game dates spread over 302 days, `by_day` holds roughly 1540 entries per date instead
of 465249, which is about two orders of magnitude less work.

The shared evaluator is therefore **not** at fault and needed no change. The 3981 s
full-corpus projection above is an artifact of the same bug and should not be quoted.

## What the pod job would have produced

The killed job was on course to spend eight or more hours and return all-zero
improvements with zero-width intervals. Stopping it was correct, but for a different
reason than the one given above: not that it was too slow to finish, but that what it
was computing was vacuous.

## Correction to the takeover record

The timestamp fix is a defect fix, not a preregistration amendment: the preregistration
declared a "symmetric one-day nonzero embargo", and the embargo was silently blocking the
entire corpus instead. Restoring it makes the harness do what was preregistered.

## NOT VERIFIED in this correction

- The corrected full-corpus cost is measured separately and reported in the result memo;
  the numbers in the original section above are superseded and must not be reused.
- The S308 projection above is withdrawn: it was extrapolated from the S310 purge rate,
  which was measured under this bug, so its 9x multiplier has no valid base. The rest of
  the S308 record (starved to 0.125 core, single-threaded, not I/O bound, no output in
  4 h 41 m) stands as measured.
- S308 does **not** carry the timestamp defect. It builds states through `s294._states`,
  which is `s276_incumbent_conformal_band_full_attempt2._states`, and its rows come from
  `s265._rows`, which converts explicitly with
  `pd.to_datetime(raw["ts"], unit="s", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")` and so
  hands `_states` an ISO string. That sibling harness independently confirms that this
  corpus's `ts` is epoch seconds, which is the reading the S310 fix adopts.
