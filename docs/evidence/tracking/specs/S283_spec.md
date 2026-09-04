GAP S283 | sport nba (in-game) | worktree a15 | log cx_s283_bayes_timescore_blend
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: Maddox et al., "Bayesian estimation of in-game home team win probability for NBA games," arXiv
  2207.05114 (2022), and its college-basketball parent arXiv 2204.11777, build a nonparametric win-rate table
  by time-elapsed and margin, blended with a time-weighted pregame prior via a FITTED, non-constant weight --
  distinct from Stern's parametric Brownian-motion form, already SCREENED NULL on WNBA by S206 (candidate delta
  +0.000384828, CI [-0.000210271, +0.000979927]). No nonparametric time-score table has been built on
  nba_checkpoints_full.parquet (465,249 ticks/1,593 games, columns verified this session, matching S277).
PREMISE (step 0, INFORMATIONAL): via scripts/platformkit/eval_gate/s86_nba_every_tick.load_ticks, print n
  ticks/games and the period_bucket/margin_bucket/rem_bucket cell counts s86's own `_cell` defines; name every
  cell whose earliest walk-forward train fold holds fewer than 200 rows (the sparse cells needing a fallback,
  not silently pooled).
CHANGE (step 1): additive new arm only. Build, walk-forward per s86 fold, an empirical table P(home wins |
  period_bucket, margin_bucket, rem_bucket) from strictly-prior folds' outcome_home_win (sparse cells fall back
  to their parent period_bucket table, named); blend with market_prob via weight w = rem_fraction ** k, k
  chosen on TRAIN folds only from the frozen grid {0.5, 1, 2, 4} by train-fold Brier, archived per fold; score
  scripts/platformkit/foundry/ingame_incumbent_nba.apply_incumbent's recal_null and the blended arm on
  identical rows/folds via cpcv_engine.cpcv_evaluate, purge + symmetric nonzero embargo.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = blended-arm minus recal_null Brier improvement, game-clustered 95 pct CI, with market and
                  recal_null Brier/ECE printed beside it
  before        = no empirical time-score table exists; S206's parametric Stern arm SCREENED NULL on WNBA
  bar           = the frozen +0.004 bar vs recal_null; NULL is the expected valid result per the S206 precedent
  n             = >= 30 game clusters (1,593 games available)
  eye check     = n/a (S-row); reproduction = verifier reruns the table build and blend, diffs every Brier
  must not move = nba_checkpoints_full.parquet, s86_nba_every_tick.py, ingame_incumbent_nba.py, the +0.004 bar
NON-TAUTOLOGY: k is selected on TRAIN folds only, never on the fold it scores; a candidate choosing k per test
  fold is circular and self-rejected. Sparse cells fall back by name, never dropped from the denominator.
EVIDENCE: docs/evidence/harness/S283_bayes_timescore_blend_2026-09-04.md + summary JSON + paired-loss CSV.
TEST: one per-file test building the empirical table on a fixture (one sparse cell, one dense cell) and
  reproducing the blend weight plus one game's Brier from the archived CSV.
REPORT: sparsity census, chosen k per fold, Brier/ECE table, RSS, test line, SHA. No push. NEVER PARK.
