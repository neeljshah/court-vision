GAP S280 | sport nba (in-game) | worktree a13 | log cx_s280_ingame_cross_venue_disagreement
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: census-first, already run by this lane's author and re-verifiable by column read (grep of
  scripts/platformkit + data/frontend for kalshi/polymarket found no cross-venue module; the overlap lives in a
  different store than the scoring archive). `nba_checkpoints_full.parquet` (the 465,249-tick incumbent grid)
  has `venue`="polymarket" on all rows -- single-venue by construction. But
  `data/cache/inplay_odds/nba_price_series.parquet` (8,399,632 rows; sport, venue, game_date, ticker_or_slug,
  event_key, market_type, side, ts, prob, traded, close_time, result_where_known) has BOTH venues: polymarket
  7,742,487 rows/1,773 distinct event_key, kalshi 657,145 rows/62 distinct event_key, kalshi game_date span
  2026-04-27..2026-06-14 (inside the checkpoints' 2024-10-22..2026-06-13). Formats differ (polymarket
  `nba-mia-min-2026-01-06`; kalshi `KXNBAGAME-26APR26LALHOU-HOU` = YYMonDD+away+home+side) so raw-string
  intersection is 0 -- a date+team-pair parse-join is required, not a key match.
PREMISE (step 0, INFORMATIONAL): reprint the venue counts/date ranges above from a one-column parquet read;
  parse each kalshi ticker_or_slug and each polymarket ticker_or_slug/checkpoint market_ticker into a (date,
  away, home) triple; print the first 3 parsed ids on both sides plus the exact columns used; count real
  overlapping games (same date + team pair) between kalshi price-series events and the checkpoints' 1,593 games.
CHANGE (step 1): if overlap is >= 30 game clusters: per overlapping game, compute the venue disagreement (kalshi
  prob minus the checkpoint's fused polymarket market_prob) at matched or nearest-ts ticks, add it as ONE
  additive feature to the S123 recal_null incumbent, scored via
  scripts/platformkit/eval_gate/cpcv_engine.cpcv_evaluate with purge and a symmetric nonzero embargo, restricted
  to overlapping ticks. If overlap is < 30 clusters: CLOSES AT LIMIT, naming the exact parsed overlap count and
  what capture would raise it (tie to S217's depth-capture closure, S250's credential-gated user decision).
  Never touches the archives (new dated filenames only); never flips a flag.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = venue-disagreement-augmented Brier minus recal_null Brier, game-clustered 95 pct CI, on the
                  overlapping-tick subset only
  before        = recal_null Brier on the overlapping subset alone (no cross-venue feature has ever been scored)
  bar           = the frozen +0.004 bar; if overlap < 30 clusters the row CLOSES AT LIMIT instead (a valid
                  success) and no Brier is scored
  n             = >= 30 game clusters if scored, printed; the parse-join enumeration is n = 62 (CONSTRUCT: every
                  kalshi event_key present, exhaustive by construction)
  eye check     = n/a (S-row); reproduction = verifier reruns the parse-join and the scorer and diffs every
                  number, including the overlap count
  must not move = nba_checkpoints_full.parquet, nba_price_series.parquet, S123's market default, the +0.004 bar;
                  backtest_fwer.jsonl untouched, K unread, nothing charged
NON-TAUTOLOGY: the overlap count is the actual parsed intersection, not a superset assumed from date range
  alone; a scored result covers every overlapping tick, never a bar-clearing subset.
EVIDENCE: docs/evidence/harness/S280_ingame_cross_venue_disagreement_2026-09-04.md + JSON + overlap table + CSV.
TEST: one per-file test parsing 3 fixture strings (kalshi, polymarket, non-matching) into (date,away,home).
REPORT: overlap count, scored-or-CLOSED-AT-LIMIT verdict, RSS, test line, SHA. No push. NEVER PARK.
