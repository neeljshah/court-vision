# S294 preregistration: full-source S86-block CPCV STATIC conformal coverage

## Scope and status

This is one additive, uncharged NBA in-game calibration measurement. It names
no comparative promotion, writes neither a ledger nor a register, and uses
calibration language only. It does not replace any S276 evidence. The S276
correction is an erratum under a new dated name.

## Binding premise measured before this seal

The game_id-only stream of
`data/cache/inplay_odds/nba_checkpoints_full.parquet` measured 465249 ticks
in 1593 game clusters. The source is a 2829826-byte Parquet tabular input;
pixel resolution is not applicable. The retained S101 references are
`data/cache/eval_gate/s101_aci_coverage_2026-09-03.json` (30939-byte JSON
tabular summary) and
`data/cache/eval_gate/s101_aci_coverage_2026-09-03_ticks.csv.gz`
(18426107-byte compressed CSV tabular input); pixel resolution is not
applicable for both.

`s94_nba_early_shrinkage.fold_dates` on the frozen full grid, with its fixed
five held-out folds, returned these six tick-balanced date blocks:

| Block | First game_date | Last game_date | Ticks | Games |
| ---: | --- | --- | ---: | ---: |
| 0 | 2024-10-22 | 2024-12-08 | 78255 | 248 |
| 1 | 2024-12-09 | 2025-01-27 | 80259 | 289 |
| 2 | 2025-01-28 | 2025-11-05 | 75563 | 238 |
| 3 | 2025-11-06 | 2026-01-02 | 77853 | 277 |
| 4 | 2026-01-03 | 2026-02-26 | 75904 | 264 |
| 5 | 2026-03-01 | 2026-06-13 | 77415 | 277 |

## Fixed OOS design

- The route creates exactly one evaluator state for every loaded source tick.
  Its stable key is `game_id|source_row|ts`; no game-level state substitutes
  for a tick.
- The six group labels are derived only from the block routine above. It calls
  `cpcv_evaluate` with six groups, one held-out group per path, game-disjoint
  purge, and the shared evaluator's fixed symmetric one-day embargo. Each of
  the six listed blocks is held out exactly once.
- The evaluator callback fits the ladder-base incumbent only from the purged
  train states. All archived model probabilities are copied from evaluator
  records, and every archived loss is computed from those records only.
- The unchanged S101 `run_fold` and `score` callbacks fit STATIC bands from
  OOS evaluator records and score nominal levels 0.90 and 0.80. The fixed
  constants remain `COVERAGE_MIN_GROUP=400`, `COVERAGE_MAX_GROUPS=50`, and
  the committed S101 24-cell tolerance remains `1e-9`. A cell below the
  requirement is named `ABSENT_BECAUSE`.
- The route asserts 465249 loaded, scorable, and scored ticks; 1593 loaded,
  scorable, and scored game clusters; unique stable state keys; and named
  exclusions. It also archives every paired evaluator loss and grouped
  coverage unit.

## Execution and evidence

The compute runs only through `/c/Users/neelj/bin/pod_run a17 --fetch
<outputs> -- python -m <entrypoint>` in `/workspace/wt/a17`. The deployed
tree is never written before acceptance. No process is stopped or restarted;
no ledger, hypotheses database, registry, or flag is touched. The pod output
must print peak RSS and both-sided MD5 parity for every shipped route input.

New evidence paths are
`docs/evidence/harness/S294_incumbent_conformal_full_s86_blocks_2026-09-04.md`,
`docs/evidence/harness/S294_incumbent_conformal_full_s86_blocks_2026-09-04.json`,
`docs/evidence/harness/S294_incumbent_conformal_full_s86_blocks_paired_loss_2026-09-04.csv.gz`,
and a pod log tail. The focused test reads only the preregistration and fetched
archives; it normalizes CRLF to LF before checking this seal and recomputes one
grouped cell from the CSV.

SEAL_SHA256: 0591642749e4dbf7bf71207b094e34759fe0c91fa9441f3296a1b79066503b90
