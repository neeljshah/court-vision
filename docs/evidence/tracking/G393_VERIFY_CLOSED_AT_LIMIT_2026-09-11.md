VERDICT: CLOSED AT LIMIT
Candidate: `38f2ade9cde1683e3ee99764973cb0965c7e83ca`; full G393 evidence series through this memo-only tip audited.
ACCEPTANCE PREMISE PASS - claimed/measured split failures 30/30, equals recovery 30/30, ordinary equality 30/30 (`G393_spec.md:5`; `test_g393_leading_hyphen_game_id.py:22-39`).
ACCEPTANCE LEADING PASS - claimed/measured proposed recovery 30/30 and original failures 30/30 (`g393_leading_hyphen_game_id_2026-09-11.md:21`; `summary.json:2-11`).
ACCEPTANCE CONTROL FAIL - claimed/measured ordinary equality 30/30 but sealed controls only 5/6; `--` parses as `[]`, so the proposal is rejected (`G393_spec.md:20`; memo:23,33-36).
ACCEPTANCE ISOLATION PASS - one caller hunk, current source hashes reproduce, and production retains the split pair (`G393_spec.md:21`; `PROPOSED_g393_game_id.diff:1-11`; `track_daemon.py:96`).
REPRODUCTION PASS - claimed/measured: split 0/30 leading and 2/6 controls; separator 0/68; equals 30/30 leading, 30/30 ordinary, 5/6 controls, 2/2 extras; 0 eligible forms (`forms_summary.json:22-66`; memo:29-31).
UNIQUENESS/EYE PASS - 66/66 unique sealed ids and ordinals; 66 cards plus even leading ordinals 1,13,25,37,49 and all controls (`cases.csv:1-67`; `forms_summary.json:15-29`).
TEST PASS - `python -m pytest tests/platformkit/test_g393_leading_hyphen_game_id.py -q` -> 4 passed in 3.29s.
IMPORTERS PASS - the sole test importer of all three touched G393 modules is the 4-test file above (`test_g393_leading_hyphen_game_id.py:7-9`).
LOC PASS - touched Python files are 244, 153, 165, and 88 lines, each <= 300 (`g393_finish.py:1`; `g393_parser_harness.py:1`; `g393_prepare.py:1`; `test_g393_leading_hyphen_game_id.py:1`).
ADDITIVITY PASS - no field, status, module, or reader behavior is renamed or removed; the production proposal is unapplied (`memo:43`; candidate name-status).
NOT VERIFIED PASS - the memo explicitly lists live routing, attribution, deployed identity/composition, and sibling callers (`memo:53-58`).
EVIDENCE FAIL - all specified bundle paths exist, but the named premise snapshot is absent and memo digest manifest entry 164 is stale; 168/169 ordinary hashes reproduce (`memo:11,60`; `digests.txt:164`).
B1 PASS - all 66 sealed cases remain in the receipts, including the failed control (`cases.csv:1-67`; `parsed_before_after.jsonl:1-66`).
B2 PASS - additive-only modules/artifacts; no existing schema or reader changed (`PROPOSED_g393_game_id.diff:1-11`; memo:43).
B3 PASS - no evidence gate or quarantine behavior is introduced (`memo:5,43`).
B4 PASS - no claim or retry lifecycle is introduced (`memo:5,43`).
B5 PASS - no pod or deployed-tree write occurred; the proposal is applied nowhere (`memo:5,43`).
B6 PASS - no module moved or retired; full-package imports resolve in the passing test (`test_g393_leading_hyphen_game_id.py:7-9`).
B7 PASS - the full sealed universe has cards and the form cards span the leading set evenly (`memo:50`; `forms_summary.json:15-29`).
B8 PASS - direct parser construct; no fit or residual comparison exists (`preregistration.md:1-10`).
B9 PASS - 30 leading, 30 ordinary, and 6 supplemental ids are each unique (`cases.csv:1-67`).
B10 PASS - the six-control bar stays sealed and the failing result is not excluded (`preregistration.md:6-8`; `g393_finish.py:75-97`).
Q1 PASS - seal `4787b4c8477a66fe8427ca0d46e1ed5b9fafa4ec776972e05f74bfe976f20d6c` reproduces and commit `e36198383` precedes final measurement `b91564a41` (`preregistration.md:11`; memo:15).
Q2 PASS - no charged trial, launch K, or multiplicity mechanism applies (`preregistration.md:1-10`).
Q3 PASS - the six-control bar is unchanged; failure closes the caller-only row at its sealed limit with no adoption (`G393_spec.md:20`; memo:3,43).
Q4 PASS - no OOS forecast or meta-learner is scored (`preregistration.md:1-10`).
Q5 PASS - no advancement status or second-corpus claim is made (`memo:1-60`).
Q6 PASS - independent focused test scans 166 text artifacts and returns 0 hits (`forms_summary.json:67-68`; test:77-88).
Q7 PASS - this is an exhaustive 66-case CONSTRUCT, not a sampled metric (`G393_spec.md:7-16`; `cases.csv:1-67`).
Q8 PASS - current caller/parser premise independently replayed before verdict: 30/30 split failures, 30/30 equals recovery (`track_daemon.py:96`; `run_clip.py:424`).
CORRECTION MINIMAL DIFF memo:3: `- VERDICT: PARTIAL` / `+ VERDICT: CLOSED AT LIMIT`.
CORRECTION MINIMAL DIFF RESULTS_LEDGER.md:747: `- PARTIAL` / `+ CLOSED AT LIMIT`; retain the measured counts.
CORRECTION MINIMAL DIFF memo:11: remove the unavailable snapshot's 12/1928, 12/1554, and 348/1928 claims; retain reproduced G375 3/1031.
CORRECTION MINIMAL DIFF digests.txt:164: `- 204c3f8f...` / `+ f15fbaf2...` for the final memo bytes.
2026-09-11 | tracking | G393 | split 0/30 leading; equals 30/30 leading and 30/30 ordinary but 5/6 sealed controls; 0 eligible caller forms | CLOSED AT LIMIT (verified: codex-sol, contract A/B/Q)
NEW GAP: archive the exact whole-ledger snapshot cited by memo:11; `data/pod_backup_2026-09-10/track_daemon_ledger.jsonl` is absent, so its three counts cannot be independently reproduced.
NEW GAP: refresh `digests.txt:164` after memo changes and correct `G393_spec.md:3` identity wording; Git LF source matches the recorded deployed digest (`memo:51`).
NEW GAP: linked-worktree Git metadata is outside the writable root; targeted `git add` and `lane_commit.py` both failed at `index.lock`, so an external path-specific committer is required.
