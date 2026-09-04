GAP S290 | sport all (pregame) | worktree aXX | log cx_s290_pregame_longshot_close_recal
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: data/cache/inplay_odds/{nba,mlb,soccer,tennis}_price_series.parquet are full tick histories (cols
  sport, venue, game_date, ticker_or_slug, event_key, market_type, side, ts, prob, traded, close_time,
  result_where_known; market_type is moneyline-only; rows nba 8,399,632 / mlb 13,473,591 / soccer 204,435 /
  tennis 1,854,100) with NO game-clock field, so a pregame-vs-in-game boundary cannot be derived from them
  (verified on one nba event_key: ticks run past close_time into settlement). The real pregame-close archives
  are data/cache/combo/gate_corpus_{nba,mlb}_close.parquet (p_close column, close_kind); soccer/tennis have only
  gate_corpus_{soccer,tennis}.parquet with p_base, a MODEL baseline (Poisson/Elo per S02/S03), not a market close.
PREMISE (step 0, PREMISE-FIRST -- this row's deliverable is the table below, not a scored recalibration):
  gate_corpus_nba_close.parquet: 1,814 rows; p_close 563/1,814; tails <=0.15: 25 and >=0.85: 60 (n=85,
  min 0.055/max 0.945).
  gate_corpus_mlb_close.parquet: 39,162 rows; p_close non-null 910; tails <=0.15: 1 and >=0.85: 1 (n=2,
  min 0.01/max 0.99).
  gate_corpus_soccer.parquet 25834 rows (event_id e.g. 20150807-E1-brighton-nott_m_forest) and
  gate_corpus_tennis.parquet 41886 rows (event_id e.g. 20150104-atp-2015-339-105357-105733-1) carry no p_close.
CHANGE (step 1): additive module scripts/platformkit/eval_gate/s290_pregame_longshot_feasibility.py (<=300 LOC)
  that reproduces the four counts above per sport and labels each TESTABLE (p_close column present AND pooled
  tail n >= 30) or NOT_TESTABLE_TODAY with the blocking fact named (null-heavy p_close, or no market-close column
  -- p_base is never substituted for a close). Never write data/ or docs/research/; never rewrite an existing
  artifact (new dated filenames; legacy fields as aliases). No walk-forward isotonic fit runs in this row; a
  TESTABLE sport is queued as its own follow-up row, not attempted here. Seal a prereg FIRST as its own commit
  (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show :<path>, verified with git show
  HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above the seal line). Print RSS
  before/after; a scorer above 500 MB runs via ~/bin/pod_run <aN> --fetch <outputs> -- <command> (not triggered
  on this CONSTRUCT-only row).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the measured feasibility table: per sport, rows, p_close non-null count/pct, pooled tail n at
                  <=0.15 and >=0.85, and the TESTABLE / NOT_TESTABLE_TODAY label with its blocking fact
  before        = no prior row measured p_close coverage or tail density for any of the four sports
  bar           = every one of the 4 sports carries a label and its exact blocking fact or its passing counts;
                  a FALSIFIED premise (a count that does not reproduce) is a valid result and closes the row
  n             = 4 (CONSTRUCT: all four sports enumerated exhaustively, not sampled)
  eye check     = n/a (S-row); reproduction = verifier reruns the module and diffs every printed count and label
  must not move = gate_corpus_*.parquet and gate_corpus_*_close.parquet files (byte-identical, untouched); the
                  +0.004 bar (unused here, named for continuity); nothing charged
NON-TAUTOLOGY: MLB's thin tail and soccer/tennis's missing p_close are reported as NOT_TESTABLE_TODAY, never
  silently dropped from the table to make three sports look ready.
EVIDENCE: docs/evidence/harness/S290_pregame_longshot_close_recal_2026-09-04.md + summary JSON with all 4 rows.
TEST: one per-file CONSTRUCT test of all 4 counts; report table, blockers, test, SHA. No push. NEVER PARK.
