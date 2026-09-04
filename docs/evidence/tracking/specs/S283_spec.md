GAP S283 | sport nba (in-game) | worktree a18 | log cx_s283_bayes_timescore_blend
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: Maddox et al., "Bayesian estimation of in-game home team win probability for NBA games," arXiv
  2207.05114 (2022), and its college-basketball parent arXiv 2204.11777, build a nonparametric win-rate table
  by time-elapsed and margin, blended with a time-weighted pregame prior via a FITTED, non-constant weight --
  distinct from Stern's parametric Brownian-motion form, already SCREENED NULL on WNBA by S206 (candidate delta
  +0.000384828, CI [-0.000210271, +0.000979927]). No nonparametric time-score table has been built on
  nba_checkpoints_full.parquet (465,249 ticks/1,593 games, columns verified this session, matching S277).
PREMISE: use s86_nba_every_tick.load_ticks plus period_bucket, margin_bucket and rem_bucket; print all
  bucket-cross counts.
CHANGE (step 1): additive new arm only. Build an empirical table P(home wins | period_bucket, margin_bucket,
  rem_bucket) from strictly-prior outcome_home_win rows (sparse cells, < 200 train rows, fall back to their parent
  period_bucket table, named); blend with market_prob via weight w = rem_fraction ** k, k chosen on TRAIN folds only
  from the frozen grid {0.5, 1, 2, 4} by train-fold Brier, archived per fold; score apply_incumbent's recal_null
  and the blended arm on identical rows via cpcv_evaluate with n_groups=5, n_test_groups=1 and embargo_days=1;
  every table and k is fit inside its train membership; the callback produces every scored probability.
PREREG: seal a prereg FIRST as its own commit (LF); hash the STAGED bytes above the seal line via git show :<path>.
Verify with git show HEAD:<path>; the seal test normalizes CRLF to LF and hashes the bytes above the seal line.
WHERE: local; above 500 MB use ~/bin/pod_run <aN> --fetch <outputs> -- <command> under the B5 NOTE.
Never write data/ or docs/research/; never rewrite an existing artifact; use new dated filenames.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = recal_null Brier minus blended-arm Brier, with a game-clustered 95 pct CI.
  before        = no empirical time-score table exists; S206's parametric Stern arm SCREENED NULL on WNBA
  bar           = the frozen +0.004 bar vs recal_null; NULL is the expected valid result per the S206 precedent
  sign          = improvement = baseline loss minus candidate loss; positive = candidate better; compared with
                  the frozen +0.004 bar.
  n             = >= 30 game clusters (1,593 games available)
  eye check     = n/a (S-row); reproduction = verifier reruns the table build and blend, diffs every Brier
  must not move = nba_checkpoints_full.parquet, s86_nba_every_tick.py, ingame_incumbent_nba.py, the +0.004 bar
NON-TAUTOLOGY: k is selected on TRAIN folds only, never on the fold it scores; a candidate choosing k per test
  fold is circular and self-rejected. Sparse cells fall back by name, never dropped from the denominator.
EVIDENCE: docs/evidence/harness/S283_bayes_timescore_blend_2026-09-04.md + summary JSON + paired-loss CSV.
TEST: one per-file test building the empirical table on a fixture (one sparse cell, one dense cell) and
  reproducing the blend weight plus one game's Brier from the archived CSV.
REPORT: sparsity census, chosen k per fold, Brier/ECE table, RSS, test line, SHA. No push. NEVER PARK.
