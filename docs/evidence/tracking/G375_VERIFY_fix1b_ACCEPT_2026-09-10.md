VERDICT: ACCEPT
CANDIDATE PASS: 6d8fcfe4f adds .txt archive support while retaining .log, adds its regression, and changes no deployed route or threshold (scripts/platformkit/tracking/g375_rate.py:43).
PREMISE PASS: claimed/recomputed census is 1031 unique ids, 14 prefixes, and sports basketball 436 / nba 308 / ncaa_basketball 217 / wnba 70; sampled sheet_0023 confirms the named bleague section is soccer (census.csv:1; g375_corpus_sport_purity_2026-09-10.md:3).
REPRODUCTION PASS: claimed/recomputed non-play is 127/281 = 452 per mille [395,510], sport impurity is 7/281 = 25 per mille [12,51], and kappa is 0.849806 (impurity_table.csv:2; g375_corpus_sport_purity_2026-09-10.md:17).
REPRODUCTION PASS: committed .txt batches reconstruct 562/562 rows byte-for-byte by parsed fields; agreement is 259/281 = 0.921708 and labels are 154/119/6/1/1 (ratings.csv:1; g375_corpus_sport_purity_2026-09-10.md:15).
ACCEPTANCE PASS: 300 unique sampled ids, 13 prefixes, 127/127 attribution or UNKNOWN, no threshold moved, no section deleted, and proposal only; PARTIAL names 19 unavailable ratings (sample.csv:1; g375_corpus_sport_purity_2026-09-10.md:27).
EVIDENCE PASS: every named evidence path exists; 281 sheets plus 19 named unavailable rows partition all 300 sampled ids, and normalized artifact hashes match the memo (reference.csv:1; absent.csv:1; g375_corpus_sport_purity_2026-09-10.md:33).
EYE CHECK PASS: the complete impure montage confirms six soccer frames and one interview; the 20 evenly spaced PLAY montage confirms the disclosed sheet_0175 close-up (g375_corpus_sport_purity_2026-09-10.md:25).
NOT VERIFIED PASS: memo names the human-rating, one-tick, missing-attribution, diagnostic, and trial-ledger limits (g375_corpus_sport_purity_2026-09-10.md:29).
B1 PASS: all 19 unavailable sampled rows are named and retained outside the 281 rated denominator (absent.csv:1; g375_corpus_sport_purity_2026-09-10.md:11).
B2 PASS: reader preserves .log and additively accepts .txt; no field, label, status, or reader behavior is removed (scripts/platformkit/tracking/g375_rate.py:43; tests/platformkit/test_g375_corpus_sport_purity.py:95).
B3 PASS: absent feeder evidence becomes UNKNOWN and remains in attribution (scripts/platformkit/tracking/g375_score.py:74; attribution.csv:1).
B4 PASS (N/A): the archive reader has no claim/reclaim state (scripts/platformkit/tracking/g375_rate.py:40).
B5 PASS: candidate touches no deployment path and memo records no deployment (g375_corpus_sport_purity_2026-09-10.md:23).
B6 PASS: candidate moves or retires no module and leaves no orphan reference (scripts/platformkit/tracking/g375_rate.py:1).
B7 PASS: sealed draw is evenly spaced by stratum, and the test reproduces sample.csv rather than taking a head slice (scripts/platformkit/tracking/g375_sample.py:45; tests/platformkit/test_g375_corpus_sport_purity.py:24).
B8 PASS: diagnostic uses the frozen G364 reference, fits nothing, and is reported only as a diagnostic (g375_corpus_sport_purity_2026-09-10.md:21).
B9 PASS: denominator has 300 unique sampled ids and 281 unique rated sheets, not recycled units (sample.csv:1; labels.csv:1).
B10 PASS: content-gate and liveness files are byte-identical between master and candidate; sealed bars match the spec (g375_prereg_2026-09-10.md:153; g375_corpus_sport_purity_2026-09-10.md:23).
Q1 PASS: normalized pre-seal bytes reproduce 2f178a9d533cd9a36f90477ef5b81d499fbe282708433fa29a55344a830242b2; sole-file commit c32050e6 predates ratings (g375_prereg_2026-09-10.md:177).
Q2 PASS (N/A): no charged trial or K applies (g375_corpus_sport_purity_2026-09-10.md:29).
Q3 PASS: prereg bars are byte-identical to the spec and none moved (g375_prereg_2026-09-10.md:153; g375_corpus_sport_purity_2026-09-10.md:27).
Q4 PASS (N/A): this is a content census, not an OOS model comparison (g375_corpus_sport_purity_2026-09-10.md:29).
Q5 PASS (N/A): no AHEAD result is claimed (g375_corpus_sport_purity_2026-09-10.md:1).
Q6 PASS: independent scoped scan found 0 prohibited prose hits and all candidate text is ASCII (g375_corpus_sport_purity_2026-09-10.md:31).
Q7 PASS: n=300 is SAMPLED; only prefixes with at least 30 rated sheets are BOUNDED (impurity_table.csv:2).
Q8 PASS: premise census was remeasured before adjudication; it remains confirmed because the named bleague frame is soccer (g375_corpus_sport_purity_2026-09-10.md:3).
TEST PASS: `python -m pytest tests/platformkit/test_g375_corpus_sport_purity.py -q` -> 10 passed in 0.81s; sole importing test file (tests/platformkit/test_g375_corpus_sport_purity.py:8).
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 1.01s (tests/platformkit/test_loc_rail_scope.py:1).
LOC PASS: touched Python files g375_rate.py 141 and test_g375_corpus_sport_purity.py 116, each <= 300 (scripts/platformkit/tracking/g375_rate.py:1; tests/platformkit/test_g375_corpus_sport_purity.py:1).
CORRECTIONS: none.
2026-09-10 | tracking | G375 | PARTIAL census reproduced: 127/281 non-play = 452 per mille [395,510]; sport impurity 7/281 = 25 per mille [12,51]; kappa 0.849806; archive reader reconstructs 562/562 rows | ACCEPT (verified: codex-sol, contract A/B/Q)
NEW GAP: The original G375 ledger row still says the 19 sources were permanently removed, while the corrected memo says only unavailable and explicitly states permanence is not established (RESULTS_LEDGER.md:716; g375_corpus_sport_purity_2026-09-10.md:11).
