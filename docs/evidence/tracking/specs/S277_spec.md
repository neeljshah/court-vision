GAP S277 | sport nba (in-game) | worktree a15 | log cx_s277_ingame_market_staleness
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: hypothesis (S213 latency memo): recal_null's conditional Brier improvement over raw market_prob
  concentrates on ticks where the venue price is STALE relative to the state feed. Verified via a one-column
  parquet read of data/cache/inplay_odds/nba_checkpoints_full.parquet (465,249 ticks/1,593 games): columns are
  game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin, market_prob, traded,
  market_ticker, outcome_home_win, venue (all 465,249 rows venue="polymarket"). `state_age_s` and `event_key`
  are NOT FOUND on this store (S213 confirms no sport but MLB has a receipt clock `captured_at` at all). Per this
  row's fallback rule, price staleness = seconds since market_prob last moved, per game_id ordered by ts.
  recal_null itself is `s94_nba_early_shrinkage._recal`, applied unmodified via
  `scripts/platformkit/foundry/ingame_incumbent_nba.apply_incumbent(rows,"recal_null")`.
PREMISE (step 0, INFORMATIONAL): reprint the verified column list and the two NOT FOUND fields above; compute
  seconds-since-last-market_prob-change for every tick after each game's first tick (first tick per game_id has
  no prior move and is excluded, its count printed by name); print n ticks in scope, p50, p90 of that
  distribution, and the resulting fresh (<= p50) / stale (> p90) tick and game-cluster counts.
CHANGE (step 1): additive stratification only, no new fit: apply the unmodified recal_null and market_prob
  columns to the frozen full 465,249-tick grid; score recal_null vs market_prob Brier improvement in the fresh
  bin, the stale bin, and pooled, each through scripts/platformkit/eval_gate/cpcv_engine.cpcv_evaluate with
  purge and a symmetric nonzero embargo and a game-clustered 95 pct CI; report the interaction (stale-bin
  improvement minus fresh-bin improvement) with its own CI. Never touches S224/S272 artifacts (new dated
  filenames only); never flips a flag; the first-tick exclusion is reported, not silently dropped elsewhere.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = recal_null minus market_prob Brier improvement, fresh bin / stale bin / pooled, game-clustered
                  95 pct CI, plus the stale-minus-fresh interaction with CI
  before        = recal_null Brier equals market Brier by construction nowhere on this archive; no staleness
                  stratification of recal_null has ever been scored (S224 stratified by market_prob level only)
  bar           = the frozen +0.004 bar on the STALE-bin improvement; NULL (stale improvement below +0.004, or
                  an interaction CI crossing zero) is a success and is reported as such
  n             = >= 30 game clusters in each of the fresh and stale bins, printed separately
  eye check     = n/a (S-row); reproduction = verifier reruns apply_incumbent and the stratified scorer and
                  diffs every number
  must not move = nba_checkpoints_full.parquet, S224's and S272's summary/per_bin artifacts, s94's _recal
                  definition, the +0.004 bar; backtest_fwer.jsonl untouched, K unread, nothing charged
NON-TAUTOLOGY: the fresh/stale boundary is fixed at the archive's own p50/p90 before any bin is scored; a
  candidate refitting that boundary to maximize the stale-bin delta is circular and self-rejected. Every one of
  the 465,249 ticks is assigned to a bin or a named first-tick exclusion; no bin drops a worsening tick.
EVIDENCE: docs/evidence/harness/S277_ingame_market_staleness_2026-09-04.md + summary JSON + paired-loss CSV.
TEST: one per-file test recomputing staleness on a small fixture (a known move pattern, a first-tick exclusion,
  a tie) and reproducing one bin's Brier improvement from the archived CSV.
REPORT: fresh/stale/pooled table, interaction CI, RSS, test line, SHA. No push. NEVER PARK.
