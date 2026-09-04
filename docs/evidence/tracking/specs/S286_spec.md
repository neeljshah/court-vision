GAP S286 | sport nba (in-game) | worktree a18 | log cx_s286_empirical_quantile_crps
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: S227 fit Gaussian sigma per _cell; FROZEN_LADDER contains evaluation thresholds only.
PREMISE (step 0, INFORMATIONAL): import s227's own `load`, `_cell`, `_remaining_fraction` unmodified; print n
  ticks/games and, per `_cell` value, the earliest walk-forward train fold's row count, naming every cell
  below s227's own MIN_CELL_TRAIN=200 threshold (the cells needing a parent-cell fallback, not silently
  pooled).
CHANGE (step 1): additive new arm only. Per `_cell`, walk-forward per s227's own N_GROUPS/EMBARGO_DAYS folds,
  build the empirical CDF of (final_margin minus the tick's point forecast) from strictly-prior training rows
  (sparse cells fall back to their parent period bucket, named); score CRPS via `crps_ensemble` in
  scripts/platformkit/dist_metrics.py against s227's own fixed-sigma and fitted-sigma arms on identical
  rows/folds through scripts/platformkit/eval_gate/cpcv_engine.cpcv_evaluate, purge + symmetric embargo.
  Call crps_ensemble once per observation so the paired series and CI are reproducible.
PREREG: seal a prereg FIRST as its own commit (LF); hash the STAGED bytes above the seal line via git show :<path>.
Verify with git show HEAD:<path>; the seal test normalizes CRLF to LF and hashes the bytes above the seal line.
WHERE: local; above 500 MB use ~/bin/pod_run <aN> --fetch <outputs> -- <command> under the B5 NOTE.
Never write data/ or docs/research/; never rewrite an existing artifact; use new dated filenames.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = fitted-sigma CRPS minus empirical-CDF CRPS, archived per tick and aggregated per game.
  before        = S227's fitted-sigma CRPS delta over fixed sigma is +0.003463, CI [0.000419, 0.006641]; no
                  nonparametric arm has been scored
  bar           = AHEAD if CI lower > 0; MATCH if CI contains 0; TRAILING if CI upper < 0.
  sign          = improvement = baseline loss minus candidate loss; positive = candidate better; compared with
                  the frozen +0.004 bar.
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
