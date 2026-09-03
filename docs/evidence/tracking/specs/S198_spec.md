GAP S198 | sport nba | worktree a14 | log cx_s198_bridge_test_red
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: on master scripts/platformkit/ingame/test_inplay_capture_bridge.py::test_bridge_enables_ingame_bet FAILS:
`assert hb["n_pairs"] == 1 and hb["n_bets"] == 1` sees n_bets 0 (measured 2026-09-04 14:35 on a clean tree). The
S186 landing was refused by this red test although S186 does not touch the bridge. Candidate breakers = the
2026-09-04 ingame landings: S184 3b837296a (24-hour construct), S177 e9a2af412 (six-file diff), S168 3319c16cf
(event_key strip), S170 eef6295cb, S166 787e38bb7, S158 15a1ad26e (git log -- scripts/platformkit/ingame/).
PREMISE (step 0): run ONLY this test file at HEAD (must fail as stated) and at 15a1ad26e^ (state pass/fail).
Then `git bisect start HEAD 15a1ad26e^`, running only this test file at each step; name the FIRST BAD COMMIT and the
exact diff hunk that flips the outcome. Finish the bisect with `git bisect reset` before any edit.
LIMIT (step 1): if the test encodes the OLD, WRONG behaviour and the breaker corrected a real defect, say so with
the evidence and propose the exact test change -- never silently weaken or delete an assertion.
CHANGE (step 2): the smallest additive fix that makes the test pass WITHOUT reverting the breaker's verified
behaviour; any touched module stays within its count in tests/platformkit/test_loc_rail_scope.py (a new helper
module <= 300 lines is allowed; the allowlist file itself must not change).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = failing tests in scripts/platformkit/ingame/test_inplay_capture_bridge.py
  before        = 1 failing at HEAD (n tests in the file stated)
  bar           = 0 failing; the first bad commit named with the flipping hunk; the breaker's own test file still
                  passes; tests/platformkit/test_loc_rail_scope.py passes; no assertion weakened or skipped
                  without the LIMIT evidence
  n             = commits bisected (CONSTRUCT; list them)
  eye check     = n/a (S-row); reproduction = the verifier re-runs the three test files at the candidate sha
  must not move = the S184 / S177 verified behaviour, every threshold, the FWER ledger
NON-TAUTOLOGY: deleting, skipping or loosening the failing assertion is a REJECT unless step 1 evidence is shown.
EVIDENCE: docs/evidence/harness/S198_bridge_test_red_2026-09-04.md with the bisect log and the before/after runs.
ASCII only. Calibration language only.
TEST: the bridge test file, the breaker's test file, tests/platformkit/test_loc_rail_scope.py -- one at a time.
REPORT: first bad commit, fix diff stat, the three test lines, SHA. Commit by pathspec, no push. NEVER PARK.
