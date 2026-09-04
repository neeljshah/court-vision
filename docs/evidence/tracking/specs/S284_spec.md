GAP S284 | sport nba (in-game) | worktree a16 | log cx_s284_orderflow_traded
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: Whelan et al., "Makers and Takers: The Economics of the Kalshi Prediction Market" (Kalshi is
  quote-driven; order flow carries information), and Angelini & De Angelis, "When Do Markets Fully Process
  Public Information? Evidence from Real-Time Prediction Markets," arXiv 2606.07811 (2026, Kalshi NBA event
  contracts + play-by-play), motivate trade OCCURRENCE as a live informativeness signal. Verified this session:
  nba_checkpoints_full.parquet's own `traded` column is DEGENERATE (465,249/465,249 True). Its sibling
  data/cache/inplay_odds/nba_price_series.parquet carries a REAL `traded` flag on 657,145 Kalshi rows (56.33
  pct True) but is NULL on all 7,742,487 Polymarket rows. Kalshi `event_key` (e.g. KXNBAGAME-26APR26BOSPHI)
  shares 0 raw keys with checkpoints' `game_id` (401704627) or `market_ticker` (nba-nyk-bos-2024-10-22) --
  S280's own finding, reproduced here.
PREMISE (step 0, INFORMATIONAL): parse team-pair + date from `market_ticker` (away3-home3-date) and Kalshi
  `event_key` (yy+mon+dd+6-letter pair); print the date-offset distribution and, for each of the away-home /
  home-away orderings, the resulting game-cluster overlap count with checkpoints; report the best ordering
  plainly, 0 silently discarded.
CHANGE (step 1): if the best ordering clears 30 clusters, asof-join (strictly prior, tolerance printed) each
  Kalshi tick's `traded` flag and a rolling trade-count-in-last-60s onto the nearest checkpoint tick per game;
  score scripts/platformkit/foundry/ingame_incumbent_nba.apply_incumbent's recal_null plus these features via
  cpcv_engine.cpcv_evaluate, purge + symmetric nonzero embargo, on the joined subset only. Below 30 clusters,
  STOP at PREMISE and report CLOSED AT LIMIT naming the acquisition (a Kalshi-native id capture) needed.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = recal_null-plus-orderflow minus recal_null Brier improvement, game-clustered 95 pct CI,
                  scored only on the joined subset
  before        = no arm has used a non-degenerate traded flag; checkpoints' own column is verified constant
  bar           = the frozen +0.004 bar; CLOSED AT LIMIT below 30 clusters is the expected valid result
  n             = >= 30 game clusters required to score
  eye check     = n/a (S-row); reproduction = verifier reruns the parse-join and diffs the overlap count
  must not move = nba_checkpoints_full.parquet, nba_price_series.parquet, the +0.004 bar; nothing charged if
                  CLOSED AT LIMIT
NON-TAUTOLOGY: both orderings are tried and both counts reported before either is scored; picking the better
  ordering is disclosed as a join-quality choice, not a fit -- no Brier computed before the count is fixed.
EVIDENCE: docs/evidence/harness/S284_orderflow_traded_2026-09-04.md + parse-join census CSV + (if scored)
  summary JSON and paired-loss CSV.
TEST: one per-file test parsing synthetic ticker/event_key pairs (one per ordering, one non-matching) and
  reproducing the overlap count; if scored, also reproduce one game's Brier from the archived CSV.
REPORT: ordering census table, cluster count, verdict, RSS, test line, SHA. No push. NEVER PARK.
