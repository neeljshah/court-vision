GAP S140 | sport all (harness) | worktree a10 | log cx_s140_loc_rail
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of section B AND section Q before you report. Template: docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md. Calibration language only: no dollar, ROI, profit or edge words. Never touch data/registry, src/, kernel/, api/, intel/, scripts/team_system/. Per-file tests only (python -m pytest <one file> -q); NEVER the full suite. data/ in this worktree is a read-only junction to the main repo's data/ (no data/cache/eval_gate, no registry) -- never write under data/. NEVER PARK: run everything to completion this turn; never end waiting. COMMIT: explicit pathspec (git add <paths> && git commit -m "..." -- <paths>), in this worktree, no push. Last line of your report: SHA: <sha>.
GAP (verbatim from the register): THREE FOUNDRY MODULES BREACH THE 300-LOC RAIL: scripts/platformkit/foundry/results_db.py (372), scripts/platformkit/combo/corpus_cache.py (487), scripts/platformkit/foundry/screen_predictor.py (332). Split each into the named module plus ONE sibling module with byte-identical public behaviour.
READ (every signature on disk): the three modules; every importer of each (grep -rn for results_db, corpus_cache, screen_predictor under scripts tests domains); their test files (tests/platformkit/foundry/test_results_db.py, scripts/platformkit/combo/test_corpus_cache_freshness.py, tests/platformkit/foundry/test_screen_predictor.py).
PREMISE (step 0): print wc -l of the three; confirm each > 300. If any is already <= 300, skip it and say so.
LIMIT (step 1): n/a (CONSTRUCT row).
CHANGE (step 2): for each module move a coherent block (pure helpers, SQL text, column tables, loaders) into a new sibling module (results_db_sql.py / corpus_cache_sources.py / screen_predictor_supply.py or similar) and re-export the moved names from the original so EVERY importer resolves unchanged (no importer edited). Byte-identical behaviour: for results_db, a scripted claim/record/reap sequence on a temp sqlite gives identical rows before and after (record the before run's output in the memo); for corpus_cache, load_gate_corpus for all four sports returns frames equal to before (assert .equals) and the sidecar freshness rules unchanged; for screen_predictor, corpus_states('soccer') and ('nba') return identical states/tables/labels and check_feature_name refusals identical on a 20-column sample.
TEST: the three existing per-file test files must pass unchanged (no test edited); add one test per split asserting the re-export (getattr on the original module) and that the original is <= 300 lines.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = modules at or under 300 LOC with byte-identical behaviour; denominator = 3
  before        = 0/3
  bar           = 3/3, all existing tests green, zero importers edited
  n             = 3 (CONSTRUCT)
  eye check     = n/a; reproduction = verifier runs the three test files + the equality scripts in master
  must not move = any public name, any threshold, data/cache/eval_gate/backtest_fwer.jsonl (18 rows; never open it), data/registry/**
NON-TAUTOLOGY: the equality checks run against the PRE-split module (a copy saved before editing) not against itself.
EVIDENCE: docs/evidence/harness/S140_loc_rail_2026-09-03.md (before/after LOC table, equality outputs, test output, NOT VERIFIED list).
POD: none. Do not ssh anywhere.
