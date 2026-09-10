VERDICT: REJECT
CANDIDATE PASS: 4a97fabf8 changes the memo plus 16 raw rater text files; no production path or table is changed (g375_corpus_sport_purity_2026-09-10.md:15).
ACCEPTANCE PASS: 300 distinct sections, 13 prefixes, kappa reported, 127/127 non-play attributed or UNKNOWN, no threshold moved, no section deleted, proposal only (g375_corpus_sport_purity_2026-09-10.md:9,19,23,27).
PREMISE PASS: recomputed census is 1031 unique ids and 14 prefixes; sports are basketball 436, nba 308, ncaa_basketball 217, wnba 70; sheet_0023 independently confirms the named bleague section is soccer (census.csv:462-467; reference.csv:24).
REPRODUCTION PASS: claimed and recomputed overall impurity 127/281 = 452 per mille [395,510]; sport impurity 7/281 = 25 per mille [12,51] (impurity_table.csv:2; g375_corpus_sport_purity_2026-09-10.md:17).
REPRODUCTION PASS: raw .txt parse gives 562 rows, 281 paired sheets, agreement 0.921708, kappa 0.849806, and exactly matches ratings.csv; labels are 154/119/6/1/1 (g375_corpus_sport_purity_2026-09-10.md:15).
EYE CHECK PASS: all 7 OTHER_SPORT/NON_SPORT sheets and 20 evenly spaced PLAY sheets confirm the memo, including the disclosed sheet_0175 close-up (g375_corpus_sport_purity_2026-09-10.md:25).
NOT VERIFIED PASS: memo names human-rating, one-tick, attribution, diagnostic, and trial-ledger limits (g375_corpus_sport_purity_2026-09-10.md:29).
B1 PASS: all 19 unavailable sampled rows are named and retained outside the 281 rated denominator (absent.csv:1; g375_corpus_sport_purity_2026-09-10.md:11).
B2 FAIL: committed batches are .txt, but the sole archive reader selects only *.log; a fresh checkout cannot regenerate ratings.csv from the committed raw evidence (scripts/platformkit/tracking/g375_rate.py:43; g375_corpus_sport_purity_2026-09-10.md:15).
B3 PASS: missing feeder evidence becomes UNKNOWN and remains in attribution (scripts/platformkit/tracking/g375_score.py:70; g375_corpus_sport_purity_2026-09-10.md:19).
B4 PASS (N/A): the evidence parser has no claim/reclaim state (scripts/platformkit/tracking/g375_rate.py:42).
B5 PASS: no deployed tree was written (g375_corpus_sport_purity_2026-09-10.md:23).
B6 PASS: no module was moved or retired (g375_corpus_sport_purity_2026-09-10.md:23).
B7 PASS: the exact sealed draw reproduces sample.csv and spans each stratum (scripts/platformkit/tracking/g375_sample.py:45; tests/platformkit/test_g375_corpus_sport_purity.py:24).
B8 PASS: diagnostic uses a frozen external reference and fits nothing (g375_corpus_sport_purity_2026-09-10.md:21).
B9 PASS: 300 unique section ids were sampled and 281 distinct rated sheets form the denominator (g375_corpus_sport_purity_2026-09-10.md:9,17).
B10 PASS: landed gate and thresholds are unchanged (g375_corpus_sport_purity_2026-09-10.md:23).
Q1 PASS: normalized prereg bytes reproduce seal 2f178a9d533cd9a36f90477ef5b81d499fbe282708433fa29a55344a830242b2; its sole-file commit predates ratings (g375_prereg_2026-09-10.md:177; g375_corpus_sport_purity_2026-09-10.md:5).
Q2 PASS (N/A): no charged trial or K applies (g375_corpus_sport_purity_2026-09-10.md:29).
Q3 PASS: sealed bars match the spec and no bar moved (g375_prereg_2026-09-10.md:158-161; g375_corpus_sport_purity_2026-09-10.md:27).
Q4 PASS (N/A): this is a content census, not an OOS model comparison (g375_corpus_sport_purity_2026-09-10.md:29).
Q5 PASS (N/A): no AHEAD result is claimed (g375_corpus_sport_purity_2026-09-10.md:1,29).
Q6 PASS: independent scoped prose/figure scan found 0 hits; candidate raw files are ASCII (g375_corpus_sport_purity_2026-09-10.md:31,35).
Q7 PASS: n=300 sampled; only prefixes with at least 30 rated sheets receive bounds (impurity_table.csv:2-15; g375_corpus_sport_purity_2026-09-10.md:17).
Q8 PASS: premise census and named-section decode precede scoring and are reported (g375_corpus_sport_purity_2026-09-10.md:3).
TEST PASS: `python -m pytest tests/platformkit/test_g375_corpus_sport_purity.py -q` -> 9 passed in 0.86s; this is the only existing test importing a G375 module (tests/platformkit/test_g375_corpus_sport_purity.py:7-10).
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 0.99s.
LOC PASS: g375_census.py 125, g375_diag.py 129, g375_rate.py 141, g375_sample.py 125, g375_score.py 184, g375_sheets.py 154; candidate commit touches no .py.
CORRECTION DIFF: scripts/platformkit/tracking/g375_rate.py:43 replace `raw_dir.glob("*.log")` with a sorted union of `*.log` and `*.txt` to preserve old and committed readers.
CORRECTION DIFF: tests/platformkit/test_g375_corpus_sport_purity.py add a collect-from-committed-.txt regression; current tests call parse_batch directly (line 88).
2026-09-10 | tracking | G375 | PARTIAL census reproduced: 127/281 non-play = 452 per mille [395,510]; sport impurity 7/281 = 25 per mille [12,51]; kappa 0.849806; committed raw reader accepts 0/16 batches | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: The memo points to impurity_table.csv for the full premise prefix table, but that file has 13 rated prefixes rather than the 14-prefix population census (g375_corpus_sport_purity_2026-09-10.md:3; impurity_table.csv:1-15).
NEW GAP: Two same-day unavailable responses do not establish permanence; retain the observed unavailable status without the permanence wording (g375_corpus_sport_purity_2026-09-10.md:11).
