VERDICT: REJECT
Candidate: a2384311599f4bf1c822f439472d5a9c939303eb
ACCEPTANCE PASS - 2,000/2,000 classified; all 1,467 unresolved rows name memo, line, and reason; six rerun files match byte-for-byte; eye records are evenly spaced; fixture behavior passes (summary.json:2, unresolved.csv:1, eye.txt:1).
B1 PASS - all tokens are retained before classification; no metric exclusion exists (scripts/platformkit/tracking/g381_census.py:79).
B2 PASS - form is additive; prior fields and statuses remain; both readers were checked (scripts/platformkit/tracking/g381_census.py:18, scripts/platformkit/tracking/g381_lint.py:7, tests/platformkit/test_g381_memo_digest_census.py:11).
B3 PASS - absent evidence remains UNRESOLVED rather than quarantined (tests/platformkit/test_g381_memo_digest_census.py:122).
B4 PASS - this one-shot census has no claim or retry state (scripts/platformkit/tracking/g381_census.py:167).
B5 PASS - the route reads Git history only and names no deployed-tree write (scripts/platformkit/tracking/g381_census.py:3).
B6 PASS - no module was moved or removed; existing import readers remain live (scripts/platformkit/tracking/g381_lint.py:7).
B7 PASS - indices 0,162,325,488,651,814,977,1140,1303,1466 span the unresolved set (scripts/platformkit/tracking/g381_census.py:114, eye.txt:1).
B8 PASS - no fitted residual or fitted comparison is used (scripts/platformkit/tracking/g381_resolution.py:89).
B9 PASS - denominator is every token occurrence in the exhaustive construct, not a recycled unit (scripts/platformkit/tracking/g381_census.py:53, summary.json:9).
B10 PASS - A2 states the bar is unchanged and the candidate does not edit the spec (g381_prereg_amendment_A2_2026-09-10.md:8).
Q1 PASS - A2 seal rehashes and commit 4bfb34931 predates the metric commit (g381_prereg_amendment_A2_2026-09-10.md:22).
Q2 PASS - no charged trial or K exists for this census (g381_memo_digest_census_2026-09-10.md:8).
Q3 PASS - no acceptance bar or threshold moved (g381_prereg_amendment_A2_2026-09-10.md:8).
Q4 PASS - this is a Git-history construct, not an OOS score or meta-learner (g381_memo_digest_census_2026-09-10.md:5).
Q5 PASS - no AHEAD outcome is claimed (g381_memo_digest_census_2026-09-10.md:1).
Q6 FAIL - one prohibited prose token occurs in copied register text (per_row.csv:378); the claimed zero-hit scan is false (g381_memo_digest_census_2026-09-10.md:40).
Q7 PASS - independent ls-tree enumeration reproduced all 627 memos; no sampling was used (scripts/platformkit/tracking/g381_census.py:29, summary.json:10).
Q8 PASS - premise independently reproduced as 380 / 2,000 / 1,375, matching the claim (g381_memo_digest_census_2026-09-10.md:8).
TEST PASS - `python -m pytest tests/platformkit/test_g381_memo_digest_census.py -q -p no:cacheprovider` -> 17 passed.
REPRODUCED - claimed 309 landing / 222 unnamed / 2 object identifiers / 1,467 unresolved; measured identical; 533/2,000 non-unresolved and linter 1,402 also reproduce (summary.json:2, lint_console.log:1).
LOC PASS - g381_census.py 190; g381_resolution.py 255; test_g381_memo_digest_census.py 203, each <= 300.
MEMO PASS - exactly 60 lines, NOT VERIFIED list present, and all ten stated file hashes reproduce (g381_memo_digest_census_2026-09-10.md:42).
CORRECTION (minimal) - at g381_census.py:142 emit a deterministic Q6-redaction marker plus source-row digest for noncompliant copied prose; add one fixture and regenerate per_row.csv plus memo hashes.
CORRECTION (minimal) - change g381_memo_digest_census_2026-09-10.md:40 only after the regenerated artifact scans to zero.
2026-09-10 | tracking | G381 | premise 380/2,000/1,375; 2,000 classified; 309 landing, 222 unnamed, 2 object identifiers, 1,467 unresolved; one Q6 prose violation | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: census.csv has 2,000 occurrence rows but 1,995 unique record tuples because token position is omitted; this does not fail the occurrence-based acceptance denominator.
