GAP S258 | sport nba | worktree a15 | log cx_s258_incumbent_conformal_band_v2
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S238 CLOSED AT LIMIT (see its register row). Attempt 2 sealed a prereg and built the incumbent conformal
  band correctly but scored the 232,951-tick / 797-game SCREEN CSV and claimed the full source was absent, while
  nba_checkpoints_full.parquet exists and measures 465,249 ticks / 1,593 games via
  scripts/platformkit/eval_gate/s86_nba_every_tick.py (CHECKPOINTS, load_ticks). This row applies the verifier's
  exact diff to the attempt-2 code (recover it from the S238 lane's branch history: commits 5e1c01525 + 6bfae6f67;
  if unreachable, rebuild from the S238 memo's description).
PREMISE (step 0, INFORMATIONAL): import s86_nba_every_tick, load s86.CHECKPOINTS through s86.load_ticks, print
  n_ticks and n_games (expect 465,249 / 1,593); print the S101 STATIC-arm market/model coverage figures.
CHANGE (step 1, the verifier's CORRECTION DIFF verbatim): the evaluator loads s86.CHECKPOINTS via s86.load_ticks and
  maps market_prob to market; the SCREEN CSV is retained ONLY for the S101 regression check; regenerate the JSON
  and memo on 465,249 / 1,593. Script <= 300 LOC under scripts/platformkit/eval_gate/, import-only against
  s101_aci_coverage.py, ingame_incumbent_nba.py, aci_online.py. Seal a prereg FIRST (own commit; seal = SHA-256 of
  the committed bytes above the seal line, LF, verified via git show HEAD). Never write docs/research/.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = empirical coverage vs nominal (90 pct, 80 pct) AND mean interval half-width per grouped cell,
                  STATIC arm, S123-incumbent series (apply_incumbent e4 | ladder_base)
  before        = no coverage or width has ever been reported for the S123 incumbent on the full source
  bar           = coverage + width printed for every cell with >= COVERAGE_MIN_GROUP=400 ticks (smaller cells
                  ABSENT_BECAUSE, never dropped); the S101 market/model STATIC-arm coverage reproduces unchanged to
                  <= 1e-9; the printed denominator is 465,249 / 1,593
  n             = 465,249 ticks / 1,593 games, cell counts printed
  eye check     = n/a (S-row); reproduction = verifier reruns the script and diffs every cell's coverage and width
  must not move = COVERAGE_MIN_GROUP, COVERAGE_MAX_GROUPS, the S86 fold/embargo design, every existing threshold
NON-TAUTOLOGY: report the worst-covered cells and the widest intervals, not only the passing ones.
EVIDENCE: docs/evidence/harness/S258_incumbent_conformal_band_v2_2026-09-04.md + JSON (new filenames; never
  rewrite an existing artifact schema). ASCII only; calibration language only; evidence files under 50 MB.
TEST: one new per-file test (full-source denominator asserted; S101 regression), run only that file.
REPORT: coverage/width table, denominator, S101 regression line, seal hashes, test line, SHA. No push. NEVER PARK.
