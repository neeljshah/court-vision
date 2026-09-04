GAP S229 | sport nba (pregame) | worktree a17 | log cx_s229_matchup_player_vs_defender
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: the person-to-person question has never been screened and the served surface cannot answer it:
matchup_preview's style_matchup note reads 'sport-level style-pairing statistics ... no team/player-to-style-category
resolver is wired' (verified live 2026-09-04). Two as-of-safe sidecars have never entered a screen:
player_def_archetype_sidecar.parquet (99,498 rows, player_id + game_date, 2022-10-18 .. 2026-05-24, player-vs-HELP_DEF
/ PACE_CONTROL / SWITCH_HEAVY deviations) with an identical-shape null twin, and player_opp_splits_sidecar.parquet
(99,498 player-vs-opponent rows). The atlas matchup stores are SNAPSHOT-ONLY (as_of 2026-05-31) and thin (106 rows)
and must NOT be joined here.
PREMISE (step 0): reproduce both sidecar row counts and date ranges, confirm the null twin has the same shape, and
report the defender-join coverage: how many player-game rows carry a non-null scheme deviation AND an opponent split,
as a share of 99,498.
LIMIT (step 1): report the main-effects-only baseline's RMSE and MAE first. If the interaction cannot be estimated on
>= 30 game clusters after the join, report CLOSED AT LIMIT with the coverage table.
CHANGE (step 2): additive only -- a new module under scripts/platformkit/ scoring the player's stat residual against
his own as-of expectation, base and candidate differing ONLY by the scheme x opponent interaction
(gate_baseline_comparability), walk-forward by game_date, the null-twin sidecar run as a planted-null arm. The atlas
half is reported BLOCKED-ON-S223, never joined. SCREEN only: no seal, no charge, no ledger.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or the FWER ledger;
no edits under src/ kernel/ api/ intel/ scripts/team_system/ or the token-gated eval_gate modules (PROPOSED snippets
in docs/research/ instead); new helpers <= 300 lines (LOC rail).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = RMSE and MAE of the stat residual, interaction arm minus main-effects-only baseline, on identical
      rows
  before        = no interaction has ever been screened; sidecars 99,498 rows each, coverage unmeasured
  bar           = the coverage table printed first; base and candidate differing only by the interaction term, proved
      by an identical-columns assertion; the null-twin arm beside the real arm on the same rows and folds; a
      game-clustered CI and n_eff; >= 30 game clusters; a null result is the expected valid outcome
  n             = >= 30 game clusters over the joined subset of 99,498 player-game rows
  eye check     = n/a (S-row); reproduction = the verifier re-runs the module and diffs the per-game residual series
  must not move = both sidecars and the null twin (read-only); the atlas stores (never opened); every threshold; the
      ledger
NON-TAUTOLOGY: the memo reports the joined subset's base rate and residual spread against the full 99,498, so a
favourable subset cannot pass as a result; rows lost at the join are counted at each step.
EVIDENCE: docs/evidence/harness/S229_matchup_player_vs_defender_2026-09-04.md plus the coverage table and per-game
residual series. ASCII only, calibration language only; an honest NULL, REJECT or CLOSED AT LIMIT is a success.
TEST: one new per-file test (base and candidate columns differ by exactly the interaction; the null-twin path runs),
run only that file.
REPORT: the coverage table, the interaction delta with its CI, the null-twin row, the test line, SHA. Commit by
pathspec, no push. NEVER PARK.
