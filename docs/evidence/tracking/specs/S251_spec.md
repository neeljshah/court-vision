GAP S251 | sport all (ops) | worktree a18 | log cx_s251_foundry_runner_heartbeat_check
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: POD_BATCH_2026-09-04_pass3.md: the foundry runner died silently for 41 min 52 s (2026-09-04T00:51:15Z to
  2026-09-04T01:33:07Z) and this was found only by an ad hoc ssh probe in pass 3, not by any routine local check.
PREMISE (step 0): re-measure and print: pass-3 observable outage window 2026-09-04T00:51:15Z..2026-09-04T01:33:07Z
  (41 min 52 s), old log bytes 6,835,769, no traceback/quota/OSError marker found in it; the runner already writes
  data/ab_reports/foundry_runner.heartbeat.json on the pod (confirmed advanced to 2026-09-04T01:37:32Z after
  relaunch: pass completed 48 screens in 134.693 s, idle=false, 12 promotions held, 0 charged); no local, routine
  (non-ssh) check of this heartbeat's age exists anywhere in the harness or pipeline loop today. If falsified,
  STOP, write the memo, commit, report FALSIFIED.
LIMIT (step 1): grep every POD_BATCH_*.md memo for a quoted heartbeat timestamp field. If none ever quoted one, a
  local check can only read what a future pass report records, never a live pod value -- report CLOSED AT LIMIT
  for a truly ssh-free LIVE check; the historical-parse module in Step 2 still proceeds either way.
CHANGE (step 2): smallest additive change -- one new local module scripts/platformkit/ops/heartbeat_age_check.py
  that parses a heartbeat ISO timestamp out of a given docs/evidence/harness/POD_BATCH_*.md memo's text (read-only
  local file parse, no ssh call added), computes age at check time against a fixed staleness threshold, and
  appends exactly one alert line to a local pipeline.log when stale, none when fresh. Rails: additive only,
  nothing renamed; helper <= 300 lines (test_loc_rail_scope.py); never write data/ (never data/registry/); no
  flag on; no edits under src/ kernel/ api/ intel/ scripts/team_system/; no ssh call in the new module; register
  and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = computed heartbeat age (seconds) at check time from a parsed memo timestamp, vs a hand-computed
                  age from the same timestamp; denominator = memo files scanned for a heartbeat field
  before        = the 41 min 52 s outage was discovered only via an ad hoc ssh probe; no local artifact recorded
                  heartbeat age before that probe
  bar           = the module parses the pass-3 heartbeat timestamp 2026-09-04T01:37:32Z from
                  POD_BATCH_2026-09-04_pass3.md and computes an age matching a hand check to within 1 second; a
                  synthetic stale fixture (age > threshold) writes exactly one alert line to pipeline.log; a
                  synthetic fresh fixture writes none
  n             = 2 (CONSTRUCT: stale fixture, fresh fixture)
  eye check     = n/a (S-row); reproduction = the verifier re-parses the same memo and pipeline.log and recomputes
                  the age and alert count independently
  must not move = the POD_BATCH_*.md memo files byte-identical (read-only); no ssh call anywhere in the new
                  module; no flag on
NON-TAUTOLOGY: state which memo timestamp was used and that it is a historical record, not a live pod read; a
  routine local check cannot detect a NEW outage until the next pass report is written, and the memo says so.
EVIDENCE: docs/evidence/harness/S251_foundry_runner_heartbeat_check_2026-09-04.md -- parsed age, fixture outputs,
  pipeline.log delta, a NOT VERIFIED list, summary JSON.
TEST: scripts/platformkit/ops/test_s251_heartbeat_age_check.py -- one new per-file test; run only that file.
REPORT: parsed age, fixture results, pipeline.log lines, test line, SHA. Commit by pathspec, no push. NEVER PARK.
