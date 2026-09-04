GAP S213 | sport all (in-game) | worktree a16 | log cx_s213_ingame_latency_ledger
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: INGAME_CAPABILITY_2026-09-01.md, verbatim: "schema_has_venue_ts=false for every sport in
  inplay_tick_latency.json, so no sport carries a real lag_p90 field at all -- nor an src_ts_coverage_pct field", and
  EVENT_REACTIVE is therefore failed closed on both halves.
PREMISE (step 0): re-measure and print: inplay_tick_latency.json carries no lag_p90 and no src_ts_coverage_pct for any
  sport; nba is absent from its SPORTS list entirely; latency_audit.json median_lag_seconds 34.0 with its own caveat
  that 129/135 = 95.6 pct of matched events moved on Kalshi before our tick; gumbo_mlb_poller stamps captured_at
  beside ts; data/domains/mlb/gumbo_live holds 1 file; depth_history/mlb holds 15 files 2026-07-05..2026-09-02. If
  falsified, STOP, write the memo, commit, report FALSIFIED.
LIMIT (step 1): per sport, count the in-play ticks that carry BOTH our receive time and an INDEPENDENT source
  timestamp (GUMBO ts, Kalshi ms trade tape, or a venue field). A sport with 0 such ticks is structurally unmeasurable
  today: report NOT MEASURABLE with the missing field named. Never substitute a proxy timestamp; a proxy would make
  the gate meetable by construction. If 0 sports are measurable, report CLOSED AT LIMIT.
CHANGE (step 2): smallest additive change -- one new read-only module under scripts/platformkit/ingame/ that reads the
  existing stores and emits one table plus a per-tick lag CSV. No capture, no fetch, no new endpoint. Additive only,
  nothing renamed; helper <= 300 lines within tests/platformkit/test_loc_rail_scope.py counts; never write data/
  (never data/registry/); no flag flipped on; no edits under src/ kernel/ api/ intel/ scripts/team_system/; one store
  at a time, never a store over 300 MB and never a whole parquet -- use ParquetFile(path).metadata or a single row
  group (the box RAM guard kills any python over 800 MB); never touch the register or the ledger.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per sport: n in-play ticks carrying both timestamps, lag = captured_at - source_ts with p50 / p90 /
                  max in seconds, and coverage pct; denominator = that sport's printed in-play tick count
  before        = no lag_p90 exists for any sport (INGAME_CAPABILITY_2026-09-01.md); latency_audit.json's 34.0 s
                  median is cross-venue, not venue-truth-to-feature, and is the only adjacent number on record
  bar           = 5 of 5 sports (nba, wnba, mlb, soccer, tennis) reported with EITHER a measured lag distribution over
                  >= 30 game clusters OR an explicit NOT MEASURABLE reason naming the absent field; 0 sports proxied;
                  the frozen EVENT_REACTIVE gates re-printed unchanged and applied as written
  n             = game clusters per sport (>= 30 wherever measurable); print tick and cluster counts per sport
  eye check     = n/a (S-row); reproduction = the verifier recomputes every p50 / p90 from the archived per-tick lag
                  CSV alone, without re-reading any source store
  must not move = latency_scoreboard.py constants (EVENT_REACTIVE_LAG_P90_SEC 5.0, EVENT_REACTIVE_COVERAGE_PCT 95.0,
                  SLOW_STATE_TICK_P90_SEC 120.0); inplay_tick_latency.json and capability_matrix outputs byte-
                  identical; backtest_fwer.jsonl untouched, K unread; nothing charged
NON-TAUTOLOGY: enumerate all five sports including those with zero measurable ticks.
EVIDENCE: docs/evidence/harness/S213_ingame_latency_ledger_2026-09-04.md -- the per-sport table, the NOT MEASURABLE
  reasons, the re-printed gates, a NOT VERIFIED list, summary JSON and the per-tick lag CSV (Q9).
TEST: scripts/platformkit/ingame/test_s213_latency_ledger.py -- one new per-file test; run only that file.
REPORT: the per-sport table, which sports are NOT MEASURABLE and why, test line, SHA. Commit by pathspec, no push.
  NEVER PARK.
