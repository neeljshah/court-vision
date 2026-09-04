GAP S242 | sport nba (pregame) | worktree aXX | log cx_s242_ptsrebast_given_minutes
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: pts/reb/ast = minutes x rate; S241 builds the minutes distribution, not the conditional
rate distributions. The 7 prop models (_PROP_STATS, player_props.py) are point estimates;
quantile_props.py / quantile_calibration.py (_CQR_STATS = pts/reb/ast) exist but live coverage is
unconfirmed. Depends on S241 landing or its CLOSED AT LIMIT naming a reusable module.
PREMISE (step 0): read quantile_props.py and quantile_calibration.py in full; report whether either
produces a real per-player 10/50/90 row (not just the 4 KB summary JSON) and its current coverage
on a fresh chronological holdout for pts/reb/ast.
LIMIT (step 1): if no quantile machinery exists beyond the summary JSON and one cannot be built
additively and <= 300 LOC, report CLOSED AT LIMIT naming the gap.
CHANGE (step 2): additive only -- new module scripts/platformkit/pts_reb_ast_conditional_dist.py:
per-minute rate distribution (quantile regression, or a parametric rate x S241's minutes quantiles)
for pts/reb/ast, conditioned as-of by game_date on momentum_signals (673,204 rows),
per_player_calibration (307,643, sigma_resid), gt_weighted_forms (99,157). Walk-forward via
walkforward_embargo_prereg.py (S233), embargo days >= 1.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or
ledger; no edits under src/ kernel/ api/ intel/ scripts/team_system/ or token-gated eval_gate
modules; new helpers <= 300 lines.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = CRPS and pinball at q10/q50/q90 for pts/reb/ast plus [q10,q90] coverage per stat
  before        = 0 CRPS numbers exist for any of the 7 prop stats; point MAE only (label OOF vs
      holdout per feedback_mae_measurement_labeling)
  bar           = q50 pinball for each stat within 10 pct of that stat's own labelled point MAE;
      [q10,q90] coverage in [0.75, 0.90] per stat, reported honestly if outside
  n             = >= 30 game clusters, target >= 1,000 player-games per stat on the holdout
  eye check     = n/a (S-row); reproduction = the verifier reruns fresh-process and diffs CRPS/
      pinball/coverage per stat
  must not move = the 7-stat _PROP_STATS list; existing point models (imported); every MAE cited in
      JOB_EVIDENCE_PACKET.md
NON-TAUTOLOGY: coverage/CRPS computed on the same holdout rows for all three stats; a stat excluded
for bad coverage is named, never silently dropped from a reported average.
EVIDENCE: docs/evidence/harness/S242_ptsrebast_given_minutes_2026-09-04.md plus the CRPS/pinball/
coverage table per stat. ASCII only, calibration language only.
TEST: one new per-file test (CRPS on a Gaussian fixture matches closed-form within tolerance;
pinball at q50 equals half-MAE on a symmetric-error fixture), run only that file.
REPORT: CRPS/pinball/coverage per stat vs labelled point MAE, test line, SHA. Commit by pathspec,
no push. NEVER PARK.
