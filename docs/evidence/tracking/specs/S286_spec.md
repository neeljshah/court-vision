GAP S286 | sport nba (in-game) | worktree a18 | log cx_s286_empirical_quantile_crps
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: Angelopoulos & Bates, arXiv 2107.07511 (2021), and the general quantile-regression/nonparametric-
  interval literature give the standard quant-desk alternative to assuming a Normal outcome distribution:
  score realized empirical quantiles instead of a fitted parametric scale. S227 (ACCEPT) fit a PARAMETRIC
  Gaussian sigma per frozen ladder point over scripts/platformkit/s227_margin_tail_crps.py's own `_cell`
  grammar (period x |margin| bucket x remaining-time bucket) and found a small win over the fixed sigma=13.5
  baseline (CRPS delta +0.003463, 95 pct CI [0.000419, 0.006641]). No nonparametric (empirical-quantile) arm
  has been scored on the same cells.
PREMISE (step 0, INFORMATIONAL): import s227's own `load`, `_cell`, `_remaining_fraction` unmodified; print n
  ticks/games and, per `_cell` value, the earliest walk-forward train fold's row count, naming every cell
  below s227's own MIN_CELL_TRAIN=200 threshold (the cells needing a parent-cell fallback, not silently
  pooled).
CHANGE (step 1): additive new arm only. Per `_cell`, walk-forward per s227's own N_GROUPS/EMBARGO_DAYS folds,
  build the empirical CDF of (final_margin minus the tick's point forecast) from strictly-prior training rows
  (sparse cells fall back to their parent period bucket, named); score CRPS via `crps_ensemble` in
  scripts/platformkit/dist_metrics.py against s227's own fixed-sigma and fitted-sigma arms on identical
  rows/folds through scripts/platformkit/eval_gate/cpcv_engine.cpcv_evaluate, purge + symmetric embargo.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = empirical-quantile-arm minus s227's fitted-sigma-arm CRPS, game-clustered 95 pct CI, with
                  the fixed-sigma arm's CRPS printed beside both
  before        = S227's fitted-sigma CRPS delta over fixed sigma is +0.003463, CI [0.000419, 0.006641]; no
                  nonparametric arm has been scored
  bar           = matching or trailing S227's fitted-sigma arm is the expected valid result (Normal is
                  already close to sufficient at this sample size); a CI-crossing-zero delta is a valid NULL
  n             = >= 30 game clusters (1,593 games available)
  eye check     = n/a (S-row); reproduction = verifier reruns the empirical-CDF build and diffs every CRPS
  must not move = nba_checkpoints_full.parquet, s227_margin_tail_crps.py, dist_metrics.py, the FROZEN_LADDER
NON-TAUTOLOGY: the empirical CDF is built ONLY from strictly-prior training rows within a fold, never the
  scored fold's own rows; a candidate leaking test-fold rows into its own quantile estimate is self-rejected.
  Sparse cells fall back by name, never dropped from the denominator.
EVIDENCE: docs/evidence/harness/S286_empirical_quantile_crps_2026-09-04.md + summary JSON + paired-loss CSV.
TEST: one per-file test building the empirical CDF on a fixture (one sparse cell, one dense cell) and
  reproducing one cell's CRPS from the archived CSV.
REPORT: sparsity census, three-arm CRPS table, RSS, test line, SHA. No push. NEVER PARK.
