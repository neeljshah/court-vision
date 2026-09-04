GAP S292 | sport nba (props) | worktree aXX | log cx_s292_prop_exceedance_tails
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: three named inputs verified. data/cache/prop_calibration_history.parquet: 4942 rows, cols player_id,
  stat, n, mean_pred, mean_actual, bias, mae, rmse, n_interval, interval_coverage, interval_nominal (7 stats:
  ast/blk/fg3m/pts/reb/stl/tov; row 0 player_id 2544/stat ast) -- PLAYER-STAT AGGREGATES, no per-game rows.
  data/cache/props_eval_nba_calibration.json: keys as_of/mode/note/overall/per_stat/settle_logic_version;
  overall={brier:0.23778, bss:0.0267, ece:0.06566, n:356678}, mode nba_oof_walk_forward, per_stat has the same
  7 stat keys -- also aggregate only. data/cache/prop_sigma_scale.json: scale_factors per stat (e.g. pts 1.0478),
  target_coverage_pct 68.27, min_n 200, window 15 -- a rolling scale, not archived per-game residuals.
PREMISE (step 0, PREMISE-FIRST -- feasibility table is the deliverable): the only per-bet-record NBA archive is
  data/frontend/prop_history_corpus.jsonl (3000 rows, cols sport/market_type/status/model_prob/market_prob/
  prop_side/outcome/line/realized_stat/prop_player/prop_stat/ts/bet_id/...): market_prob is null on all 3000
  rows (no market comparison possible); only 15 unique prop_player ids, 619 unique (prop_player, ts) player-game
  pairs; model_prob tail bins <=0.05: 21 rows, >=0.90: 20 rows (both below n=30). No column carries a q90/q10/
  q05/q95 quantile prediction anywhere in the four files.
CHANGE (step 1): additive module scripts/platformkit/eval_gate/s292_prop_exceedance_feasibility.py (<=300 LOC)
  reproducing every count above and labeling P(actual>=q90)/P(actual<=q10)/q05-q95-coverage exceedance
  calibration TESTABLE or NOT_TESTABLE_TODAY per its exact blocking fact (aggregate-only file, or thin/no-market
  per-bet file). Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal
  line via git show :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF
  to LF, hashes above the seal line). Print RSS before/after; a scorer above 500 MB runs via ~/bin/pod_run <aN>
  --fetch <outputs> -- <command> (not triggered on this CONSTRUCT-only row). Never write data/ or docs/research/;
  never rewrite an existing artifact (new dated filenames; legacy fields as aliases).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the measured feasibility table: per input file, rows, granularity (aggregate vs per-bet),
                  market_prob availability, tail-bin counts where applicable, TESTABLE/NOT_TESTABLE_TODAY label
  before        = no prior row measured whether exceedance-tail calibration is computable from these 4 files
  bar           = all 4 inputs carry a label and blocking fact or passing counts; a count that fails to
                  reproduce is FALSIFIED and closes the row honestly
  n             = 4 (CONSTRUCT: all four input files enumerated exhaustively, not sampled)
  eye check     = n/a (S-row); reproduction = verifier reruns the module and diffs every printed count and label
  must not move = the 4 named files (byte-identical, untouched); the +0.004 bar (named for continuity, unused);
                  nothing charged
NON-TAUTOLOGY: the 21/20-row tail bins and the all-null market_prob column are reported as blocking facts, never
  silently omitted to make the corpus look sufficient.
EVIDENCE: docs/evidence/harness/S292_prop_exceedance_tails_2026-09-04.md + summary JSON with all 4 file rows.
TEST: one per-file test (CONSTRUCT) asserting the printed counts equal the archived file counts.
REPORT: the 4-file table, blocking facts, test line, SHA. No push. NEVER PARK.
