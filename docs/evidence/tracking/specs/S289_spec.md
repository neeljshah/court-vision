GAP S289 | sport nba (in-game) | worktree aXX | log cx_s289_ingame_longshot_bins
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: successor to S224/S272 (S272 BEHIND, docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04.md,
  tail-candidate minus recal_null improvement -0.000037 [-0.000070, -0.000008]) and S277 (NULL). Both scored the
  nba_checkpoints_full.parquet grid via scripts/platformkit/foundry/ingame_incumbent_nba.py apply_incumbent(...,
  "recal_null") and scripts/platformkit/eval_gate/cpcv_engine.py cpcv_evaluate (purge + symmetric embargo).
  Neither scored the FAVORITE-LONGSHOT bias in fine bins near 0/1 with log-loss (Brier is tail-insensitive per
  the program's tail design rule). This row is the fine-bin screen those rows never ran.
PREMISE (step 0): reproduce the measured bin counts on nba_checkpoints_full.parquet (465,249 ticks/1,593 games;
  columns game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin, market_prob, traded,
  market_ticker, outcome_home_win, venue): [0.01,0.05) 9226/649 games, [0.05,0.10) 8982/691, [0.10,0.20)
  15778/826; mirrors [0.80,0.90) 23912/1005, [0.90,0.95) 13123/871, [0.95,0.99) 12624/827.
CHANGE (step 1): additive module scripts/platformkit/ingame/s289_ingame_longshot_bins.py (<=300 LOC): per-bin
  LOG-LOSS and reliability (empirical outcome rate vs mean market_prob), market vs recal_null incumbent
  (unmodified apply_incumbent import), through cpcv_evaluate; ALSO the all-ticks Brier improvement of recal_null
  over market with its CI (non-inferiority requirement). Seal a prereg FIRST as its own commit (LF; seal =
  SHA-256 of the STAGED bytes above the seal line via git show :<path>, verified with git show HEAD:<path>; the
  seal TEST reads the FILE, normalizes CRLF to LF, hashes above the seal line). Print RSS before/after; a scorer
  above 500 MB runs via ~/bin/pod_run <aN> --fetch <outputs> -- <command>. Never write data/ or docs/research/;
  never rewrite an existing artifact (new dated filenames; legacy fields as aliases).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-bin log-loss + reliability, recal_null vs market, game-clustered 95 pct CI on the six
                  bins; PLUS all-ticks Brier improvement of recal_null over market with its own CI
  before        = S272 tail-candidate minus recal_null improvement -0.000037 [-0.000070,-0.000008]; no fine-bin
                  log loss exists.
  Also print recal_null minus market Brier on the exact all-tick rows before applying the non-inferiority rule.
  bar           = frozen +0.004 all-ticks Brier bar untouched; all-ticks improvement CI LOWER BOUND > -0.0005 (preregistered
                  non-inferiority tolerance = 1/8 of the bar; a CI merely not below 0 proves nothing)
  sign          = improvement = baseline loss minus candidate loss; positive = candidate better; compared with
                  the frozen +0.004 bar.
  n             = 9226/8982/15778/23912/13123/12624 ticks (649/691/826/1005/871/827 games) per bin, each >= 30
  eye check     = n/a (S-row); reproduction = verifier recomputes log-loss/reliability/CI per bin and the
                  all-ticks Brier delta from the archived paired-loss CSV
  must not move = S272/S277 artifacts; the +0.004 bar; ingame_incumbent_nba.py apply_incumbent byte-identical
                  (SHA-256 printed); nothing charged
NON-TAUTOLOGY: report all six bins including any that hurt recal_null; no bin is dropped to improve the mean.
EVIDENCE: docs/evidence/harness/S289_ingame_longshot_bins_2026-09-04.md + summary JSON + paired-loss CSV (Q9).
TEST: one per-file test recomputing one bin's log-loss and the all-ticks Brier delta from the archived CSV.
REPORT: per-bin table, CIs, non-inferiority check, RSS, test line, SHA. No push. NEVER PARK.
