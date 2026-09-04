GAP S293 | sport nba (in-game) | worktree aXX | log cx_s293_tail_metric_rail
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: the shared evaluator route S268/S272 both used is scripts/platformkit/eval_gate/cpcv_engine.py:93
  def cpcv_evaluate (records p_model/p_close/y/split_id/n_train) and scripts/platformkit/eval_gate/
  walkforward.py:122 def walk_forward. Neither is on the SHARED_MODULE_TOKEN list (ledger.py/backtest_runner.py/
  combo/fwer_budget.py are); the precedent for adding fields beside them without editing them is S268 (ACCEPT):
  it added the sibling scripts/platformkit/eval_gate/cpcv_distribution.py (59 lines) importing cpcv_engine
  read-only, leaving cpcv_engine.py byte-identical (SHA-256 e9fe694a721658a067bd452911b7f95627897ba4d6c6dccd86c
  c080f9fa6935c verified in the S268 memo). This row is the SAME pattern for tail metrics instead of a
  distributional forecast.
PREMISE (step 0): confirm cpcv_engine.py and walkforward.py are still byte-identical to the S268 memo's recorded
  hashes (engine e9fe694a...6935c; walkforward 9b5f87b0bbd4e0255489fc40f069f092439592f3c35a7b3037dd210648a1baeb);
  confirm S272's archived paired-loss CSV (docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_paired
  _losses.csv, 310,349 data rows, cols record_type/game_id/season/game_date/split_id/n_ticks/loss_candidate_sum/
  loss_incumbent_sum/n_train_games/ts/outcome_home_win/candidate/incumbent/loss_candidate/loss_incumbent) still
  reproduces S272's reported Brier/ECE to 1e-12 with the current unmodified scorers.
CHANGE (step 1): additive sibling scripts/platformkit/eval_gate/cpcv_tail_metrics.py (<=300 LOC), importing
  cpcv_evaluate/walk_forward read-only, adding log_loss, tail_log_loss and a per-bin reliability table beside
  the existing p_model/p_close/y/split_id/n_train record fields (new keys only, none renamed or removed). Seal
  a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Print RSS before/after; a scorer above 500 MB runs via ~/bin/pod_run <aN> --fetch <outputs> --
  <command>. Never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = replay of S272's archived paired-loss CSV through the new sibling: Brier and ECE recomputed
                  vs S272's reported 0.073354/0.073317 (all-ticks) and 0.001245/0.001493 (tail ECE) values
  before        = S268 precedent: sibling route matched cpcv_evaluate to 1e-9 on the fixture and 0.0 delta on
                  777 clusters/3,000 rows; no tail_log_loss field exists anywhere in the repo today
  bar           = Brier/ECE unchanged to <= 1e-12 on the replay; log_loss and tail_log_loss computed and printed
                  for the same rows; engine and walkforward SHA-256 identical to the hashes above
  n             = 310,349 archived CSV data rows / 1,593 games (>= 30)
  eye check     = n/a (S-row); reproduction = verifier reruns the replay script and diffs Brier/ECE to 1e-12
  must not move = cpcv_engine.py, walkforward.py (byte-identical, hashes printed); S272's summary JSON and CSV;
                  the +0.004 bar; nothing charged
NON-TAUTOLOGY: the replay uses every one of the 310,349 archived data rows, not a favorable subset; a log_loss that
  cannot be computed on a zero-probability row is named and excluded by count, not silently dropped.
EVIDENCE: docs/evidence/harness/S293_tail_metric_rail_2026-09-04.md + summary JSON + the replay script itself.
TEST: one per-file test replaying one archived game's rows and asserting log_loss/tail_log_loss are finite.
REPORT: replay deltas, new-field sample, both SHA-256 identities, test line, SHA. No push. NEVER PARK.
