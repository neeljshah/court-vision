GAP S225 | sport nba (in-game) | worktree a16 | log cx_s225_ingame_intel_conditioning_rerun
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: two in-game conditioning layers exist and were never scored against a market.
ingame_hypothesis_{hot_night,scheme_fit}.json plus row parquets hold 7,350 rows / 1,225 games (2024-25) and 444 / 74
(2025-26), keyed by ESPN event_id. Own caveats: the prior 'is fit on the SAME season it is scored against'; 'No
in-play odds -> verdict is CALIBRATION'; and for hot_night 'PLANTED NULL SURVIVED'. Recorded: hot_night 0.1723 ->
0.1689, delta 0.00345, CI [0.00201, 0.0049]; scheme_fit -0.00027, n_clusters 919. Measured 2026-09-04:
espn_nba_game_bridge.parquet (1,299 exact) joins the checkpoints on 635 of 1,593 games = 187,203 ticks, 579 with a
hot_night row -- the no-odds caveat is now false.
PREMISE (step 0): reproduce the 635-game / 187,203-tick bridge join and the 579-game intersection, THEN verify the
rows align in TIME: (period, seconds_remaining) must map to the ticks' (period, game_clock_s) within a stated
tolerance. If they do not, that misalignment IS the finding -- report it and stop.
LIMIT (step 1): re-run the planted-null (shuffled conditioning prior) arm FIRST, leak-free. If the planted null still
beats BASE the layer is a flexibility artifact and the row is CLOSED AT LIMIT as a confirmed REJECT.
CHANGE (step 2): additive only -- a new module under scripts/platformkit/ fitting the conditioning prior strictly on
data EARLIER than the scored game (walk-forward by game-first-date), optionally substituting momentum_signals.parquet
(673,204 as-of rows) for hot_night's in-sample prior, scoring every arm against both the S123 incumbent and
market_prob at the same tick, truncation invariance via ingame_guards.assert_tick_asof at 8 probes. SCREEN only: no
seal, no charge, no ledger.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or the FWER ledger;
no edits under src/ kernel/ api/ intel/ scripts/team_system/ or the token-gated eval_gate modules (PROPOSED snippets
in docs/research/ instead); new helpers <= 300 lines (LOC rail).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = Brier and n-weighted ECE per arm on the bridged ticks, vs the incumbent and vs market_prob
  before        = hot_night brier_base 0.1723 / brier_prior 0.1689 (in-sample, no market); scheme_fit delta -0.00027
  bar           = every real arm reported beside its planted-null arm on identical rows and folds, with game-clustered
      DM CI, n_eff and the market's own Brier and ECE; the alignment tolerance printed; >= 30 game clusters; 0 ticks
      dropped without a printed reason; a surviving planted null is reported REJECT and the real arm published anyway
  n             = 187,203 ticks / 635 game clusters (579 with a hot_night row)
  eye check     = n/a (S-row); reproduction = the verifier re-runs the module and diffs the per-game differential CSV
  must not move = the +0.004 bar; the published in-sample figures (kept as the BEFORE row); the FWER ledger; the
      families spec
NON-TAUTOLOGY: the memo states how many of the 1,225 hot_night games lack a checkpoint match and reports the scored
subset's outcome base rate against the full corpus's, so a favourable subset cannot pass as a result.
EVIDENCE: docs/evidence/harness/S225_ingame_intel_conditioning_rerun_2026-09-04.md plus per-game differentials for
every arm. ASCII only, calibration language only; an honest NULL, REJECT or CLOSED AT LIMIT is a success.
TEST: one new per-file test (the walk-forward prior never sees the scored game; the planted-null path runs), run only
that file.
REPORT: each arm's Brier vs incumbent and vs market with its CI, the planted-null row, the test line, SHA. Commit by
pathspec, no push. NEVER PARK.
