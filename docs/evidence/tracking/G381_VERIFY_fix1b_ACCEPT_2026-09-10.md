VERDICT: ACCEPT
Candidate: 9d19a2db84182ba8944d5b59509b9cda9e5b252b
ACCEPTANCE PASS - 2,000/2,000 classified; all 1,467 unresolved rows name memo, line, and reason; six run artifacts reproduce byte-identically; eye indices span 0..1,466; measured-population memo edits 0; both linter fixtures pass (summary.json:8, unresolved.csv:1, eye.txt:1).
B1 PASS - all token occurrences are retained before classification (scripts/platformkit/tracking/g381_census.py:95).
B2 PASS - headers and class/reason/form sets match the parent; the sole reader and its test were checked (scripts/platformkit/tracking/g381_lint.py:7, tests/platformkit/test_g381_memo_digest_census.py:11).
B3 PASS - absent evidence remains UNRESOLVED (tests/platformkit/test_g381_memo_digest_census.py:122).
B4 PASS - the one-shot census has no claim or retry state (scripts/platformkit/tracking/g381_census.py:169).
B5 PASS - the route reads local Git history only and names no deployed-tree write (scripts/platformkit/tracking/g381_census.py:21).
B6 PASS - no module moved or retired; the existing linter import remains live (scripts/platformkit/tracking/g381_lint.py:7).
B7 PASS - eye indices are 0,162,325,488,651,814,977,1140,1303,1466 (scripts/platformkit/tracking/g381_census.py:132).
B8 PASS - no fit or residual comparison is used (scripts/platformkit/tracking/g381_resolution.py:205).
B9 PASS - the denominator is every token occurrence in the exhaustive construct (G381_spec.md:43, summary.json:11).
B10 PASS - A2 states the bar is unchanged and the candidate does not edit the spec (g381_prereg_amendment_A2_2026-09-10.md:9).
Q1 PASS - A2 seal rehashes; seal commit 4bfb34931 precedes metric commit a23843115 (g381_prereg_amendment_A2_2026-09-10.md:22).
Q2 PASS - no charged trial or K applies to this construct census (g381_memo_digest_census_2026-09-10.md:8).
Q3 PASS - no acceptance bar or threshold moved (g381_prereg_amendment_A2_2026-09-10.md:9).
Q4 PASS - this is a Git-history construct, not an OOS score or meta-learner (g381_memo_digest_census_2026-09-10.md:3).
Q5 PASS - no AHEAD outcome is claimed (g381_memo_digest_census_2026-09-10.md:1).
Q6 PASS - 0 non-exempt hits in 58 added lines; copied prose is deterministically marked and source-bound (g381_census.py:75, test_g381_memo_digest_census.py:206, per_row.csv:378).
Q7 PASS - independent ls-tree enumeration reproduced the exhaustive 627-memo construct (scripts/platformkit/tracking/g381_census.py:30, summary.json:10).
Q8 PASS - premise independently reproduced as 380 / 2,000 / 1,375 (g381_memo_digest_census_2026-09-10.md:8).
TEST PASS - `python -m pytest tests/platformkit/test_g381_memo_digest_census.py -q -p no:cacheprovider` -> 18 passed in 9.56s; it is the only test importer.
REPRODUCED - claimed 309 landing / 222 unnamed / 2 object ids / 1,467 unresolved; measured identical; claimed 533/2,000 non-unresolved and linter 1,402; measured identical (summary.json:2).
BYTE CHECK PASS - census.csv, unresolved.csv, per_row.csv, summary.json, eye.txt, and run.log match in-memory regeneration; all 13 memo SHA-256 lines rehash (g381_memo_digest_census_2026-09-10.md:36).
LOC PASS - g381_census.py 203; test_g381_memo_digest_census.py 211; both <= 300.
ADDITIVITY PASS - all CSV headers and class/reason/form values remain; only per_row G74 prose changed, with matching source-row digest (scripts/platformkit/tracking/g381_census.py:75, per_row.csv:378).
MEMO PASS - exactly 60 lines with a NOT VERIFIED list (g381_memo_digest_census_2026-09-10.md:42).
CORRECTIONS: none.
2026-09-10 | tracking | G381 | premise 380/2,000/1,375; 2,000 classified; 309 landing, 222 unnamed, 2 object ids, 1,467 unresolved; Q6 scan 0 non-exempt hits | ACCEPT (verified: codex-sol, contract A/B/Q)
NEW GAP: census.csv has 2,000 occurrence rows but 1,995 unique record tuples because token position is omitted; the acceptance denominator is occurrence-based.
NEW GAP: per_row.csv marks one copied register row instead of quoting it verbatim; the original remains at the frozen Git ref and is source-bound, and verbatim prose is outside the acceptance rule (G381_spec.md:31).
