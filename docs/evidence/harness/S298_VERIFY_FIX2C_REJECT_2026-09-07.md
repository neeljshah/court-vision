VERDICT: REJECT
CANDIDATE PASS: reviewed full diff and stat for `d6ff90e227a98d681732b39fa54286c63942c2c7` (13 files; durable shards plus scorer/test edits).
PREMISE PASS: independent column-only reads reproduce rows 77744/1023, STL/BLK zeros 40520/53267 and 669/799, first keys and source hashes (`S298_rare_count_mixture_2026-09-07.md:46-56`).
ACCEPTANCE PASS: all six fixed comparisons remain published; exactly 2/6 adjusted lower bounds are positive, so the fixed all-six bar is not met (`S298_spec.md:14-23`; `S298_rare_count_mixture_2026-09-07.md:58-82`).
REPRODUCTION PASS: claimed/reproduced 472602 paired rows and 78767 unique keys match; six means 0.003408/-0.466006/-0.450305/0.003191/-0.348459/-0.339889 match within 1.2e-16 (`S298_rare_count_mixture_2026-09-07.json:108-193`).
REPRODUCTION PASS: streamed 630136 PMF rows from all 8 committed shards; canonical hash matches, PMF sum error <=6.67e-16, and direct-loss residual <=2.23e-16 (`s298_pmf_shards.py:18-45`; memo:188-216).
DURABILITY PASS: all 8 shard hashes/sizes and 78767 rows per shard reproduce; together they retain both stats and all four families (`S298_rare_count_mixture_2026-09-07.json:4-61`).
EVIDENCE PASS: every named local artifact exists; the committed shard set alone supports replay (`S298_rare_count_mixture_2026-09-07.md:218-251`).
ADDITIVITY FAIL: `artifacts.pmfs` changes from a filename scalar to a manifest object, while the scorer still emits the scalar contract (`S298_rare_count_mixture_2026-09-07.json:4`; `s298_rare_count_mixture.py:294`).
LOC PASS: touched Python files are 55/300/58 LOC; repository rail passes (`s298_pmf_shards.py:1`; `s298_rare_count_mixture.py:1`; `test_s298_rare_count_mixture.py:1`).
NOT VERIFIED PASS: the candidate memo has an explicit list (`S298_rare_count_mixture_2026-09-07.md:253-270`).
B1 PASS: every held-out key remains in the scored and archived denominator (`s298_rare_count_mixture.py:197-220`; memo:129-139).
B2 FAIL: the prior `artifacts.pmfs` field behavior is removed without an alias; repository search finds only the unchanged scalar writer and no checked manifest reader (`json:4`; `s298_rare_count_mixture.py:294`).
B3 PASS: no absent-evidence quarantine or production gate is introduced (`s298_rare_count_mixture.py:273-298`).
B4 PASS: no claim/retry lifecycle is introduced (`s298_rare_count_mixture.py:273-298`).
B5 PASS: scored compute is documented in pod scratch only; this fix performs no deployed-tree write (`S298_rare_count_mixture_2026-09-07.md:146-164`).
B6 PASS: no module is moved/retired; the sole existing test importer resolves (`test_s298_rare_count_mixture.py:6`).
B7 PASS: all held-out rows, not a head slice, are archived and replayed (`S298_rare_count_mixture_2026-09-07.md:176-216`).
B8 PASS: candidate forecasts use evaluator train rows strictly earlier than each test timestamp (`s298_rare_count_mixture.py:143-170`).
B9 PASS: 78767 unique player-game units and 3645 distinct game clusters reproduce (`S298_rare_count_mixture_2026-09-07.md:58-65`).
B10 PASS: candidate changes no threshold; groups, embargo, six comparisons and zero lower-bound bar match the spec (`S298_spec.md:17-21`; `prereg.md:59-73`).
Q1 PASS: both embedded seals recompute; commits `287ae3aca` and `8672cb998` precede scored evidence commit `440e0aa93` (`prereg.md:97`; `prereg_supplement.md:65`).
Q2 PASS: this comparison opens no charged-trial ledger or launch count; only the post-result system row is declared (`s298_rare_count_mixture.py:273-298`; `supplement:58-63`).
Q3 PASS: the fixed six-comparison bar is unchanged across spec, preregistration and memo (`S298_spec.md:17-21`; `prereg:59-73`; `memo:58-82`).
Q4 PASS: shared CPCV supplies purging, symmetric one-day embargo and redaction; fitting additionally filters to strict past (`cpcv_vector_distribution.py:20-49`; `s298_rare_count_mixture.py:143-170`).
Q5 PASS: no AHEAD claim is made and the memo remains SINGLE-WINDOW (`S298_rare_count_mixture_2026-09-07.md:3-8`).
Q6 PASS: candidate text is ASCII and the restricted-language/retracted-number scan is clean (`S298_rare_count_mixture_2026-09-07.md:1-270`).
Q7 PASS: reproduced per-fold game clusters 775/812/755/768/535, each >=30 (`s298_rare_count_mixture.py:259-270`; `memo:109-127`).
Q8 PASS: scorer checks/prints the premise before scoring; independent recount matches (`s298_rare_count_mixture.py:274-281`; `memo:46-56`).
TEST PASS: `python -m pytest tests/platformkit/test_s298_rare_count_mixture.py -q -p no:cacheprovider` -> 2 passed in 2.03s (local).
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed in 0.75s (local).
BASELINE N/A: same S298 command on master -> file absent, no tests ran; candidate tests passed, so no pre-existing-failure comparison was needed.
CORRECTION (minimal B2 diff): restore `artifacts.pmfs` to `"S298_rare_count_mixture_2026-09-07_pmfs.csv.gz"`; add the new object unchanged as sibling `artifacts.pmf_shards`.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-07 | nba rare-count calibration | S298 | 78767 player-games/3645 clusters; 2/6 adjusted lower bounds positive; PMF shards replay; B2 schema break | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: memo artifact table claims JSON 8665 bytes/hash da304a7b..., but current file is 11224 bytes/hash 2776f461...; update that row after the B2 correction (`memo:220`).
NEW GAP: candidate memo reports two test files in one command; retain the two independent commands above (`memo:168-174`).
NEW GAP: `load_pmf_shards` materializes rows plus multiple full 328969124-byte copies and has no test importer; use streaming reconstruction for this laptop (`s298_pmf_shards.py:23-45`).
