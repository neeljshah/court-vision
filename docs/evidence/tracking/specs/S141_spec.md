GAP S141 | sport nba (data) | worktree a12 | log cx_s141_wallclock_tolerance
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of section B AND section Q before you report. Template: docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md. Calibration language only: no dollar, ROI, profit or edge words. Never touch data/registry, src/, kernel/, api/, intel/, scripts/team_system/. Per-file tests only (python -m pytest <one file> -q); NEVER the full suite. data/ in this worktree is a read-only junction to the main repo's data/ -- never write under data/. NEVER PARK: run everything to completion this turn; never end waiting. COMMIT: explicit pathspec (git add <paths> && git commit -m "..." -- <paths>), in this worktree, no push. Last line of your report: SHA: <sha>.
GAP (verbatim from the register): scripts/platformkit/venue_history/nba_wallclock_join.py:122 performs a backward as-of join of state onto price ticks with NO staleness tolerance (S104 found the same pattern carrying a 2-hour-stale score forward elsewhere).
READ: scripts/platformkit/venue_history/nba_wallclock_join.py (whole file) and every caller (grep -rn nba_wallclock_join scripts tests); scripts/platformkit/eval_gate/asof_join.py (asof_join_state(ticks, states, key, max_staleness_s) -> (merged, stale_share); S104's helper, tested); its test tests/platformkit/eval_gate/test_asof_join.py.
PREMISE (step 0): print the join line(s) and confirm no tolerance; measure on the real inputs the join reads (find them in the junctioned data/) the distribution of state age at join time (p50 / p90 / max seconds, share > 300 s). If a tolerance already exists, STOP and report FALSIFIED.
LIMIT (step 1): n/a.
CHANGE (step 2): route the join through asof_join_state with max_staleness_s = 300 (the S99/S104 rail; expose it as a keyword with that default), record stale_share in the function's returned meta / log line; behaviour identical for rows within tolerance (assert on the real inputs: every merged row with age <= 300 s equal before/after) and nulled beyond it.
TEST: NEW tests/platformkit/venue_history/test_nba_wallclock_join_tolerance.py: a fresh state merges; a stale one (> 300 s) is nulled; the stale_share is reported; the default keyword is 300.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = joins with a staleness tolerance; denominator = 1 (this join)
  before        = 0/1
  bar           = 1/1, existing venue_history tests green, real-input stale share reported
  n             = 1 (CONSTRUCT)
  eye check     = n/a; reproduction = verifier reruns the test + the measurement in master
  must not move = the 300 s rail (a keyword default, not a bar), the ledger (never open), data/registry/**
NON-TAUTOLOGY: the within-tolerance equality is asserted against the PRE-change join output saved before editing.
EVIDENCE: docs/evidence/harness/S141_nba_wallclock_tolerance_2026-09-03.md (premise ages, diff, equality, test output, NOT VERIFIED).
POD: none. Do not ssh anywhere.
