GAP S231 | sport all | worktree aXX | log cx_s231_signal_combination_shrinkage
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: how signals are WEIGHTED has never been tested; only SELECTION has. S114's nested top-k over 564 screened NBA
in-game hypotheses: best arm k=5 at -0.000400 vs the raw in-play line, DM CI [-0.000934, +0.000133]; k=5 beat k=1 by
+0.0000830, CI [+0.0000027, +0.0001634], p 0.0429 -- 'the one CI in this memo that excludes zero', 48x below the bar.
No weighting layer exists: signal_ensemble.py is a TRACKING-arm ensemble, family_combo_screen.py (S79) scores its
top-k on the same partition ('an in-sample ceiling, not a verdict'), stacker.py stacks OOF gap ARMS, and
confidence_ensemble.parquet (307,643 rows) has never been an arm.
PREMISE (step 0): reproduce S114's k=1 and k=5 numbers from its archived series (s114_ingame_ensemble_series.csv,
192,635 rows) at max abs diff <= 1e-9. If they do not reproduce, that is the finding and no weighting is fitted.
LIMIT (step 1): the k=5-over-k=1 gain of +0.0000830 is the ceiling any weighting scheme must beat to be interesting.
If no weighting arm exceeds it, report CLOSED AT LIMIT -- a valid and expected result.
CHANGE (step 2): additive only -- a new module under scripts/platformkit/ implementing inverse-variance and
James-Stein shrunk weights over the SAME screened members, plus a ridge/logit stack whose penalty is chosen in an
INNER fold, weights fitted on strictly earlier windows only and walked forward by game-first-date; confidence_ensemble
runs as one further arm. Every new column is OPT-IN, every caller of a touched helper grepped and listed, existing
callers bit-identical. SCREEN only: no seal, no charge, no ledger.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or the FWER ledger;
no edits under src/ kernel/ api/ intel/ scripts/team_system/ or the token-gated eval_gate modules (PROPOSED snippets
in docs/research/ instead); new helpers <= 300 lines (LOC rail).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = Brier and log-loss of each weighting arm vs (a) the S114 incumbent and (b) the raw in-play line,
      same rows
  before        = S114 k=5 -0.000400 vs the line, CI [-0.000934, +0.000133]; k=5 over k=1 +0.0000830, CI [+0.0000027,
      +0.0001634]
  bar           = the two S114 anchors reproduce at <= 1e-9; every weighting arm scored on identical rows and folds
      with a game-clustered CI, n_eff and its weight vector archived; the caller list printed; no arm beating
      +0.0000830 is the expected valid result
  n             = 192,635 series rows over the S114 game clusters
  eye check     = n/a (S-row); reproduction = the verifier re-runs the module in a fresh process and diffs the per-arm
      series
  must not move = s114_ingame_ensemble.json and its CSVs; the +0.004 bar; the ledger; every existing caller's output
NON-TAUTOLOGY: all screened members enter every arm; none is dropped for hurting one, and the memo prints each arm's
member count.
EVIDENCE: docs/evidence/harness/S231_signal_combination_shrinkage_2026-09-04.md plus per-arm series and the archived
weight vectors. ASCII only, calibration language only; an honest NULL, REJECT or CLOSED AT LIMIT is a success.
TEST: one new per-file test (weights fitted on a train window are byte-identical when future rows are appended), run
only that file.
REPORT: the two anchors reproduced, each weighting arm with its CI, the caller list, the test line, SHA. Commit by
pathspec, no push. NEVER PARK.
