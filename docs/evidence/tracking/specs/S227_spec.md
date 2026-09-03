GAP S227 | sport nba (in-game) | worktree aXX | log cx_s227_margin_tail_crps
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: every in-game arm on record is binary (home win) and therefore blind to the margin tail, where the blowout
and wild-outcome questions live. S58 trial B and S103 record that the repricer's FIXED margin sigma of 13.5
'over-states confidence at halftime' and was 'half the model-vs-line gap', and that a per-cell fitted sigma brings the
state-priced prior to -0.0021 vs the line with a CI including zero -- but sigma has only ever been judged through a
binary Brier, which cannot see distributional width. No CRPS or tail-coverage number exists for NBA in-game margin.
PREMISE (step 0): reproduce the corpus (nba_checkpoints_full.parquet 465,249 ticks / 1,593 games, margin and
outcome_home_win present on every row) and confirm the final margin is recoverable per game from score_home /
score_away at the last tick. If it is not, report FALSIFIED and stop.
LIMIT (step 1): compute CRPS and tail coverage for the incumbent's Gaussian at the fixed sigma 13.5 as the BEFORE row.
If that coverage is already within its nominal band at every ladder point there is nothing to fix -- CLOSED AT LIMIT.
CHANGE (step 2): additive only -- a new module under scripts/platformkit/ scoring CRPS of the margin distribution and
empirical coverage of P(|margin| >= m) on a FROZEN ladder m in {5, 10, 15, 20, 25, 30}, for the fixed-sigma arm and
for a walk-forward per-cell fitted sigma, with data/intelligence/garbage_time_segments.parquet supplying a blowout
label where its ids join. SCREEN side only: no prereg seal, no charge, no ledger read or write.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or the FWER ledger;
no edits under src/ kernel/ api/ intel/ scripts/team_system/ or the token-gated eval_gate modules (PROPOSED snippets
in docs/research/ instead); new helpers <= 300 lines (LOC rail).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = CRPS of the final-margin distribution and empirical coverage at each frozen ladder point
  before        = no CRPS or coverage number exists; the incumbent uses a constant sigma of 13.5
  bar           = both arms reported at all 6 ladder points with empirical coverage, nominal coverage, CRPS, a
      game-clustered CI on the CRPS difference and n_eff; the ladder frozen before any fit; 0 games dropped without a
      printed reason; a fitted sigma no better than 13.5 is the expected valid result
  n             = 1,593 game clusters (465,249 ticks)
  eye check     = n/a (S-row); reproduction = the verifier re-runs the module and diffs the per-game CRPS series
  must not move = the constant 13.5 in the existing repricer (this row fits a SEPARATE sigma and never edits it); the
      +0.004 bar; the FWER ledger
NON-TAUTOLOGY: coverage is reported at every ladder point including sparse ones, with the count beside it; no ladder
point is dropped for being sparse.
EVIDENCE: docs/evidence/harness/S227_margin_tail_crps_2026-09-04.md plus the per-game CRPS and coverage series. ASCII
only, calibration language only; an honest NULL, REJECT or CLOSED AT LIMIT is a success.
TEST: one new per-file test (CRPS of a known Gaussian against a known draw; the ladder is frozen), run only that file.
REPORT: the two-arm CRPS table, the coverage column, the CI on the difference, the test line, SHA. Commit by pathspec,
no push. NEVER PARK.
