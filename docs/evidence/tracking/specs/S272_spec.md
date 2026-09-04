GAP S272 | sport nba (in-game) | worktree a16 | log cx_s272_ingame_tail_recal_screen
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: successor to S224 (CLOSED AT LIMIT, all 20 frozen 1 pct tail bins UNDERPOWERED individually). Verified
  from S224's memo: low-tail bin 00-01 has 118,601 ticks, realized rate 0.000228 (market Brier 0.000227); the
  worst (highest-MDE) low-tail bin is 09-10, 1,574 ticks, realized 0.107370, MDE 0.133559; the pooled low tail is
  136,809 ticks/775 clusters and the mirror high tail 171,947 ticks/963 clusters (308,756/1,590 together, 0
  dropped) -- S224 scored each 1 pct bin alone and never pooled the tails, so pooled tail power is unmeasured and
  this row is not a repeat of S224's construct.
PREMISE (step 0, INFORMATIONAL): reproduce S224's denominators from nba_checkpoints_full.parquet (465,249 ticks/
  1,593 games): low tail 136,809/775, high tail 171,947/963, MIDDLE 156,493, 0 ticks dropped.
CHANGE (step 1): additive tail-only recalibration arm: isotonic or beta calibration fit walk-forward PER SEASON
  (train on one season's tail ticks, score the other, game-first-date purge) using only ticks in the low or high
  tail bands (market_prob <= 0.10 or >= 0.90); scored against the S123 recal_null incumbent both on tail-ticks-
  only and on all 465,249 ticks, through scripts/platformkit/eval_gate/walkforward.py or cpcv_engine.py with
  purge and a symmetric nonzero embargo. Reports tail ECE and tick-weighted Brier with a game-clustered 95 pct CI
  for both denominators. Never touches S224's or S123's artifacts (new dated filenames only); never flips a flag.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = tick-weighted Brier (all-ticks and tail-ticks-only) and tail ECE, tail-recal candidate vs
                  recal_null incumbent, game-clustered 95 pct CI, >= 30 game clusters on both denominators
  before        = S224: recal_null Brier equals market Brier by construction on every tail bin (no recalibration
                  has ever been fit); S123 recal_null all-ticks Brier 0.144293 (79,554-tick archive) is the
                  standing incumbent reference
  bar           = the frozen +0.004 bar on the ALL-TICKS Brier; tail ECE reported beside it with its own CI; a
                  BEHIND all-ticks result with improved tail ECE is reported as a trade-off, never as a win
  n             = >= 30 game clusters on both the all-ticks and tail-ticks-only denominators, printed separately
  eye check     = n/a (S-row); reproduction = verifier reruns the calibrator and both scorers and diffs every
                  number
  must not move = S224's summary.json/per_bin.csv, S123's ingame_incumbent_nba.py market default, the frozen 20
                  bin edges, the +0.004 bar; backtest_fwer.jsonl untouched, K unread, nothing charged
NON-TAUTOLOGY: the all-ticks Brier is scored over every one of the 465,249 ticks, never only the tail; the tail
  band stays fixed at market_prob <= 0.10 / >= 0.90 -- a candidate that improves tail ECE by refitting that
  boundary is rejected as circular.
EVIDENCE: docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04.md + summary JSON + paired-loss CSV.
TEST: one per-file test recomputing one season-fold's tail ECE and all-ticks Brier from the archived paired-loss
  CSV, under 200 MB.
REPORT: tail vs all-ticks table, CI, trade-off framing, RSS, test line, SHA. No push. NEVER PARK.
