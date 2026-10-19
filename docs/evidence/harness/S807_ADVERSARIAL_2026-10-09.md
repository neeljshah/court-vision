# S807 verifier tiers -- 2026-10-09 (PAPER ONLY)

Subject: commit e0f8155e1 (spec + result memo) and the PROPOSED diff s807_tools/venue_time_memo.diff (not committed).

## Contract tier (Sonnet, read-only): ACCEPT
Premise reproduced from the night records: 10-06 / 10-07 / 10-08 steps[e] KILLED at 1800.172 / 1800.547 / 1800.328 s; 10-05 RAN 1119.672 s, 1521 rows. registry_scorer_e_night.py has 0 hits for forward_capture_stream / forward_capture_slim / fill_realism.
A1 PASS (all six logs recomputed; census_features is the largest phase on every run). A2 PASS (10-05 receipt 48dd38a2... and full 6fcb3499... equal master vs candidate; vs committed only reader_census.future_records 2755 vs 3281 plus path / sha leaves). A3 PASS (c07 1113.69 s, c08 1072.71 s, peak 79.57 pct of ceiling; master 10-07 1724.3 s). A4 PASS (venue_time.py in _EXTERNAL_DEPENDENCIES; adapters / ticks in IMPLEMENTATION_FILES; every candidate replay reached scoring). A5 PASS on structure (pytest not rerun by the tier). Prefix copy sizes equal the fill_realism inputs[].bytes. Language clean.
Notes taken: the census cut is 47.7 pct (10-05) and 40.2 pct (10-07), whole wall 42 / 35 pct; the diff comment said ~25 MB, measured +37-40 MB (comment corrected to ~40 MB); "82 importers" counts `from/import venue_time` lines under scripts/ only; land against merge-base 9b40bb209.

## Adversarial tier (Opus, scratch only): ACCEPT on behaviour
Harness: mutant file registered as scripts.platformkit.execution.venue_time via a pytest plugin; patched = 4 / 65 / 13 pass, master = memo test 4 of 4 fail.
13 mutants: 11 killed (isinstance gate, cache whole _parse, maxsize None, maxsize 1, reason dropped, strip key, lower key, list return, fraction-dropping key, isinstance + typed, prefix key); m09 (memo consulted first) equivalent; m11 (subclass routed through str(value)) SURVIVED -- the PROPOSED diff does not do this, the tests did not pin it.
Fix: a fifth case test_subclass_parses_its_own_characters_uncached (a subclass whose __str__ returns a different valid stamp must parse its own characters, uncached). Patched: 5 passed; test_venue_time.py 65 passed. m11 now fails that case by construction (its output is a valid epoch, the case asserts invalid_time).
Fuzz (seed 807): 25,000 exact str + 25,000 subclass calls + 7,456 repeats + 466 non-str: 0 mismatches; eviction run 320,000 calls over 160,000 distinct strings past the 131,072 bound: 0 mismatches; the same fuzz catches m01 / m10 / m11.

## Landing check for whoever lands the PROPOSED diff (not a behaviour issue)
venue_time.py's sha (fbbe778f...) is pinned elsewhere: scoreboard_cumulative_prereg.py:34 / :209 (_validate raises implementation_mismatch on an existing payload -- no committed payload with a window_id found, local data/ not checked), scoreboard_history_slices.py:28 (code_identity rotates, cached slices recompute), PREREG_FORECAST_LOG_PROPOSED_2026-10-06.json:47. Confirm none is live, or re-seal, before landing.
NOT VERIFIED: the bytes claim on 10-08 master vs candidate (no master 10-08 replay); the paper-night wrapper wall.
