GAP S221 | sport all (harness) | worktree aXX | log cx_s221_pod_multirunner_probe
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: the program wants the pod pushed hard, and the measured ceiling is one runner: S16_pod_hour section 4 records
  3,780 T1 screens in one pod hour against a bar of 200, QUEUE-BOUND, with a sustained 9,331.5 screens/hour while
  claimable work existed; S102 records the in-game tier at 3,266.7 screens/hour (mean 1.07 s, median 0.93 s).
PREMISE (step 0): re-measure and print at HEAD: results_db LEASE_SECONDS and the presence and signature of renew(),
  the claimer identity form, and the reap_expired scoping; then reproduce the S135 double-claim probe against the
  CURRENT code in an ISOLATED temporary sqlite database (never the pod DB, never the repo cache). If the probe shows
  the pre-S135 behaviour, STOP and report FALSIFIED.
LIMIT (step 1): if the probe still double-claims at any tested horizon, report the defect with its line numbers and
  STOP. Do not launch, propose launching, or deploy a second runner.
CHANGE (step 2): smallest additive change -- one new probe script under scripts/platformkit/eval_gate/ that builds an
  isolated temp DB, runs the enumerated cases, and prints the table; plus a REPORTED (not executed) two-runner launch
  recipe naming the sport binding, the seed-with-runner-paused rule from S110, and the stop-flag path. No pod contact,
  no deploy (B5). Rails: additive only, nothing renamed; helper <= 300 lines (LOC rail test_loc_rail_scope.py); never
  write data/ (never data/registry/); no flag on; no edits under src/ kernel/ api/ intel/ scripts/team_system/; one
  store at a time via metadata or one row group, never > 300 MB (the box RAM guard kills python over 800 MB); register
  and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per enumerated case, the rows runner B claims that runner A holds unfinished, and the sport-NULL
                  queued rows a sport-bound runner cannot drain; denominator = the full enumerated case grid, printed
  before        = S135 measured runner B claiming all 3 held hypotheses at +901 s, and claim(sport='mlb') 0 vs
                  claim(sport=None) 1 for a sport-NULL row, against the pre-fix code
  bar           = 0 double-claimed rows for runner B at +901 s AND at +1801 s with the heartbeat running, 0 double-
                  claims after a SIGTERM-and-restart of runner A, and 0 sport-NULL queued rows asserted at startup;
                  any non-zero cell is reported as a live defect and the row stops there
  n             = 12 (CONSTRUCT) -- 2 horizons x 3 lifecycle cases (heartbeat running, heartbeat stopped, SIGTERM
                  restart) x 2 sport bindings (bound, unbound); every case enumerated, none sampled
  eye check     = n/a (S-row); reproduction = the verifier re-runs the probe script in a fresh temp DB and reproduces
                  every cell of the case grid
  must not move = LEASE_SECONDS, results_db.py, foundry_runner.py and every queue module byte-identical -- this row
                  probes and changes nothing; the pod is not contacted; backtest_fwer.jsonl untouched, K unread
NON-TAUTOLOGY: report all 12 cases including the ones that pass trivially, and state that the aggregate-rate figure in
  the launch recipe is an ESTIMATE extrapolated from the single-runner 9,331.5 / 3,266.7 screens per hour, not a
  measurement of two runners.
EVIDENCE: docs/evidence/harness/S221_pod_multirunner_probe_2026-09-04.md -- the 12-case grid, the HEAD source reading
  with line numbers, the reported launch recipe, a NOT VERIFIED list and the summary JSON (Q9).
TEST: scripts/platformkit/eval_gate/test_s221_multirunner_probe.py -- one new per-file test; run only that file.
REPORT: the case grid, any live defect, the launch recipe (reported, not executed), test line, SHA. Commit by
  pathspec, no push. NEVER PARK.
