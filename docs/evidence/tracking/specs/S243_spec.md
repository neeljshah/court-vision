GAP S243 | sport nba (pregame) | worktree aXX | log cx_s243_boxscore_coherence_check
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: distributions must stay coherent: roster minutes cannot exceed 240 (5x48) plus OT, and
summed player pts/reb/ast should track the team-level totals. scripts/platformkit/
boxscore_crosscheck.py + tests/platformkit/test_boxscore_crosscheck.py already exist, unread this
session -- this row may be mostly wiring, not a new check.
PREMISE (step 0): read boxscore_crosscheck.py in full (skeleton then functions); report exactly
what it checks today (point totals only, or already distributional) and whether it consumes S241/
S242 output or only point predictions.
LIMIT (step 1): if it already does the full coherence check (minutes-sum-to-240+OT AND stat-sum-to-
team, at distribution level), report FALSIFIED -- already built -- and stop; do not duplicate it.
CHANGE (step 2): only if LIMIT falsifies the premise -- additive only, extend its own test file with
new cases, or add scripts/platformkit/boxscore_dist_coherence.py if it is point-only, that: (a)
sums S241's top-5-minutes players' q50 minutes and flags > 240 + 5*OT periods; (b) sums S242's q50
pts/reb/ast across the roster vs the team-level total from matchup_grid.parquet or the game
engine's own output, reporting absolute and pct deviation.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or
ledger; no edits under src/ kernel/ api/ intel/ scripts/team_system/ or token-gated eval_gate
modules; new helpers <= 300 lines.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = boxscore_crosscheck.py's current check inventory; if extended, minutes-sum and
      stat-sum deviation per game
  before        = boxscore_crosscheck.py exists but its coverage against a DISTRIBUTIONAL box score
      has never been reported
  bar           = the inventory printed in full with file:line citations; if extended, minutes-sum
      deviation reported for every sampled game (0 silently excluded), mean abs pct deviation for
      team stat sums stated with its n
  n             = >= 30 games (CONSTRUCT for the check inventory; sampled if scoring deviations)
  eye check     = n/a (S-row); reproduction = the verifier re-reads the module and reruns its test
      file plus any new cases
  must not move = boxscore_crosscheck.py's existing behavior on its current tests (byte-identical);
      every threshold
NON-TAUTOLOGY: if extending, the team-level target is named (source file + column), not invented; a
game where the target is missing is reported excluded, not zero-deviation.
EVIDENCE: docs/evidence/harness/S243_boxscore_coherence_check_2026-09-04.md plus the check inventory
and (if built) the deviation table. ASCII only, calibration language only.
TEST: run the existing test_boxscore_crosscheck.py; if extended, exactly one new case, run only
that file.
REPORT: FALSIFIED-already-built or the new deviation table, test line, SHA. Commit by pathspec, no
push. NEVER PARK.
