GAP S246 | sport all (pregame) | worktree aXX | log cx_s246_boxscore_scoring_harness
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: S241-S245 need a shared leak-free scoring spine so numbers are comparable, not each
re-deriving CRPS/pinball independently. S233 landed eval_gate/walkforward_embargo_prereg.py
(purge_embargo_walk_forward, seal_prereg, assert_sealed) 2026-09-04 (63d5ec4b7); no box-score
scoring wrapper exists. S228 (open) parses closing_props into a tidy table this row consumes.
PREMISE (step 0): re-read walkforward_embargo_prereg.py's exact signatures; confirm S228's tidy
prop-close table exists at its own spec's named path; if S228 has not landed, use the raw
closing_props/*.json files directly instead, naming the substitution.
LIMIT (step 1): if the S233 utility cannot wrap a CRPS/pinball scorer additively (its predict_fn
returns a single float, not a distribution), report CLOSED AT LIMIT naming the mismatch; never edit
walkforward_embargo_prereg.py (import-only, token-gated).
CHANGE (step 2): additive only -- new module scripts/platformkit/boxscore_scoring_harness.py:
crps_score(quantile_preds, actual) and pinball_loss(q, quantile_pred, actual) as pure functions
(no dependency on S241-S245's output shape beyond a {quantile: value} dict), plus
score_vs_prop_close(tidy_table, quantile_preds_by_row) reporting CRPS/pinball/coverage against the
S228 closing line where present and NOT SCORABLE where absent, wrapping S233's walk-forward split.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or
ledger; no edits under src/ kernel/ api/ intel/ scripts/team_system/ or token-gated eval_gate
modules (import, do not edit walkforward_embargo_prereg.py); new helpers <= 300 lines.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = crps_score/pinball_loss reproduce closed-form values on fixtures (Gaussian CRPS
      within 1e-6; pinball at q50 = half-MAE on a symmetric fixture); score_vs_prop_close runs
      end-to-end on S228's table (or raw JSONs) with 0 crashes
  before        = no shared CRPS/pinball scorer exists in scripts/platformkit/ (grep confirms)
  bar           = both fixture tests pass at tolerance; score_vs_prop_close processes every input
      row (0 silently dropped), reporting SCORABLE/NOT SCORABLE per row plus a summary count
  n             = 2 closed-form fixtures (CONSTRUCT) plus >= 30 game clusters if scored end-to-end
  eye check     = n/a (S-row); reproduction = the verifier reimports, reruns both fixtures, reruns
      score_vs_prop_close, diffs every score to 1e-9
  must not move = walkforward_embargo_prereg.py source (imported); S228's table schema (read-only)
NON-TAUTOLOGY: score_vs_prop_close never excludes a row to flatter the average; a row with no
closing line counts as NOT SCORABLE, never silently omitted from the denominator.
EVIDENCE: docs/evidence/harness/S246_boxscore_scoring_harness_2026-09-04.md plus the two fixture
JSONs and (if run) the end-to-end score table. ASCII only, calibration language only.
TEST: one new per-file test (both closed-form fixtures plus one score_vs_prop_close call on a 3-row
synthetic table with one NOT SCORABLE row), run only that file.
REPORT: fixture tolerances met, S228-substitution status, end-to-end row counts, test line, SHA.
Commit by pathspec, no push. NEVER PARK.
