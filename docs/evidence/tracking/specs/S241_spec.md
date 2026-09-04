GAP S241 | sport nba (pregame) | worktree a16 | log cx_s241_nba_minutes_distribution
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: points = minutes x rate, so minutes is the box-score keystone. Four point-estimate minutes
modules exist (src/prediction/minutes_predictor.py, minutes_floor_model.py, minutes_aware_props.py,
pts_minutes_model.py, none read this session) and no distributional (quantile/CRPS) minutes target
exists on disk. opp_minutes_predictions.parquet is opponent-facing only.
PREMISE (step 0): read all four minutes modules (skeleton then relevant functions); report which,
if any, already emits a distribution vs a point value, and its point-MAE on a fresh chronological
80/20 holdout (same protocol as scripts/verify_production_mae.py), labelled explicitly.
LIMIT (step 1): if no module extends additively to quantiles without editing a signature other code
calls (grep every caller first), report CLOSED AT LIMIT and name the coupling; never edit
src/prediction/*.py (human-gated).
CHANGE (step 2): additive only -- new module scripts/platformkit/nba_minutes_distribution.py
wrapping the strongest existing point model to emit 10/50/90 minutes quantiles per player-game,
using pinball-loss training or per_player_calibration.parquet's sigma_resid (307,643 as-of rows) as
a residual-width prior. Walk-forward via eval_gate/walkforward_embargo_prereg.py (S233), embargo
days >= 1.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or
ledger; no edits under src/ kernel/ api/ intel/ scripts/team_system/ or token-gated eval_gate
modules (import-only; PROPOSED snippets in docs/research/); new helpers <= 300 lines.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = pinball loss at q10/q50/q90 and empirical [q10,q90] coverage on the holdout
  before        = point-MAE only; no quantile/coverage number exists for any of the four modules
  bar           = q50 pinball loss matches the point model's MAE scale (not a regression); [q10,q90]
      coverage lands in [0.75, 0.90], reported honestly if outside
  n             = >= 30 game clusters, target >= 1,000 player-games on the holdout
  eye check     = n/a (S-row); reproduction = the verifier reruns fresh-process, diffs pinball/
      coverage numbers
  must not move = the four existing minutes modules (read-only, imported); every threshold in
      verify_production_mae.py
NON-TAUTOLOGY: DNP (0-minute) rows are included in coverage, not silently dropped to flatter it; the
holdout row count is printed in full.
EVIDENCE: docs/evidence/harness/S241_nba_minutes_distribution_2026-09-04.md plus a per-player
quantile sample and the pinball/coverage table. ASCII only, calibration language only.
TEST: one new per-file test (a synthetic minutes series checks q10<=q50<=q90 monotonicity and
pinball loss on a known fixture), run only that file.
REPORT: which module was reused, pinball/coverage numbers, DNP handling, test line, SHA. Commit by
pathspec, no push. NEVER PARK.
