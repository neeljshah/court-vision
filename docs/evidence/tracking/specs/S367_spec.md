GAP S367 | sport mlb + nfl | worktree harness-h25 (master-based) | log cx_s367_late_game_cohorts
# Late-game cohort builder: membership from observables AT THE TICK only (design: docs/evidence/harness/ASTRA_ROUND12_2026-09-21.md section 3; section 6 row 8)

SINGLE PROBLEM: earlier late-band readings selected ticks with hindsight (minutes to the realized close) and used a close proxy that
is now known to be wrong (the venue close_time is administrative; expected_expiration_time tracks the game). A cohort builder must
make outcome-conditioned selection impossible.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/ingame/late_game_cohorts.py` fails.

CHANGE:
1. scripts/platformkit/ingame/late_game_cohorts.py (<= 300 LOC, stdlib): input = chronological (state row, contemporaneous book
   mid) pairs per game; cells frozen in code exactly as the design states -- MLB: inning >= 7 and absolute score difference <= 3;
   NFL: fourth quarter, remaining regulation clock <= 600 s, absolute score difference <= 8; price bands [0.05, 0.20] and
   [0.80, 0.95] with fixed side orientation. It selects the FIRST eligible tick per game and cell. The function signature takes NO
   outcome, NO settlement, NO final score and NO realized end time -- they are not parameters, and a test proves the output is
   identical when those fields are present or absent in the rows. Missing state -> ineligible, never inferred. Output: cohort
   membership rows + counts per sport / cell / band + games per cell (the design's floor is 50 distinct games per cell; below
   it the cell is labelled DESCRIPTIVE_ONLY). No residual, no calibration statistic is computed here.
2. tests/platformkit/ingame/test_late_game_cohorts.py: hindsight-blindness, first-tick rule, band edges, missing state, overtime
   excluded from the NFL regulation cell, MLB extra innings included by the inning >= 7 rule (state it).
3. Memo docs/evidence/harness/S367_late_game_cohorts_2026-09-21.md.

CONTROLS: PREPARE only, NEW files only (edit no pre-existing module; import landed code), construct / fixture tests, no real
archive run, no network, no measured calibration, fill or markout number. ACCEPTANCE: the per-file tests pass; every CLI has
--help; diff = NEW files only. Vocabulary follows contract Q6; automated scan required; assemble retracted-figure literals
from single digits. The memo ends with a NOT VERIFIED list. The pod is OFF.
