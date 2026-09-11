VERDICT: DONE

# G381 memo digest census -- measure phase run 2

Population ref: `627cdc63b7d0a3f82b6b6afb334df81414eb4581`, computed by
`git merge-base track-a7 master`. Landing commits are first-add commits in that history.
Run 1 remains archived under `g381_memo_digest_census_2026-09-10/run1_git_object_ids/`;
it is superseded because it compared Git object IDs rather than A1 raw-blob SHA-256 bytes.

PREMISE: 380 digest-carrying memos / 2,000 digest tokens / 1,375 distinct tokens.
The full tracking-memo population is 627; premise passes (380 >= 30).
All 2,000 tokens are classified; 329/2,000 (16.45 pct) resolve under A1.

| Class | Count | Share |
|---|---:|---:|
| IDENTIFIES_AT_LANDING | 108 | 5.40 pct |
| IDENTIFIES_AT_HEAD_ONLY | 0 | 0.00 pct |
| CRLF_ONLY | 0 | 0.00 pct |
| ARTIFACT_UNNAMED | 219 | 10.95 pct |
| OBJECT_ID | 2 | 0.10 pct |
| UNRESOLVED | 1,671 | 83.55 pct |

Worst per-row records by unresolved volume: `g327_prereg_2026-09-08d.md` 1/127;
`g325_prereg_attempt2_2026-09-07.md` 0/126; `g322_oversized_boxes_attempt2_2026-09-07.md` 0/111.
`unresolved.csv` names every unresolved token, memo line, and sub-reason; `eye.txt` gives
ten evenly spaced unresolved records with their source lines and attempted candidates.

The final repeat was byte-identical for census.csv, per_row.csv, unresolved.csv, summary.json,
eye.txt, and run.log. Final census wall time: 188 s; repeat wall time: 210 s.
Diagnostic only: the unwired proposed linter scanned 627 memos and reported 1,402 violations.
The focused fixture suite passed: 12 tests.
Q6 automated vocabulary scan: 0 non-exempt hits in authored prose and generated structural fields;
the one lexical geometric-register quote remains verbatim under the exact-evidence exception.

NOT VERIFIED:
- External or pod-only artifact bytes and absolute paths remain unresolved by construction.
- No claim is made that an unresolved historic token identifies an artifact outside this Git history.
- The linter is diagnostic only and has no production caller.

SHA-256 b06b744caed08faeef55c909ad7984ba2d233e8a3c20a1b330b55a11e0292f8d docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_2026-09-10.md
SHA-256 940674af3ea31cc5203ab58f36aef68cd9d7eb4a729a309aeb3c0c13c5a14b80 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_amendment_A1_2026-09-10.md
SHA-256 172893096eecc7b3f37fb7c1cf60bb68b1da4acde4fc6f6d0156018a644a12e6 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_amendment_A1_2026-09-10.md (sealed bytes above SEAL line)
SHA-256 d585e74591b9b7973aa21a14e1425c4652857c1eaf3b9c917866d89e70e1b5d7 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/PROPOSED_digest_convention.md
SHA-256 bbcdc774dd06a9e150f67f1877fcf4809f2b64ee99abad8d5694515c77bc8985 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/census.csv
SHA-256 8ebb6e14dc539413a1660e55f8539d62fe9850e94ccc2bf34c7b3360b12e755d docs/evidence/tracking/g381_memo_digest_census_2026-09-10/per_row.csv
SHA-256 17f651e72d32515f1a0dcc6fc772741949be63516828d855ec0b5058551537be docs/evidence/tracking/g381_memo_digest_census_2026-09-10/unresolved.csv
SHA-256 0f2f9963c3cda8d62fef608c68d5a327a6d1c375300394b17811f1d9d2fedd0a docs/evidence/tracking/g381_memo_digest_census_2026-09-10/summary.json
SHA-256 8b61d1a974ba13bf70b2f24e56ad082f9090425d0396a739738a1619aca51ee2 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/eye.txt
SHA-256 3f390aec94ac56c6fb7d65ddefde3c5636bb92c5d73fe682e1a3104d3167df49 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/run.log
SHA-256 8b1ad1ad92780fc86aec20c3e96ac48628e580608e61063516b07a7e865b44b9 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/lint_console.log
