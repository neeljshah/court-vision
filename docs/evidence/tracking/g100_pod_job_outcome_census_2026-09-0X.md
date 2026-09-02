# G100 Pod Job Outcome Census

## Scope and frozen read

This is a retrospective, read-only census. No daemon code, threshold, timeout,
pod process, ledger row, coordinate contract, or job was changed. The live
source was `/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl`.
It contained **401 valid JSONL rows** when read (the brief's 397-row count was
already stale because the daemon was appending). The 401 rows contain 187
distinct `game_id` values; this memo intentionally counts ledger job outcomes,
not unique games.

| status | rows |
|---|---:|
| tracked | 183 |
| thin | 165 |
| timeout | 50 |
| corrupt | 3 |
| total | 401 |

The committed data products are the [snapshot summary](g100_pod_census/ledger_snapshot_summary.csv), [outcomes by sport and path](g100_pod_census/outcome_by_sport_adapter.csv), the [thin row-count distribution](g100_pod_census/thin_row_count_distribution.csv), the [pre-checkpoint timeout rows](g100_pod_census/timeout_pre_first_checkpoint.csv), and the [output spot checks](g100_pod_census/spot_checks.csv).

## (a) Exact meaning of `thin`

`track_daemon._finish()` writes the status with this exact condition:

```python
graded = None if timed_out else verdict(job["sport"], job["game_id"], job["video"])
status = "timeout" if timed_out else "tracked" if graded is not None else "thin"
```

`verdict()` calls `adjudicate()`. `adjudicate()` returns `None` when the CSV
cannot be fsynced, cannot be read, or is empty. For any readable nonempty CSV,
it writes `harness_verdict.json` atomically and returns a payload, whether the
harness result is passed or failed. `retain()` runs after the ledger record and
moves footage; it does not decide the status.

Therefore `thin` means: **a non-timeout completion for which no durable
adjudication payload was returned**. It is not a row-count threshold and does
not mean "the harness failed". The historical rows can predate the currently
deployed source behavior, so this establishes the writer condition rather than
asserting a single causal mechanism for every old row.

## (b) Thin by sport and adapter path

The daemon routes `wnba`, `basketball`, `ncaa_basketball`, and `nba` through
`run_clip.py` (5,400 s); all other acquisition labels go through the adapter
registry (12,000 s). The full sport-by-path counts and elapsed-time sums are in
[the outcome table](g100_pod_census/outcome_by_sport_adapter.csv).

| adapter path | thin jobs | share of thin | ledger seconds |
|---|---:|---:|---:|
| adapter registry | 158 | 95.8% | 145,702 |
| run_clip.py | 7 | 4.2% | 3,589 |
| total | 165 | 100.0% | 149,291 |

Thin is overwhelmingly on the adapter-registry path. The largest individual
sport slice is `baseball` with 53 thin outcomes (12.81 estimated job-hours),
followed by football with 32 (11.17 estimated job-hours) and MLB with 32
(4.96 estimated job-hours).

## (c) Timeout by sport and adapter path; checkpoint cliff

| adapter path | timeout jobs | share of timeout | ledger seconds |
|---|---:|---:|---:|
| adapter registry | 24 | 48.0% | 68,559 |
| run_clip.py | 26 | 52.0% | 87,529 |
| total | 50 | 100.0% | 156,088 |

The documented `run_clip.py` signature before its first 2,000-frame checkpoint
is zero to four output rows (the four frame-0 rows are possible). Applying that
documented signature gives **25 of 50 timeouts (50.0%)** with no post-checkpoint
rows: 17 NCAA basketball and 8 WNBA. Their 82,113 ledger seconds equal **22.81
estimated job-hours**. Every qualifying row is enumerated in
[the pre-checkpoint table](g100_pod_census/timeout_pre_first_checkpoint.csv).

## (d) Thin row-count distribution

The distribution is not homogeneous: its median is 0, with 93/165 jobs at zero
rows, 97/165 at zero through four rows, and 68/165 above four rows. The range is
0 to 496 rows. Every observed row-count value and multiplicity is in
[the distribution table](g100_pod_census/thin_row_count_distribution.csv); a
4-row and a 496-row result do share the `thin` label.

## (e) Largest recoverable bucket (estimate)

The largest **confirmed recoverable** bucket is the 25 clip-path timeouts before
the first post-2,000-frame checkpoint: 82,113 `seconds`, or **22.81 estimated
job-hours**. This is an estimate formed as `sum(seconds) / 3600`; it is pod job
slot time, not a measurement of GPU utilization under concurrent work.

The raw `thin` adapter-registry slice is larger in elapsed time (158 jobs,
145,702 seconds, 40.47 estimated job-hours), but it is not labelled recoverable
here: the `thin` condition establishes lack of a durable adjudication payload,
not that a particular change would rescue every raw output.

## Eye checks

Three current outputs were selected from the three ordinal thirds of the 165
thin ledger rows, restricted only to the 34 whose current CSV still exactly
matched its historical row count and still lacked a verdict sidecar. Earlier
unrestricted quartile picks had been superseded by later re-tracks and were not
used as evidence. The three inspected CSVs each contained only a header, had
zero data rows matching their ledger row, and had no `harness_verdict.json`.
Details, including headers and byte sizes, are in
[the spot-check table](g100_pod_census/spot_checks.csv).

## NOT VERIFIED

- The ledger does not carry a kill frame for these timeout rows. `rows <= 4` is
  the daemon's documented first-checkpoint signature, not an independently
  recorded frame number.
- This census does not establish the root cause of each historic thin outcome
  or that every thin raw output is unrecoverable.
- Current output paths are mutable across re-tracks. Only 34 of 165 thin rows
  still matched their historical row count and lacked a verdict sidecar at the
  time of the spot-check selection.
- No GPU utilization telemetry was read; estimated job-hours are elapsed ledger
  seconds divided by 3,600.

## Verifier-contract self-check

- A1: no code was added, so no new per-file test exists to rerun.
- A2: status counts, the 165-row thin distribution, and all grouped totals were
  independently recomputed from all 401 valid ledger rows before writing tables.
- A3: no render evidence is used. Output checks are spread over three ordinal
  bands, with the eligibility restriction and its reason stated above.
- A4: counted 187 unique `game_id` values separately from 401 job-outcome rows.
- A5: this change adds evidence only and touches no schema field or reader.
- A6: landing to master is verifier work; this lane made the explicit-path a11
  commit requested by G100 and did not copy anything to the pod.
- A7: every committed evidence path linked in this memo was checked after the
  commit. The live pod ledger and CSVs are source observations, not committed
  evidence artifacts.

Section B self-check: B1 no rows were excluded (all 401 valid ledger rows are
counted); B2 no schema changed; B3-B6 no gate, claim, deployment, or module
changed; B7 no head-slice render evidence; B8 no fitted metric; B9 each unit is
one ledger job outcome with `game_id` uniqueness separately reported; B10 no
bar or threshold changed.
