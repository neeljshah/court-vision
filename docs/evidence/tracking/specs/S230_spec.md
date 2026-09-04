GAP S230 | sport nba (pregame) | worktree a16XX | log cx_s230_pregame_scheme_interaction
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: S108 fit every numeric as-of column the NBA gate corpus supplies (178) with logit(incumbent) as a true offset
under nested walk-forward and the inner CV zeroed EVERY coefficient in 20 of 23 outer folds (elastic net +0.001360, n
619). That refutes single-column additions, not pairwise INTERACTIONS. An as-of-safe pairing table has never been
used: matchup_grid.parquet (4,900 rows, game_id + game_date + team_id + opp_team_id, 2024-10-22 .. 2026-04-12,
offense-z vs defense-z per SCHEDULED game). S204 measured p_close non-null on 563 of 1,814 gate rows, only 220
pregame.
PREMISE (step 0): reproduce the 4,900-row matchup_grid count and its date range, and report how many gate_corpus_nba
rows join it AND carry a pregame p_close (at most 220). If that count is below 30, that is the finding.
LIMIT (step 1): score the incumbent and the close on the joined rows first. If the close is not scorable there (S204
labelled NBA NOT SCORABLE at n_eff 2 on 220 rows), report CLOSED AT LIMIT and publish the model-relative number only,
labelled as not market-relative.
CHANGE (step 2): additive only -- a new module under scripts/platformkit/ adding ONE family of offense-z x defense-z
interaction terms to the incumbent as an offset model, walk-forward by event_date, the UNDATED
archetype_scheme_interactions (108) and position_scheme_interactions (315) grids used ONLY to freeze the hypothesis
list before any fit. SCREEN only: no seal, no charge, no ledger.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or the FWER ledger;
no edits under src/ kernel/ api/ intel/ scripts/team_system/ or the token-gated eval_gate modules (PROPOSED snippets
in docs/research/ instead); new helpers <= 300 lines (LOC rail).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = ECE, Brier and log-loss of the interaction arm vs the incumbent, and vs p_close where it is joined
  before        = S108 elastic net +0.001360 (n 619), every coefficient zeroed in 20 of 23 folds; p_close 563/1,814
      (220 pregame)
  bar           = the joined-row census printed first; the interaction arm scored against the incumbent on all joined
      rows with a corpus_unit-clustered CI and n_eff, and against p_close only on the pregame subset with its n
      stated; 10-bin reliability under the S05 bin-edge rule; 0 rows dropped after the pairing step; NULL is the
      expected result
  n             = >= 30 clusters for the model-relative arm; the pregame-close n stated exactly whatever it is
  eye check     = n/a (S-row); reproduction = the verifier re-runs the module and diffs the per-row prediction CSV
  must not move = gate_corpus_nba and its close parquet (read-only); the S05 bin-edge rule; every threshold; the FWER
      ledger
NON-TAUTOLOGY: the memo separates the model-relative and market-relative rows and never quotes the former as a market
result; the pregame and first_inplay close rows are never pooled.
EVIDENCE: docs/evidence/harness/S230_pregame_scheme_interaction_2026-09-04.md plus the per-row prediction CSV. ASCII
only, calibration language only; an honest NULL, REJECT or CLOSED AT LIMIT is a success.
TEST: one new per-file test (the interaction list is frozen before the fit; the offset is exactly logit(incumbent)),
run only that file.
REPORT: the joined-row census, the interaction arm's ECE / Brier / log-loss with CI, the close row and its n, the test
line, SHA. Commit by pathspec, no push. NEVER PARK.
