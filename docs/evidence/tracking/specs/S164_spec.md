GAP S164 | sport all | worktree a16 | log cx_s164_shared_strip_helper
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
PREMISE (step 0): the series-prefix strip that turns an event_key into a game key now exists TWICE:
scripts/platformkit/venue_history/build_price_series.py add_game_key (landed S157 2026-09-04) and
scripts/platformkit/eval_gate/s99_corpus.py:56 (frame.pop("event_key").str.split("-", n=1).str[1]). Measure: quote
both lines; apply both to the same 200-row sample of data/cache/inplay_odds/mlb_price_series.parquet (read-only,
head only) and confirm the outputs are identical today (n = 200 CONSTRUCT).
LIMIT (step 1): n/a.
CHANGE (step 2): ONE shared helper (a new small module under scripts/platformkit/venue_history/ or eval_gate/,
<= 40 LOC) exporting game_key_from_event_key(series) -> series; add_game_key and s99_corpus both call it; no
behaviour change (outputs byte-identical on the sample and on the full mlb + soccer_intl stores by row count and
sha of the derived column -- read one store at a time, never both).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = number of independent implementations of the strip rule under scripts/platformkit
  before        = 2
  bar           = 1 (both call sites import the helper); derived-column sha identical before/after per store
  n             = 2 call sites + 2 stores (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier greps for split("-" and re-derives the sha on one store
  must not move = event_key, game_key values, every reader, every threshold, the FWER ledger (never touched)
NON-TAUTOLOGY: the sha comparison covers every row of each store, not the sample only.
EVIDENCE: docs/evidence/harness/S164_shared_strip_helper_2026-09-04.md -- the two quoted lines, shas before/after
per store, NOT VERIFIED list. ASCII only. Calibration language only.
TEST: one new per-file test for the helper (construct, no store read); also run scripts/platformkit/venue_history/
test_build_price_series.py and the s99_corpus test file if one exists, one file per command.
COMMIT: explicit pathspec in the worktree, no push. Report the sha. NEVER PARK; finish with the report + SHA.
