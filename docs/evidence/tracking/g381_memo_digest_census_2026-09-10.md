VERDICT: DONE

# G381 memo digest census -- measure phase run 4

Population ref: `627cdc63b7d0a3f82b6b6afb334df81414eb4581`, computed by `git merge-base track-a7 master`; each memo uses its first-add master commit.
A2 applied whole-landing-tree basename lookup, raw/CRLF SEAL forms, and the ten-candidate cap; finite blob reads, object-id caching, and progress logging remain.

PREMISE: 380 digest-carrying memos / 2,000 digest tokens / 1,375 distinct tokens.
The complete population is 627 memos; 380 >= 30, so the premise holds.
All 2,000 tokens are classified; 533/2,000 (26.65 pct) are non-UNRESOLVED.

| Class | Count | Share |
|---|---:|---:|
| IDENTIFIES_AT_LANDING | 309 | 15.45 pct |
| IDENTIFIES_AT_HEAD_ONLY | 0 | 0.00 pct |
| CRLF_ONLY | 0 | 0.00 pct |
| ARTIFACT_UNNAMED | 222 | 11.10 pct |
| OBJECT_ID | 2 | 0.10 pct |
| UNRESOLVED | 1,467 | 73.35 pct |

UNRESOLVED reasons: artifact never committed 1,149; token is not a digest 193;
pod-only or absolute path 111; basename ambiguous 14. `unresolved.csv` names all.
Worst ten rows (UNRESOLVED; reasons):
- `g325_prereg_attempt2_2026-09-07.md` 126; artifact never committed 125, token is not a digest 1.
- `g327_prereg_2026-09-08d.md` 125; artifact never committed 125.
- `g322_prereg_attempt2_2026-09-07.md` 111; artifact never committed 110, token is not a digest 1.
- `g323_nonplayer_boxes_attempt2_2026-09-07.md` 30; artifact never committed 24, token is not a digest 6.
- `g324_apache_arm_rebudget_2026-09-07.md` 24; artifact never committed 13, pod-only or absolute path 7, token is not a digest 4.
- `g302_amateur_vs_resolution_attribution_2026-09-07.md` 22; token is not a digest 7, artifact never committed 6, pod-only or absolute path 5, basename ambiguous 4.
- `g322_oversized_boxes_attempt2_2026-09-07.md` 21; artifact never committed 18, token is not a digest 3.
- `g303_production_resolution_recall_2026-09-07.md` 19; token is not a digest 11, artifact never committed 7, pod-only or absolute path 1.
- `g311_apache_detector_arm_attempt2_2026-09-07.md` 18; artifact never committed 18.
- `g325_offframe_boxes_attempt2_2026-09-07.md` 17; artifact never committed 13, token is not a digest 4.

Run 1 (Git object IDs), run 2 (hung), and run 3 (pre-A2) are superseded and retained respectively under `run1_git_object_ids/`, the historical run record, and `run3_pre_A2/`; no archive was deleted.
The independent rerun at `C:/Users/neelj/AppData/Local/Temp/g381_rerun4/` was byte-identical for census.csv, per_row.csv, unresolved.csv, summary.json, eye.txt, and run.log.
The required G372 checks pass: A3 SEAL `3ed74708...` and `track_daemon.py` `9747d9a0...` identify at landing.
Diagnostic only: the unwired linter scanned 627 real memos and reported 1,402 violations (exit 1 expected).
Focused validation: `tests/platformkit/test_g381_memo_digest_census.py` passed 17 tests.
Q6 automated vocabulary scan built from character codes: 0 non-exempt hits in every changed or written file after fix 1b (copied register prose in per_row.csv is redacted with a marker plus the source-row digest; one row affected).

NOT VERIFIED:
- Bytes outside this Git history, including pod-only and absolute-path artifacts.
- Whether any unresolved historical token identifies an artifact not committed at the measured ref.
- The proposal linter as enforcement; it has no production caller.

Wall time: production census completed below 20 minutes; independent rerun 00:06:42.
SHA-256 b06b744caed08faeef55c909ad7984ba2d233e8a3c20a1b330b55a11e0292f8d docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_2026-09-10.md
SHA-256 481390c52cf868e4bf2a7b0ff8c387996164f135ec225ff15354575069398889 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_2026-09-10.md (bytes above SEAL)
SHA-256 940674af3ea31cc5203ab58f36aef68cd9d7eb4a729a309aeb3c0c13c5a14b80 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_amendment_A1_2026-09-10.md
SHA-256 172893096eecc7b3f37fb7c1cf60bb68b1da4acde4fc6f6d0156018a644a12e6 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_amendment_A1_2026-09-10.md (bytes above SEAL)
SHA-256 e03451b7307e9b5e0d52d27d69d38674e361ea7b0d326e84bf3bba1070bacfa0 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_amendment_A2_2026-09-10.md
SHA-256 6e35de55800cc325ecdd57bf6d94015d2d2021477a52fbb6bb5c229286eb7b06 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/g381_prereg_amendment_A2_2026-09-10.md (bytes above SEAL)
SHA-256 35fc4a634372f8c3e723946cbb51869e2941391d8ba3fbd22c92962054494341 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/census.csv
SHA-256 0c105cb0ab43b2dca820e53c12f8fe8caa99ba8397bd282e51c13d2a3eb1fab8 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/per_row.csv
SHA-256 5e546dbc496dfc8322e47f4ac028dd83ecc4ee277cbbc10f1fd873b25c1f1827 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/unresolved.csv
SHA-256 29201ff5c5cf95306f359bf7de3daab0711185fbc0a92b5d8e814b54a0517309 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/summary.json
SHA-256 5cb65500a7910bf762960de57b83bd1e0fd9e7d6730eebc762a64d3a03ee640b docs/evidence/tracking/g381_memo_digest_census_2026-09-10/eye.txt
SHA-256 01b1d6aaa3e6c196c130415826714344edc85703e051d8c4a289268a18ae8f37 docs/evidence/tracking/g381_memo_digest_census_2026-09-10/run.log
SHA-256 72316717f6cf0e3837d62839f201752537ba180d599eb8ffd5c88439dd28282a docs/evidence/tracking/g381_memo_digest_census_2026-09-10/PROPOSED_digest_convention.md
