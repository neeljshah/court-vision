GAP S168 | sport all | worktree a16 | log cx_s168_third_strip_copy
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
PREMISE (step 0): after S164 (shared helper scripts/platformkit/venue_history/game_key.py, imported by
build_price_series.add_game_key and eval_gate/s99_corpus.rekey) a THIRD copy of the strip rule survives at
scripts/platformkit/ingame/s90_microstructure_screen.py:69 (frame["event_key"].astype(str).str.split("-", n=1)
.str[1], bound to `suffix`). Measure: quote the line; grep the tree for every remaining split("-" / n=1 strip of
event_key (list file:line); count implementations today (expect 2: helper + s90).
LIMIT (step 1): n/a.
CHANGE (step 2): s90 imports game_key_from_event_key; derived values byte-identical (sha of the derived column
on the mlb store event_key column, read one store at a time, event_key column only); decide the helper's HOME
package: keep venue_history/game_key.py as the home and record in its docstring the three importers (venue_history,
eval_gate, ingame) -- or move it to a shared util with a re-export alias at the old path; name every importer.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = implementations of the strip rule under scripts/platformkit (excluding the helper itself)
  before        = 1 (s90) besides the helper
  bar           = 0 besides the helper; s90 derived column sha identical before/after; helper docstring names
                  every importer; tests/platformkit/ingame/test_s90_microstructure_screen.py still 5 passed
  n             = 3 call sites (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier greps and re-derives the sha on the mlb column
  must not move = event_key, game_key values, every reader, thresholds, the FWER ledger (never touched)
NON-TAUTOLOGY: the grep covers the whole scripts/platformkit tree.
EVIDENCE: docs/evidence/harness/S168_third_strip_copy_2026-09-04.md -- grep table, shas, the home decision,
NOT VERIFIED list. ASCII only. Calibration language only.
TEST: run scripts/platformkit/venue_history/test_game_key.py and tests/platformkit/ingame/
test_s90_microstructure_screen.py, one file per command; no new test file needed.
COMMIT: explicit pathspec in the worktree, no push. Report the sha. NEVER PARK; finish with the report + SHA.
