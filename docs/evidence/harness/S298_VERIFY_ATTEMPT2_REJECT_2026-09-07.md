VERDICT: REJECT
CANDIDATE PASS: reviewed `440e0aa937a21638b228d719c526a1cae1dcff99`; its full diff adds the JSON, memo, paired-loss archive and one results-ledger row (`RESULTS_LEDGER_SYSTEM.md:546`).
PREMISE PASS: independently streamed the two named parquets and reproduced rows 77744/1023, zero counts STL/BLK 40520/53267 and 669/799, first three keys, hashes, and 78767 unique union keys (`S298_rare_count_mixture_2026-09-07.md:46-56`).
ACCEPTANCE PASS: all six fixed comparisons are published; only STL/NB2 and BLK/NB2 have positive adjusted lower bounds, so the fixed all-six bar is correctly reported BEHIND (`S298_spec.md:14-23`; `S298_rare_count_mixture_2026-09-07.md:58-82`).
REPRODUCTION PASS: streamed 472602 paired rows/78767 keys; all means, intervals and adjusted bounds match JSON, with loss-identity residual 0; 630136 PMF rows replay paired losses within 2.23e-16 and all secondary values to 5.13e-13 (`S298_rare_count_mixture_2026-09-07.md:176-186`).
DURABILITY FAIL: the required 73504906-byte PMF archive is untracked and absent from commit 440e0aa93, so a clean checkout cannot perform the required PMF replay (`S298_spec.md:25-26`; `S298_rare_count_mixture_2026-09-07.md:188-205`).
EVIDENCE PASS: every named local artifact exists now and its stated size/hash matches; the PMF file's current presence does not cure the durability failure (`S298_rare_count_mixture_2026-09-07.md:188-207`).
ADDITIVITY/READERS PASS: candidate commit only adds artifacts and appends a row; no field, status, reader behavior, module, import or command is removed/renamed; sole Python importer is `test_s298_rare_count_mixture.py:6`.
LOC PASS: candidate touches no `.py`; complete S298 route/test are 300/56 LOC and the repository rail passes (`s298_rare_count_mixture.py:1-300`; `test_s298_rare_count_mixture.py:1-56`).
NOT VERIFIED PASS: candidate memo has an explicit list (`S298_rare_count_mixture_2026-09-07.md:209-228`).
B1 PASS: all 78767 keys remain scored, including 16705 empty-history states (`s298_rare_count_mixture.py:64-93`; `S298_rare_count_mixture_2026-09-07.md:129-139`).
B2 PASS: additions are schema-additive and the sole importer ran (`s298_rare_count_mixture.py:197-220`; `test_s298_rare_count_mixture.py:6`).
B3 PASS: no production gate or absent-evidence quarantine is introduced (`s298_rare_count_mixture.py:273-297`).
B4 PASS: no claim/retry lifecycle is introduced (`s298_rare_count_mixture.py:273-297`).
B5 PASS: heavy compute is documented as pod scratch only, with no deployed-tree write (`S298_rare_count_mixture_2026-09-07.md:146-164`).
B6 PASS: no module is moved or retired and the only importer resolves (`test_s298_rare_count_mixture.py:6`).
B7 PASS: every held-out key is archived; no head slice supplies scored evidence (`S298_rare_count_mixture_2026-09-07.md:58-82`).
B8 PASS: each forecast uses evaluator training rows strictly earlier than its test timestamp (`s298_rare_count_mixture.py:143-170`).
B9 PASS: 78767 unique player-game units and 3645 distinct game clusters independently reproduce (`s298_rare_count_mixture.py:64-93`; `S298_rare_count_mixture_2026-09-07.md:58-65`).
B10 PASS: five groups, one-day symmetric embargo, six families-by-stat comparisons and the zero lower-bound bar match the unchanged spec (`S298_spec.md:14-23`; `S298_rare_count_mixture_2026-09-07_prereg.md:59-73`).
Q1 PASS: seals 906ef129... and fa854d69... recompute and their one-file commits 287ae3aca/8672cb998 precede route commit 619e244d7 and scoring evidence (`S298_rare_count_mixture_2026-09-07_prereg.md:97`; `S298_rare_count_mixture_2026-09-07_prereg_supplement.md:65`).
Q2 PASS: this calibration comparison opens no trial ledger or launch count; only the post-result results row is declared (`s298_rare_count_mixture.py:273-297`; `S298_rare_count_mixture_2026-09-07_prereg_supplement.md:58-63`).
Q3 PASS: the fixed bar is byte-consistent across spec, preregistration and memo (`S298_spec.md:14-23`; `S298_rare_count_mixture_2026-09-07_prereg.md:59-73`; `S298_rare_count_mixture_2026-09-07.md:58-82`).
Q4 PASS: shared CPCV supplies symmetric purge/embargo and strict test redaction; fitting then filters training rows to strict past (`cpcv_vector_distribution.py:20-49`; `s298_rare_count_mixture.py:143-170`).
Q5 PASS: no AHEAD claim is made and both memo and row say SINGLE-WINDOW (`S298_rare_count_mixture_2026-09-07.md:3-8`; `RESULTS_LEDGER_SYSTEM.md:546`).
Q6 PASS: candidate text is ASCII and the restricted-language/retracted-number scan is clean (`S298_rare_count_mixture_2026-09-07.md:1-228`).
Q7 PASS: independently reproduced held-out game clusters 775/812/755/768/535, all above 30 (`s298_rare_count_mixture.py:259-270`; `S298_rare_count_mixture_2026-09-07.md:109-127`).
Q8 PASS: the scorer checks and prints the premise before any score computation; independent recount matches (`s298_rare_count_mixture.py:273-281`; `S298_rare_count_mixture_2026-09-07.md:46-56`).
TEST PASS: `python -m pytest tests/platformkit/test_s298_rare_count_mixture.py -q -p no:cacheprovider` -> 2 passed in 1.34s (local).
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed in 0.68s (local).
BASELINE N/A: `tests/platformkit/test_s298_rare_count_mixture.py` is absent on master, so no master copy exists to execute.
CORRECTION: commit the exact PMF rows in a compact archive or committed sub-50-MB shards, then minimally update `artifacts.pmfs` and the memo artifact table/hashes and rerun replay.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-07 | NBA rare-count calibration | S298 | 78767 player-games/3645 clusters; adjusted lower bound positive on 2/6; required PMF archive absent from candidate | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: the scorer and focused test verify the primary preregistration seal but not the attempt-2 supplement seal (`s298_rare_count_mixture.py:42-51`; `test_s298_rare_count_mixture.py:9-11`).
