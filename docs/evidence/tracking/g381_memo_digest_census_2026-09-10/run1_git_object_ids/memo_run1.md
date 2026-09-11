VERDICT: PARTIAL (the repository's `git hash-object --no-filters` emits 40-hex SHA-1 IDs, so the requested 64-hex Git-object SHA-256 form is unavailable; full byte SHA-256 values follow)

# G381 Memo Digest Census

Scope: every `docs/evidence/tracking/g*_*.md` and `G*_*.md` at merge-base
`627cdc63b7d0a3f82b6b6afb334df81414eb4581` (`HEAD~2`), read from Git history only.

Premise step 0: 380 digest-carrying memos / 2,000 digest tokens / 1,375 distinct
tokens. The premise passed (380 >= 30). The complete population had 627 memo paths.

Classification (2,000 / 2,000 classified):

| Class | Count | Share |
| --- | ---: | ---: |
| IDENTIFIES_AT_LANDING | 0 | 0.0% |
| IDENTIFIES_AT_HEAD_ONLY | 0 | 0.0% |
| CRLF_ONLY | 44 | 2.2% |
| ARTIFACT_UNNAMED | 0 | 0.0% |
| UNRESOLVED | 1,956 | 97.8% |

The acceptance metric is 0 / 2,000 = 0.0%. `unresolved.csv` names every
unresolved token with memo:line and its required sub-reason. `eye.txt` contains
10 evenly spaced unresolved tokens, source memo lines, and candidate sets tried.

Worst per-row unresolved counts: G327 prereg d (127/127), G325 prereg attempt 2
(126/126), G322 prereg attempt 2 (111/111), G327 detector stability attempt 2
(31/31), and G321 prereg (27/27).

Second run in `C:/Users/neelj/AppData/Local/Temp/g381_second` was byte-identical:
census.csv, per_row.csv, unresolved.csv, summary.json, and eye.txt all matched.
The diagnostic-only, unwired proposed linter found 1,402 violations over 627 memos.
Focused test: `tests/platformkit/test_g381_memo_digest_census.py` passed (10 tests).
Wall time for the final census: about 51 seconds; peak observed RSS: 108,085,248 bytes.
Q6 automated vocabulary scan built its patterns from character codes: 0 non-exempt
claim-language hits; retained historical source-path and source-line fields are data.

NOT VERIFIED: the 1,956 unresolved printed tokens identify no committed artifact;
the convention linter is a proposal with no production callers; 64-hex Git object
IDs cannot be produced by this SHA-1-format repository.

SHA-256 b06b744caed08faeef55c909ad7984ba2d233e8a3c20a1b330b55a11e0292f8d `docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_2026-09-10.md` (whole file)
SEAL sha256 481390c52cf868e4bf2a7b0ff8c387996164f135ec225ff15354575069398889 `docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_2026-09-10.md` (bytes above seal)
SHA-256 6c3d42cd71470b66bb3d364cc11687f8df86311791f43a5f30b69df6bfcd1995 `docs/evidence/tracking/g381_memo_digest_census_2026-09-10/census.csv`
SHA-256 494ccdb8753481e835ac955b5890705b441cc338ee04b4e54ee65ef8d02a38d3 `docs/evidence/tracking/g381_memo_digest_census_2026-09-10/per_row.csv`
SHA-256 8985c092485898fb35d327d1d3c5a30676f9ba523627763456dd6d7d2c581f92 `docs/evidence/tracking/g381_memo_digest_census_2026-09-10/unresolved.csv`
SHA-256 0772fbd2c5fed0d62d1c1fcd1afb1814e480c2abaa0b4e4b2ab8a4579a6db259 `docs/evidence/tracking/g381_memo_digest_census_2026-09-10/summary.json`
SHA-256 9ad84b7e2a0f22eaf3af4664d96ba0c8f5a02ca72da0b1548f1b5e4903e4470c `docs/evidence/tracking/g381_memo_digest_census_2026-09-10/eye.txt`
SHA-256 d585e74591b9b7973aa21a14e1425c4652857c1eaf3b9c917866d89e70e1b5d7 `docs/evidence/tracking/g381_memo_digest_census_2026-09-10/PROPOSED_digest_convention.md`
