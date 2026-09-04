GAP S265 | sport nba | worktree a15 | log cx_s265_incumbent_conformal_band_sample
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S238 and S258 both CLOSED AT LIMIT on the same wall: the full 465,249-tick / 1,593-game source needs ~900 MB,
  the laptop RAM guard kills it, and contract B5 forbids a pod run before ACCEPT. This row is stage 1 of the B5
  shape: a SAMPLE-SCALE acceptance that lands the module; stage 2 (a successor row) runs the landed module on the
  full source on the pod. Recover the scorer from the S258 lane history: `git show 7d6407749 --stat` (sample screen)
  and `git show dd6b3c378 --stat` (its prereg); `git show <sha>:<path> > <path>` for scripts/ and tests/ files.
PREMISE (step 0, INFORMATIONAL): print n_ticks / n_games of s86.load_ticks(s86.CHECKPOINTS) via a streaming read of
  ONLY the game_id column (expect 465,249 / 1,593); print the 24 STATIC market/model coverage cells from the
  committed S101 JSON (name its path).
CHANGE (step 1): additive; scorer <= 300 LOC under scripts/platformkit/eval_gate/, import-only against
  s101_aci_coverage.py, ingame_incumbent_nba.py, aci_online.py. Seal a prereg FIRST as its own commit (LF; seal =
  SHA-256 of the STAGED bytes above the seal line via git show :<path>, verified with git show HEAD:<path>) that
  fixes the sample: a seeded, whole-game subsample of at most 80,000 ticks (print seed, games, ticks), the grouped
  cells, COVERAGE_MIN_GROUP=400, the S86 fold/embargo design. Score the S123-incumbent STATIC arm on that sample
  through the shared evaluator with purge + symmetric embargo; the S101 regression REPLAYS the retained S101 screen
  and compares all 24 STATIC cells to the COMMITTED S101 JSON (never to itself). RSS printed before/after; abort
  with MEMORY LIMIT above 600 MB. Never a full-source call; never a pod copy (B5).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = empirical coverage vs nominal (90, 80 pct) AND mean half-width per grouped cell, STATIC arm,
                  S123-incumbent series, on the sealed sample
  before        = no coverage or width has ever been ACCEPTED for the S123 incumbent (S238, S258 closed at limit)
  bar           = every cell with >= 400 sample ticks reported (smaller cells ABSENT_BECAUSE); the 24 S101 STATIC
                  cells replayed from the retained screen match the committed S101 JSON to <= 1e-9; printed sample
                  denominator equals the sealed one; peak RSS printed and < 600 MB
  n             = the sealed sample (>= 30 game clusters), denominators printed; NOT the full source
  eye check     = n/a (S-row); reproduction = verifier reruns the scorer with the sealed seed and diffs every cell
  must not move = COVERAGE_MIN_GROUP, COVERAGE_MAX_GROUPS, the S86 fold/embargo design, every existing threshold,
                  the committed S101 JSON, every existing artifact (new dated filenames only)
NON-TAUTOLOGY: worst-covered cells and widest intervals reported; the memo states plainly that sample coverage is
  not full-source coverage and names the stage-2 pod row as the only route to the 465,249 / 1,593 claim.
EVIDENCE: docs/evidence/harness/S265_incumbent_conformal_band_sample_2026-09-04.md + JSON + paired-loss CSV (Q9).
TEST: one per-file test recomputing one cell from the archived paired-loss CSV (< 200 MB), run only that file.
REPORT: seed/denominators, coverage-width table, S101 24-cell match line, RSS, test line, SHA. No push. NEVER PARK.
