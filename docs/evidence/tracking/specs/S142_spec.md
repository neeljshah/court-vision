GAP S142 | sport all (harness) | worktree a11 | log cx_s142_a2_tests
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of section B AND section Q before you report. Template: docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md. Calibration language only: no dollar, ROI, profit or edge words. Never touch data/registry, src/, kernel/, api/, intel/, scripts/team_system/. Per-file tests only (python -m pytest <one file> -q); NEVER the full suite. data/ in this worktree is a read-only junction to the main repo's data/ (no data/cache/eval_gate junction -- the archives were COPIED into this worktree's data/cache/eval_gate/) -- never write under data/. NEVER PARK: run everything to completion this turn; never end waiting. COMMIT: explicit pathspec (git add <paths> && git commit -m "..." -- <paths>), in this worktree, no push. Last line of your report: SHA: <sha>.
GAP (verbatim from the register): EIGHT LANDED IN-GAME MODULES HAVE NO TEST THAT REPRODUCES THEIR PUBLISHED HEADLINE FROM THE ARCHIVE (A2): s92_nba_lineup_dynamic, s94_nba_early_shrinkage, s96_nba_overreaction, s97_nba_sensor_fusion, s103_nba_sigma, s115_ingame_models, s116_pooled_ingame (all under scripts/platformkit/eval_gate/) and foundry/ingame_screen_soccer.
READ: each module's memo under docs/evidence/harness/ (S92_*, S94_*, S96_*, S97_*, S103_*, S115_*, S116_*, S117_*) for its headline numbers and the archive paths under data/cache/eval_gate/ (s92_*, s94_*, s96_*, s97_*, s103_*, s115_*, s116_*, s117_*); scripts/platformkit/eval_gate/dm_test.py (diebold_mariano reference), eval_gate/tick_informative.py; an existing A2-style test to copy the shape from: tests/platformkit/ingame/test_s114_ingame_ensemble.py or test_s121_requote.py.
PREMISE (step 0): for each of the 8, print whether a test file exists under tests/platformkit/ingame/ or tests/platformkit/foundry/ and whether the archive CSV/JSON exists under data/cache/eval_gate/. If an archive is absent, that module is CLOSED AT LIMIT for this row (say which) -- never fabricate.
LIMIT (step 1): n/a.
CHANGE (step 2): NEW per-file tests tests/platformkit/ingame/test_<module>_a2.py (one per module; the soccer one under tests/platformkit/foundry/): each loads the archived per-tick/per-event series, recomputes the headline Brier(s), improvement and the game-clustered DM CI with the REFERENCE dm_test.diebold_mariano, and asserts equality to the memo's printed digits (abs tol 1e-6 on Brier/improvement; CI bounds 1e-5), plus n / n_informative from tick_informative.flag_ticks where the memo quotes them. Skip cleanly (pytest.skip naming the path) if the archive is absent at test time so the suite is clone-safe. Do NOT edit any landed module.
TEST: run each new file individually; all must pass on this box.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = modules with a passing A2 archive-reproduction test; denominator = 8
  before        = 0/8
  bar           = 8/8 (or N/8 with each miss named CLOSED AT LIMIT on a missing archive)
  n             = 8 (CONSTRUCT)
  eye check     = n/a; reproduction = verifier runs the 8 files in master
  must not move = every landed module, every archive (read-only), the ledger (never open it), data/registry/**
NON-TAUTOLOGY: the tests recompute from the SERIES columns (per-tick losses / probabilities + outcomes), never from a stored summary number.
EVIDENCE: docs/evidence/harness/S142_a2_tests_2026-09-03.md (table: module, archive, headline reproduced to, test file, pass).
POD: none. Do not ssh anywhere.
