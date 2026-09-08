VERDICT: REJECT
Candidate: e641f68ee16b5fca563c42adb3c45d7e7678b45c; effective row diff dce917b36..e641f68ee.
ACCEPTANCE FAIL: the claimed exhaustive table is a same-line count and omits streamed/multiline sinks (g326_crlf_safe_hashes_2026-09-07.md:13-20; autoloop/standing_prereg.py:241; combo/corpus_cache.py:42).
PREMISE PASS: `git show dce917b36:scripts/platformkit/tracking/g298_audit.py | python -` raises at source line 29; `python -m scripts.platformkit.tracking.g298_audit` prints PASS (g298_audit.py:33).
NUMBERS FAIL: claimed 99 exhaustive; reproduced 99 same-line matches but at least 154 executable AST sinks (122 direct/tainted, 32 streamed). Claimed 4 LF/6 RAW of 10; reproduced 5 LF/8 RAW over 13 unique (path, expected) pairs (memo:14,35-38).
HASHES PASS: all three memo LF hashes reproduced and the effective diff changes 0 existing committed hash constants/artifacts (memo:28,58-60).
TEST PASS: `python -m pytest tests/platformkit/test_g326_crlf_safe_hashes.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 4 passed in 0.87s.
TEST PASS: `python -m pytest scripts/platformkit/tracking/test_g298_compare.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 5 passed in 0.94s.
IMPORT/LOC/ADDITIVITY PASS: only test_g326 imports touched modules; hash_lf.py 32, g298_audit.py 74, test 69 LOC; no field/status removal or reader change (g298_audit.py:11,33).
EVIDENCE PASS: 23/23 named paths exist; memo is 60 lines and has NOT VERIFIED at g326_crlf_safe_hashes_2026-09-07.md:45-53.
B1 FAIL: unnamed non-one-line sinks are excluded from the denominator (g326_crlf_safe_hashes_2026-09-07.md:14-20).
B2 PASS: additive helper import/call only; no renamed/removed field, status, or reader behavior (g298_audit.py:11,33).
B3 PASS: no gate or absent-evidence branch was added (g298_audit.py:18).
B4 PASS: no claim lifecycle was added or changed (g298_audit.py:18).
B5 PASS: local CPU-only execution and no deployment are stated (g326_crlf_safe_hashes_2026-09-07.md:4).
B6 PASS: no module moved or retired; the helper is additive (hash_lf.py:1).
B7 PASS: this is a construct with no renders or head-slice sampling (g326_crlf_safe_hashes_2026-09-07.md:13,52).
B8 PASS: no fitted residual is used (g326_crlf_safe_hashes_2026-09-07.md:21).
B9 PASS: each static file-byte hash sink is a nonrecycled unit, although the enumeration is incomplete (g326_crlf_safe_hashes_2026-09-07.md:14).
B10 PASS: no threshold or gate value changed (g326_crlf_safe_hashes_2026-09-07.md:28).
Q1 PASS: prereg seal a2a5fbc7a3e4f7f655a4798c1cab78bc0e8cf718ab5321383f7e2839977fe9ad reproduced and commit 8fe486f80 predates 4de3f41b9 (g326_prereg_2026-09-07.md:83).
Q2 PASS: this tooling construct charges no trial (g326_prereg_2026-09-07.md:1).
Q3 PASS: 0 existing committed hashes and 0 bars changed (g326_crlf_safe_hashes_2026-09-07.md:28).
Q4 PASS: no OOS scored comparison is claimed (g326_crlf_safe_hashes_2026-09-07.md:52).
Q5 PASS: no AHEAD verdict is claimed (g326_crlf_safe_hashes_2026-09-07.md:1).
Q6 PASS: candidate changes use compliant calibration language (g326_crlf_safe_hashes_2026-09-07.md:1).
Q7 FAIL: n is declared CONSTRUCT but is not exhaustive; at least 32 streamed sinks are absent (g326_crlf_safe_hashes_2026-09-07.md:13-20; eval_gate/ledger_backup.py:37).
Q8 PASS: the older-row premise was independently remeasured true before scoring (g298_audit.py:33).
CORRECTION: memo:14 `99 ... (denominator)` -> `99 same-line matches; NOT an exhaustive denominator`; rerun and classify every static sink exactly once.
CORRECTION: memo:35-38 `4 LF, 6 RAW, 10 pairs` -> `5 LF, 8 RAW, 13 unique (path, expected) pairs`.
CORRECTION: memo:23-24,33 current converted/raw references are g298_audit.py:33 and :31, not :29 and :28.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-07 | all | G326 | premise and after-command reproduced; exhaustive-site claim not reproduced (99 same-line matches versus at least 154 executable static sinks); 13 unique hash pairs reproduce as 5 LF and 8 RAW; 0 existing committed hashes changed | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: g298_audit.py:69 rewrites a committed inventory with absolute worktree paths and current code bytes; direct execution dirties the tree and is not checkout-stable.
