GAP S250 | sport all (pregame) | worktree a16 | log cx_s250_mlb_tennis_prop_close_capture
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S240 census: NBA closing_props/ = 77 files, 48,515 tidy rows, 0/48,515 (0.0 pct) null prices, SCORABLE
  n=77. MLB and tennis prop_history_corpus_*.jsonl = 3,000 rows each, 3,000/3,000 (100.0 pct) null market_prob,
  NOT SCORABLE n=0. Soccer prop_history_corpus_soccer.jsonl = 0 rows.
PREMISE (step 0): re-measure and print, from S240's fresh complete-store census: NBA 77 files SCORABLE (real-price
  source count 77, real-price clusters 77/77); MLB 3,000 rows / 0 real-price rows / 0 real-price clusters (0/777
  date clusters); tennis 3,000 rows / 0 real-price rows / 0 real-price clusters (0/389 date clusters); soccer 0
  rows. Identify the exact odds-API route/module that produced the 77 NBA closing_props/ files (print its file
  path and call site) -- this is the tier S250 must reuse for MLB/tennis. If falsified, STOP, FALSIFIED.
LIMIT (step 1): probe the identified odds-API tier once for one MLB and one tennis market at the venue's
  documented rate-limit guidance. If the tier does not carry MLB or tennis player-prop markets at all (sport not
  offered), report CLOSED AT LIMIT per sport and name the missing sport; do not substitute a different tier.
CHANGE (step 2): smallest additive change -- one new resumable pod-side (or local, per LIMIT finding) capture
  script under scripts/platformkit/ingame/ reusing the same odds-API tier/module identified in Step 0 for MLB and
  tennis player props; append-only JSONL keyed (sport, event_id or ts date, market, ts) so a restart never
  duplicates or loses a snapshot; stops by READING a stop-flag file; own nohup setsid nice job, unique /tmp log,
  no git on the pod; report files you would deploy and deploy nothing (B5). Rails: additive only; helper <= 300
  lines (test_loc_rail_scope.py); never write data/ (never data/registry/); no flag on; no edits under src/
  kernel/ api/ intel/ scripts/team_system/; register and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = captured rows with a concrete finite price, per sport (MLB, tennis), against the same
                  real-price-cluster denominator method S240 used (date or event cluster); a scorability forecast
                  = clusters with >= 1 real price / total clusters attempted, per sport
  before        = MLB 0/777 date clusters real-priced; tennis 0/389 date clusters real-priced (S240)
  bar           = >= 30 real-priced clusters captured for at least one of MLB or tennis, OR a CLOSED AT LIMIT
                  verdict per sport naming why the tier cannot supply it; 0 duplicate (sport,key,ts) rows across
                  3 enumerated restart cases
  n             = 3 (CONSTRUCT) for the restart cases -- clean stop, mid-poll interrupt, process kill mid-write --
                  plus the printed per-sport captured-row and cluster counts
  eye check     = n/a (S-row); reproduction = the verifier recomputes the real-price cluster counts and duplicate
                  count from the archived capture JSONL alone
  must not move = the S240 census artifacts and the 77-file NBA archive byte-identical; the odds-API tier module
                  used for NBA unedited; no flag on
NON-TAUTOLOGY: count zero-price and rate-limited attempts in the denominator with their reasons; do not drop them
  to inflate the real-price rate.
EVIDENCE: docs/evidence/harness/S250_mlb_tennis_prop_close_capture_2026-09-04.md -- per-sport cluster table, the
  restart construct table, a scorability forecast, a NOT VERIFIED list, summary JSON, capture JSONL sample.
TEST: scripts/platformkit/ingame/test_s250_prop_close_capture.py -- one new per-file test; run only it.
REPORT: real-price clusters, restart construct, LIMIT verdicts, test, SHA. Commit by pathspec, no push. NEVER PARK.
