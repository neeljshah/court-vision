GAP S01 | sport all (harness) | worktree a10 | log cx_s01_baseline_const
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check against every line of section B AND section Q (Q1-Q8) before you report. Template: docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md.
GAP (verbatim from the register): scripts/platformkit/ingame/run_gap_arms_real_corpus.py:18-19 `_BASELINE_TICKS` 144424 and `_BASELINE_WINDOW_TICKS` 14802 match nothing on disk (real: 52,558 / 7,158); a two-line fix.
READ: the module (108 LOC) and its imports `discover_store`, `_window_ids`, `load_records`; docs/research/organization-sprint/E4_PROMOTION_RESULT_2026-09-01.md section 1 if present in this worktree (gitignored on master -- absent is fine).
PREMISE (step 0): run the module's own `_load_ticks(discover_store())` (or the store path the module's CLI defaults to) on the real local store `data/cache/ingame_grade_joined/mlb`. Print len(ticks) and the `_window_ids` count exactly as the module computes them. Premise holds iff 52,558 / 7,158 and the two constants differ. If the store is absent, STOP and report NO STORE with the path tried. If the counts differ from 52,558 / 7,158, STOP, write the memo with the measured counts, commit, report FALSIFIED (a valid result).
LIMIT (step 1): n/a -- CONSTRUCT row; the loader counts ARE the limit.
CHANGE (step 2): exactly two lines: `_BASELINE_TICKS = 52558` and `_BASELINE_WINDOW_TICKS = 7158`. Nothing else in the module. No rename, no removal, no other file under scripts/platformkit/ingame/.
TEST: NEW tests/platformkit/ingame/test_gap_arms_baseline_constants.py -- drives the module's own `_load_ticks` on the real store (`pytest.skip` with a reason if the store is absent); asserts both constants equal the loader counts and that the module's own match/comparison flag is True. Run ONLY this file: `python -m pytest tests/platformkit/ingame/test_gap_arms_baseline_constants.py -q`. Never run the whole tests/ tree.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = constants equal loader counts; denominator = the 2 constants
  before        = 0/2 (measured: 144424 vs 52,558 ticks; 14802 vs 7,158 window ticks)
  bar           = 2/2
  n             = 2 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier runs the test in master and re-prints the loader counts
  must not move = every other file under scripts/platformkit/ingame/, every gate threshold under scripts/platformkit/eval_gate/, data/registry/** (never written), data/cache/eval_gate/backtest_fwer.jsonl (13 rows, never touched)
NON-TAUTOLOGY: the metric covers both constants; nothing is excluded.
EVIDENCE: docs/evidence/harness/S01_baseline_const_2026-09-03.md -- before/after table (loader counts, old and new constants), the exact commands run, test output, and a NOT VERIFIED list. Calibration language only: no dollar, ROI, profit or edge word.
POD: none. Local store only. Do not ssh anywhere.
COMMIT: explicit pathspec (the module, the test, the memo), in this worktree, no push. Report the sha as the LAST line: `SHA: <sha>`.
NEVER PARK: run the test to completion this turn; never end waiting.
