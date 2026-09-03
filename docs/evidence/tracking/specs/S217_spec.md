GAP S217 | sport mlb (in-game) | worktree aXX | log cx_s217_mlb_depth_capture_pod
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S100 closed order-book microstructure with "premise falsified: depth captured pre-game only".
PREMISE (step 0): re-measure and print: book_depth/kalshi file count; depth_history/mlb file count and date span (15
  files, 2026-07-05..2026-09-02 as measured 2026-09-04); the three constants above at HEAD; and the S105 achieved pod
  cadence while live, median 30.0 s / p90 64.8 s against TARGET_CADENCE_SEC 5.0. If falsified, STOP, FALSIFIED.
LIMIT (step 1): measure the cost of ONE full ladder pass over the live MLB tickers at the venue's documented 5-10 s
  guidance. S105 measured the pass itself at about 30 s, so the achievable floor may be well above 10 s. Report the
  measured floor and, if it exceeds 15 s, report CLOSED AT LIMIT at that number -- never poll faster than the venue
  guidance to meet a bar, and never raise max_markets to force it.
CHANGE (step 2): smallest additive change -- one new pod capture script under scripts/platformkit/ingame/ reusing
  ingame_book_depth_kalshi.snapshot_market and the existing 429 backoff; append-only JSONL keyed (date, ticker, ts) so
  a restart never duplicates and never loses a window; stops by READING a stop-flag file, never by a kill; own nohup
  setsid nice job, unique /tmp log, no git on the pod. Report the files you would deploy and deploy nothing (B5).
  Rails: additive only, nothing renamed; helper <= 300 lines (LOC rail test_loc_rail_scope.py); never write data/
  (never data/registry/); no flag on; no edits under src/ kernel/ api/ intel/ scripts/team_system/; one store at a
  time via metadata or one row group, never > 300 MB (the box RAM guard kills python over 800 MB); register and ledger
  untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = achieved inter-pass cadence p50 / p90 / max while at least one MLB game is live, per game, with per-
                  level ladders present; plus the duplicate count over (date, ticker, ts) after restart; denominator =
                  every pass the run recorded, idle passes labelled and counted separately
  before        = one pass per 300 s from the local hook, and 0 files under book_depth/kalshi (measured 2026-09-04);
                  pod achieved median 30.0 s / p90 64.8 s against a 5.0 s target (S105)
  bar           = one full live slate captured end to end with achieved cadence printed per game; 0 duplicate (date,
                  ticker, ts) rows and 0 lost windows across 3 enumerated restart cases; 0 un-backed-off 429
                  responses. A measured floor above 15 s reported as CLOSED AT LIMIT is a valid result
  n             = 3 (CONSTRUCT) for the restart cases -- clean stop, SIGTERM mid-pass, process kill mid-write -- plus
                  the printed live-game and pass counts of the captured slate
  eye check     = n/a (S-row); reproduction = the verifier recomputes the cadence quantiles and the duplicate count
                  from the archived capture JSONL alone
  must not move = DEPTH_CAPTURE_EVERY_N_TICKS 15, LIVE_INTERVAL_SEC 20.0, TARGET_CADENCE_SEC 5.0, MAX_CADENCE_SEC 60.0
                  and max_markets_per_sport; ingame_book_depth_retention eviction order; the supervisor manifest (no
                  autostart, no flag flip); backtest_fwer.jsonl untouched, K unread
NON-TAUTOLOGY: count idle passes and error passes in the denominator with their reasons.
EVIDENCE: docs/evidence/harness/S217_mlb_depth_capture_pod_2026-09-04.md -- the per-game cadence table, the restart
  construct table, the 429 tally, a NOT VERIFIED list, summary JSON and the capture JSONL sample (Q9).
TEST: scripts/platformkit/ingame/test_s217_mlb_depth_capture.py -- one new per-file test; run only that file.
REPORT: achieved cadence, the restart construct result, the measured floor and its verdict, the files you would
  deploy, test line, SHA. Commit by pathspec, no push. NEVER PARK.
