# S298 preregistration: rare-count mixture comparison

This preregistration fixes the S298 comparison before its first metric. It
self-checks sections B and Q1-Q9 of
`docs/evidence/tracking/VERIFIER_CONTRACT.md`.

## Binding premise

The binding pre-condition is re-run before score execution with pyarrow
row-group reads. Its required result is:

- `data/domains/basketball_nba/player_boxscores.parquet`: STL zeros 40520;
  BLK zeros 53267.
- `data/cache/omni_box_refresh/nba_player_box_extension.parquet`: STL zeros
  669; BLK zeros 799.

The two source paths, their first three `(game_id, player_id)` keys, byte
sizes, SHA-256 values, and the four counts are emitted in the run summary and
memo before any reported metric. The scorer stops if any binding count differs.

## Frozen comparison

Each player-game is exactly one evaluator state and one stable key
`game_id|player_id`; it is never expanded into a substitute per-game unit.
States are ordered by date at 12:00 local-naive time. The only predictor
feature is `strict_prior_marker`, available one day before the state time. The
test view removes the settled observed count. For each test state and stat,
every fit uses only evaluator-supplied train states strictly earlier than the
test state. No row is excluded after its outcome is known.

The shared evaluator is
`scripts.platformkit.eval_gate.cpcv_vector_distribution.cpcv_evaluate_vector_distributional`,
which delegates purging and a symmetric nonzero one-day embargo to
`scripts.platformkit.eval_gate.cpcv_engine`. It uses five date groups, one
held-out group per fold, and rejects a fold with fewer than 30 held-out game
clusters. Every source state is held out exactly once.

For both STL and BLK, score all four finite integer-support forecasts:

1. Poisson baseline, with a strictly-past player mean or strictly-past league
   mean fallback;
2. NB2, fitted from strictly-past mean and variance, falling back to the
   Poisson limit when dispersion is not finite and positive;
3. hurdle-NB2, with strictly-past zero probability and a truncated-positive
   NB2 component; and
4. ZINB, with a strictly-past zero-inflation estimate and NB2 component.

The PMF support is integers `0..20` plus a final `tail_gt_20` bucket. A model
is rejected before scoring if its finite CDF/PMF cannot be produced, has a
negative mass, or its stored support including tail does not sum to one within
`1e-12`. The bounded support is an archive convention, not outcome truncation:
every observed count receives its correct tail probability when above 20.

NB2, hurdle-NB2, and ZINB remain separate scored families. A deterministic
inner strictly-past walk-forward log-score selection is recorded per stat and
outer fold only as a selection diagnostic; it may not remove or relabel any
outer comparison. Every family, including the worst, is published.

## Metrics and decision rule

Primary metric is discrete log score. Its sign convention is improvement =
Poisson log score minus candidate log score; positive means candidate lower
loss, in discrete log-score units. Secondary diagnostics are ranked probability
score (RPS), zero reliability (predicted zero mass minus observed zero rate,
reported as an absolute error), and randomized PIT.

The six primary comparisons are STL and BLK each against NB2, hurdle-NB2, and
ZINB. For each, bootstrap game-cluster means with seed 298 and 4000 resamples,
then calculate paired two-sided 95 percent intervals. The Holm-adjusted paired
95 percent lower bound must be greater than 0 for all six comparisons. This is
the fixed S298 bar; no NBA Brier threshold applies to this count log-score
comparison. A failure is reported as REJECT or CLOSED AT LIMIT without moving
the bar. This is one corpus window, so no AHEAD result is claimed.

## Inputs, durability, and machine

The scorer is expected to exceed 500 MB RSS and therefore runs once, only on
the pod in scratch `/workspace/wt/a10/` through
`/c/Users/neelj/bin/pod_run a10 --ship <this run evidence inputs> --fetch <outputs> -- <command>`.
The deployed pod tree is not written. Inputs are opened one store at a time:

| Path | Bytes | Resolution |
|---|---:|---|
| `data/domains/basketball_nba/player_boxscores.parquet` | 1118538 | tabular; not applicable |
| `data/cache/omni_box_refresh/nba_player_box_extension.parquet` | 34147 | tabular; not applicable |

Outputs are new dated files only: a JSON summary, re-emitted per-state PMF
archive, paired-loss CSV, evidence memo, and one focused test. The PMF archive
retains ids, dates, observed count, zero flag, family PMFs through the stated
tail cutoff, evaluator split, strict-prior feature availability, and model
as-of summary. The paired-loss archive is derived from evaluator records only.
No source parquet, model, quantile calibration file, register, or ledger is
opened for write. The one test reads the preregistration file, normalizes CRLF
to LF, and verifies the bytes above this seal line; it does not use `git show
HEAD`.

S298_PREREG_SEAL_SHA256=906ef129f74c860192046e1c60d21fffb2dd9c98a780efc766f2b30597be082b
