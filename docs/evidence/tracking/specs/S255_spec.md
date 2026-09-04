GAP S255 | sport nba (in-game) | worktree aXX | log cx_s255_asof_rate_snapshot_producer
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S247 (a13, S247_nba_sim_engine_vs_line_v2_2026-09-04.md) CLOSED AT LIMIT: the predicate
  player_snapshot_date < game_date and team_snapshot_date < game_date returns 0/661 qualifying game clusters
  (79,554 ticks, 2024-10-25..2026-04-06) -- player_rates.parquet (71,906 B) and team_rates.json (378,935 B) are a
  SINGLE undated snapshot (both fs-dated 2026-06-07, after every archive game). S223's census (196aed9e1) found
  the same defect pool-wide: atlas 4/55/0 AS-OF SAFE/SNAPSHOT-ONLY/UNDATED (59), intelligence 45/0/54 (99), 158/158.
PREMISE (step 0): re-measure and print: player_rates.parquet and team_rates.json each carry 0 as-of/date columns
  and a single fs mtime (2026-06-07), postdating all 661 _all-archive clusters. If falsified, STOP, write memo,
  commit, report FALSIFIED.
LIMIT (step 1): name the box-score / play-by-play corpora already on disk with a per-row game_date (S223's dated
  data/intelligence/ sidecars, e.g. momentum_signals 673,204 rows; the S92 lineup-dynamic archives). Count how
  many of the 661 S247 clusters have enough prior-dated games banked to compute a walk-forward rate snapshot. If
  fewer than 30 would qualify, report CLOSED AT LIMIT and build nothing.
CHANGE (step 2): one new additive module under scripts/platformkit/ingame/ (e.g. asof_rate_snapshot_producer.py)
  plus one per-file test: for each qualifying game date, rebuild player and team rate aggregates using ONLY rows
  with a game_date strictly before that date, writing a dated snapshot table keyed (entity_id, as_of_date). Rails:
  additive only, nothing renamed; helper <= 300 lines (test_loc_rail_scope.py); never write data/ (never
  data/registry/); no flag on; no edits under src/ kernel/ api/ intel/ scripts/team_system/ (existing
  player_rates.parquet / team_rates.json read-only, untouched); one store at a time, <= 300 MB; register and
  ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = fraction of the 661 S247 archive game clusters receiving a qualifying strictly-prior snapshot
                  (player_snapshot_date < game_date and team_snapshot_date < game_date); denominator = 661
  before        = 0/661 (S247); the two existing rate stores carry one undated snapshot each
  bar           = >= 30 of 661 clusters receive a qualifying snapshot so S247 can be re-run; if lower, state the
                  true fraction honestly and report CLOSED AT LIMIT rather than lowering the bar
  n             = qualifying clusters (target >= 30), fixed denominator 661 (CONSTRUCT: exhaustive over the list)
  eye check     = n/a (S-row); reproduction = the verifier recomputes the qualifying-cluster count and re-derives
                  the leakage assertion from the snapshot table and its named inputs alone
  must not move = player_rates.parquet and team_rates.json byte-identical (read-only); the 661-cluster S247 list
                  unchanged; no flag on
NON-TAUTOLOGY: report the qualifying fraction over the full fixed 661-cluster list, never a subset chosen after
  seeing which pass; a planted future row (as_of_date > game_date) must be asserted absent from every snapshot.
EVIDENCE: docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04.md -- qualifying-fraction table, named
  source corpora, leakage-test result, NOT VERIFIED list, summary JSON, snapshot table (docs/evidence/harness/
  S255_asof_rate_snapshot_producer_2026-09-04/, csv/parquet if < 2 MB else sha256+rows).
TEST: scripts/platformkit/ingame/test_s255_asof_rate_snapshot_producer.py -- one new per-file test; run only it.
REPORT: qualifying fraction, source corpora named, leakage-test result, LIMIT verdict, test, SHA. Commit by
  pathspec, no push. NEVER PARK.
