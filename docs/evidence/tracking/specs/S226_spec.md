GAP S226 | sport nba (in-game) | worktree aXX | log cx_s226_ingame_clutch_foul_rotation
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: the clutch cell has never been scored as its own partition. Measured 2026-09-04 on
nba_checkpoints_full.parquet: period 4 with |margin| <= 5 and game_clock_s <= 300 holds 62,465 ticks / 702 games;
period 4 overall 284,586 ticks / 1,593 games. Two as-of-safe state stores have never entered a screen:
inplay_foul_state.parquet (5,010 rows, team foul totals by game_id + period) and possession_states_* (30,383 / 30,199
rows, seconds_remaining, pace, run_diff). The atlas foul and rotation stores are SNAPSHOT-ONLY at as_of 2026-05-31 and
must NOT be joined here.
PREMISE (step 0): reproduce the 62,465 / 702 and 284,586 / 1,593 counts, and measure what share of clutch ticks can be
given a foul state and a possession state from those two stores (report the join key and the coverage).
LIMIT (step 1): report the market's own n-weighted ECE and Brier inside the clutch cell beside the S123 incumbent's,
with n_eff and the 80 pct-power MDE. If the MDE exceeds 0.004 the cell is UNDERPOWERED -- report CLOSED AT LIMIT.
CHANGE (step 2): additive only -- a NEW sibling module beside scripts/platformkit/foundry/ingame_grammar_nba.py
exposing the same five functions (TRANSFORMS, build_state, build_grid, enumerate_hypotheses, hypothesis_column) over
the foul-state and possession-state columns; ingame_grammar_nba.py itself is never edited. SCREEN side only: no prereg
seal, no charge, no ledger read or write. The atlas join is reported BLOCKED-ON-S223, not performed.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or the FWER ledger;
no edits under src/ kernel/ api/ intel/ scripts/team_system/ or the token-gated eval_gate modules (PROPOSED snippets
in docs/research/ instead); new helpers <= 300 lines (LOC rail).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = Brier improvement over the S123 leak-free incumbent inside the clutch cell, per enumerated
      hypothesis
  before        = no clutch-cell result exists; cell counts 62,465 ticks / 702 games
  bar           = market and incumbent Brier plus ECE printed for the clutch cell BEFORE any arm; every enumerated
      hypothesis reported with improvement, DM p, game-clustered CI, n_eff and a BH-adjusted p at q 0.05 across the
      family; >= 30 game clusters; 0 ticks dropped without a printed reason; SCREEN_NULL is the expected valid result
  n             = 62,465 ticks / 702 game clusters
  eye check     = n/a (S-row); reproduction = the verifier re-runs the sibling module and diffs the per-hypothesis CSV
  must not move = the +0.004 bar; foundry/ingame_grammar_nba.py byte-identical; the FWER ledger; the frozen families
      spec
NON-TAUTOLOGY: the clutch cell is defined on tick-observable state only (period, margin, clock); the memo states how
many of the 1,593 games contribute no clutch tick and excludes no game that does.
EVIDENCE: docs/evidence/harness/S226_ingame_clutch_foul_rotation_2026-09-04.md plus the per-hypothesis CSV. ASCII
only, calibration language only; an honest NULL, REJECT or CLOSED AT LIMIT is a success.
TEST: one new per-file test (the sibling grammar enumerates deterministically; BAR is imported, never assigned), run
only that file.
REPORT: the clutch-cell market/incumbent table, the best hypothesis with its CI and BH p, the foul and possession
coverage, the test line, SHA. Commit by pathspec, no push. NEVER PARK.
