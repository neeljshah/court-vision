# G105 Recover Lost GPU Hours

This is a read-only sizing investigation for
[G105_spec.md](specs/G105_spec.md), performed against 403 valid live pod ledger
rows. It cites and self-checks
[VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A7 and every item in
section B. No job was rerun; no pod process, timeout, threshold, ledger row,
coordinate contract, `track_daemon.py`, or `src/` file was changed.

## Fresh source and mechanics check

The growing live ledger contained 403 valid JSONL rows: 185 `tracked`, 165
`thin`, 50 `timeout`, and 3 `corrupt`. This is two more tracked rows than
G100's 401-row read; all G105-relevant buckets are unchanged.

The current daemon sets `CLIP_JOB_TIMEOUT_SECONDS = 5400`. Its comments record
four concurrent NCAA processing-rate measurements, while
`UnifiedPipeline` checkpoint-enqueues and clears tracking rows only at the
2,000-frame cadence. Normal completion does flush/export the residual, but a
daemon timeout calls `Popen.kill()` (SIGKILL), so normal Python cleanup cannot
run. The exact observed rows are committed in
[timeout_pre_first_checkpoint_live.csv](g105_recovery/timeout_pre_first_checkpoint_live.csv)
and the documented rate measurements in
[timeout_rate_measurements.csv](g105_recovery/timeout_rate_measurements.csv).

## Bucket 1: clip timeout checkpoint cliff

All 25 qualifying clip-path timeout outcomes were re-enumerated. They total
82,113 elapsed ledger seconds, or **22.81 estimated job-hours**. This is job
slot time (`seconds / 3600`), not GPU-utilization telemetry. The complete
distribution is:

| Observed timeout group | Jobs | Elapsed seconds | What it establishes |
|---|---:|---:|---|
| 2,701--2,715 s | 17 | 46,044 | Historical job needed more than its recorded timeout; no per-job rate was stored. |
| 3,608--3,609 s | 4 | 14,435 | Same lower-bound-only conclusion. |
| 5,401--5,416 s | 4 | 21,634 | Current 5,400-s cap still did not reach a post-2,000-frame checkpoint. |
| Total | 25 | 82,113 | Confirmed cliff-exposed work. |

The four available measured rates imply first-checkpoint times of 2,062, 2,439,
2,564, and 3,610 seconds. Thus, the earlier 3,600-second timeout needed only
10 additional seconds for the slowest observed measurement; the 5,400-second
cap already adds up to 1,800 seconds (50%) of maximum slot occupancy per job
relative to 3,600 seconds. It did **not** resolve the later four 5,401--5,416-s
cases.

The ledger records neither a kill frame nor a processing-rate measurement for
any of the 25 historic outcomes (their source-rate, duration, and log-tail
fields are null). Consequently, there is no defensible single replacement
timeout, and no way to claim that a larger one would clear all 25. The
per-row strict lower bounds and both distributions are retained in
[timeout_checkpoint_distribution.csv](g105_recovery/timeout_checkpoint_distribution.csv).

| Candidate fix | Recoverable job-hours | Additional slot holding | Recommendation |
|---|---:|---|---|
| (a) Raise timeout again | 0 confirmed; 22.81 is only an upper bound if every job crosses later | A configured cap above 5,400 holds each still-running slot longer; the four current-cap misses need at least 2--17 more seconds merely to exceed their observed elapsed time, with unbounded further time to frame 2,000 from this ledger | **Do not raise it again now.** First record kill frame and processing FPS per timeout; current evidence already falsifies 5,400 as a universal solution. |
| (b) Cooperative residual checkpoint flush | 22.81 confirmed cliff-exposed job-hours whose partial work would be retained rather than requiring a repeat solely to obtain durable output | No timeout increase; a short shutdown grace is required before hard kill | **Recommend human application.** It removes the all-or-nothing checkpoint cliff rather than moving it. |

The proposed implementation is
[G105_residual_checkpoint_PROPOSED.diff](../../research/organization-sprint/G105_residual_checkpoint_PROPOSED.diff).
It is not applied and awaits human review/application because it touches the
human-gated `src/` tree and requires paired cooperative daemon termination.

## Bucket 2: adapter-registry `thin`

The 158 adapter-registry `thin` outcomes total 145,702 ledger seconds, or
**40.47 estimated job-hours**. The full sport sizing is committed in
[thin_adapter_sizing.csv](g105_recovery/thin_adapter_sizing.csv).

`thin` means the non-timeout daemon completion received no durable adjudication
payload. Current `adjudicate()` returns `None` before it writes a sidecar when
the CSV cannot be fsynced/read or is empty; a readable nonempty CSV receives an
atomic sidecar even if the harness fails. Therefore a header-only CSV with no
sidecar is evidence of no raw observations, not a failed quality verdict.

Six outputs were opened across distinct adapter sports, exceeding the required
five. The exact inspection data are in
[thin_opened_outputs.csv](g105_recovery/thin_opened_outputs.csv):

| Sport | Game | Current result | Inference |
|---|---|---|---|
| football | `football_a7OUF22mt-I` | Historic 0 rows still match; 23-byte header only; no sidecar | Non-timeout job completed but had no raw observations to adjudicate. |
| mlb | `mlb_FGtFanovws4` | Historic 0 rows still match; 64-byte header only; no sidecar | Same cause. |
| tennis | `tennis_10` | Historic 0 rows still match; 87-byte header only; no sidecar | Same cause. |
| baseball | `mlb_2026-08-30_10893dca` | Historic 116 rows; current path has 3,061 rows | Current path was re-tracked; cannot attribute its present content to the historic thin outcome. |
| kbo | `kbo_Y4HqKr58TZk` | Historic 7 rows; current path has 18,736 rows | Current path was re-tracked; no historic-cause claim. |
| soccer | `soccer_HxBqMbI5kqQ` | Historic 256 rows; current path has 91,744 rows | Current path was re-tracked; no historic-cause claim. |

The stable cases answer the narrow causal question: these are **non-timeout
completions with empty raw output, not completions that merely lost a verdict
payload**. They are not rescued by the basketball residual-flush change. The
remaining current paths are mutable, and the ledger has no per-job adapter
progress telemetry, so recoverability for the 40.47 job-hour adapter bucket is
**0 confirmed**. Its causal investigation remains an adapter-output issue, not
a reason to increase the clip timeout.

Recommendation: preserve the 158 / 40.47 sizing as an at-risk bucket, but do
not claim it as recoverable until an adapter-specific experiment captures raw
output/progress before and after its completion path. No pod rerun was
authorized or performed here.

## NOT VERIFIED

- The ledger does not record a kill frame or processing FPS for any of the 25
  historic timeout records; an exact all-25 checkpoint-clear timeout
  distribution cannot be calculated from existing evidence.
- The four documented NCAA rate observations are not a rate measurement for
  every historic timeout attempt, including the WNBA and WFl3V7ZY4ss cases.
- A 5,417-second cap merely exceeds the largest recorded elapsed time; it is
  not verified to reach frame 2,000 for the four current-cap misses.
- Mutable current output paths cannot establish the cause of their older thin
  ledger records. The absent handball output was not treated as evidence.
- No GPU utilization, frame-level kill telemetry, or durable adapter-progress
  sidecar was available.
- The proposed diff has not been human-applied, tested, deployed, or copied to
  the pod.

## Verifier-contract self-check

- A1: no code or test was added; there is no new per-file test to rerun.
- A2: all headline counts and sums were recomputed from all 403 valid live
  ledger rows; the 25 timeout rows and 158 adapter thin rows are committed as
  additive derived tables.
- A3: no render metric is asserted. Output inspection covers six sports rather
  than a head slice; mutable paths are named rather than excluded.
- A4: this metric's unit is a ledger job outcome, not a unique game. G100's
  separately reported 187 unique game IDs is not reused as this denominator.
- A5: no schema field or reader changed.
- A6: this lane made no deployment, archive landing, or pod copy. The requested
  explicit-path worktree commit is made before reporting; verifier landing is
  deliberately left to the verifier.
- A7: before reporting, every memo-named committed evidence path was checked to
  exist in the commit: this memo, five derived CSVs, and the explicitly staged
  proposed diff. Live pod observations are sources, not committed evidence.

Section B self-check: B1 all 403 valid rows were counted without outcome-based
exclusion; B2 no schema changed; B3 no gate was changed; B4 no claiming path
changed; B5 no pre-verification deployment occurred; B6 no module moved or
retired; B7 no head-slice evidence was used; B8 no fitted metric is claimed;
B9 each unit is one distinct ledger outcome (duplicate game IDs remain distinct
outcomes); and B10 no timeout, threshold, or harness bar changed.
