VERDICT: REJECT
Candidate `8fa8b7d65`; full stat/diff inspected. ACCEPTANCE FAIL: reproduced 3/6 stage receipts and 1/2 connection receipts, below 6/6 and 2/2 (`S313_attempt2_artifact/route_status.md:19-22`; `S313_spec.md:24-26`).
ACCEPTANCE FAIL: S71 remains 5 failed/46 passed against <=1, so FINISHED is blocked (`S313_answers_roundtrip_attempt2_2026-09-08.md:31-33`).
ACCEPTANCE FAIL: answer as_of is ledger mtime 2026-09-08T05:51:54Z, later than oldest required receipt 2026-09-08T05:44:15Z; guard checks ledger older than receipt and resolver emits ledger mtime (`receipt_guard.py:25,61`; `resolver_registry.py:841-845`).
REPRODUCTION PASS: S293 archive is 7,071,878 bytes; 465249 rows, 308756 unique tail (game_id,ts), 1590 games; candidate/null losses 0.030833806300609553/0.028761870222461097, difference -0.002071936078148453 vs claimed -0.002071936078148454 (`test_s313_answers_label_survival.py:91-103`).
CAPABILITY PASS: claimed/got NBA 1814/563/25/60, MLB 39162/910/1/1; soccer 25834/16322/9512/16322; tennis 41886/33766/8120/33685 (`completion_manifest.json:2-40`).
FIELD/REPEAT PASS: R1-R4 findings equal committed envelopes, four labels survive, R5 withholds its numeric claim, pass1==pass2; 10/10 listed hashes and 6/6 extra named paths exist (`completion_manifest.json:93-133`; `sha256sums.txt:1-10`).
A1 PASS: master has no S313 test to replay; candidate worktree test passed. A2/A3/A4 PASS: archive recomputed, S-row has no sampling, 8/8 route rows, 5/5 questions, 4/4 sports and 308756/308756 tail keys unique.
A5 PASS: readers grepped; contract_client fields exercised, MCP envelope premise rerun, aggregate readers checked. A6 N/A by verifier-only instruction. A7 PASS: all memo evidence paths checked.
B1 PASS: exhaustive constructs retain every failed/unavailable row. B2 PASS: no key/status removed; required n=0 to None change is consumed by contract_client.
B3 PASS/B4 PASS: absent input returns no_data or measured NOT_TESTABLE with no numeric claim; no claim lifecycle changed.
B5 PASS/B6 PASS: no deployed-tree write, move, retirement or orphan; pod launcher never contacted pod.
B7 PASS/B8 PASS/B9 PASS: exhaustive construct, no new fit, and unique stage/connection/route/sport/tail units.
B10 FAIL: candidate raises the shared resolver LOC allowance 1323 to 1330 while master remains 1323 (`8fa8b7d65:tests/platformkit/test_loc_rail_scope.py:18`).
Q1 FAIL: the prereg says its hash is recorded in the memo but does not embed the seal required by Q1; the value appears only in later artifacts (`S313_answers_roundtrip_attempt2_prereg_2026-09-08.md:101-102`; `completion_manifest.json:135`).
Q2 PASS: uncharged construct. Q3 PASS: S313's 6/6, 2/2, <=1-red and fixed calibration bars were not lowered.
Q4 PASS/Q5 PASS: no new OOS fit, meta-learner result or AHEAD result. Q6 PASS: independent added-byte scan found 0 restricted-vocabulary and 0 restricted-figure hits.
Q7 PASS: all construct cases enumerated. Q8 PASS: premise reproduced as S71 5/46 and S275 8/8 exact readings with flip delta 0 before adjudication.
LOC FAIL: touched Python LOC = 204,170,98,1330,204,172; resolver exceeds 300 and restored repo rail fails 1 test at 1330 > 1323 (`test_loc_rail_scope.py:18,191`).
REPORT PASS: candidate memo has a NOT VERIFIED list (`S313_answers_roundtrip_attempt2_2026-09-08.md:49-50`).
TEST: `python -m pytest tests/platformkit/test_s313_answers_label_survival.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 10 passed.
TEST: `python -m pytest tests/platformkit/mcp_server/test_envelope_contract.py -q -p no:cacheprovider` -> 46 passed, 5 failed.
TEST: `python -m pytest scripts/platformkit/eval_gate/test_s275_key_explicit_consumers.py -q -p no:cacheprovider` -> 1 passed.
TEST: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 failed.
TEST: `python -m pytest tests/platformkit/analytics_verify/test_answers.py -q -p no:cacheprovider` -> 15 passed; `python -m pytest tests/platformkit/analytics_verify/test_system_map.py -q -p no:cacheprovider` -> 15 passed.
TEST: `python -m pytest tests/platformkit/answers/test_atlas_resolver.py -q -p no:cacheprovider` -> 8 passed; `python -m pytest tests/platformkit/answers/test_prediction_quality_resolver.py -q -p no:cacheprovider` -> 6 passed.
TEST: `python -m pytest tests/platformkit/mcp_server/test_edge_refusal.py -q -p no:cacheprovider` -> 16 passed.
CHECK: `python -m scripts.platformkit.analytics_showcase.mechanism_ledger_export --check` -> 291; `python -m scripts.platformkit.analytics_showcase.mechanism_survival --check` -> 291.
POD COMMAND, each file separately: `/c/Users/neelj/bin/pod_run a22 -- python -m pytest <file> -q -p no:cacheprovider`; `<file>` = `scripts/platformkit/answers/test_{answer_consistency_intel,answer_consistency_mlb,answer_consistency_nba,answer_consistency_soccer,answer_consistency_tennis,calibration_scoreboard_regex,claims_resolver,edge_calibration_guards,effect_graph,leaderboard_resolver,leaderboard_team_scope,mechanism_effect,player_compare,resolver_registry_routing}.py`; all launcher rc 256 before pod contact, no pytest count.
CORRECTIONS: restore LOC allowance 1330->1323 and extract enough resolver code to meet the rail; emit as_of=min(ledger, named receipts); create a prereg with an embedded prefix seal before rerun; do not close S313 until the missing 3 stages, 1 connection and S71 bar pass.
2026-09-08 | harness-to-answers calibration | S313 | 3/6 stage receipts, 1/2 connection receipts; freshness and shared LOC rails fail | REJECT (verified: codex-sol, contract A/B/Q)
NOT VERIFIED: 14 pod-routed answer importer files; live resident connectivity; missing DATA, SIGNALS, PREDICTIONS and CONNECTION 1 receipts.
NEW GAP: S313-POD-LAUNCHER-BLOCKED - Git Bash exits with CreateFileMapping Win32 error 5 before `/c/Users/neelj/bin/pod_run` can contact the pod.
NEW GAP: S313-VERIFY-COMMIT-BLOCKED - linked-worktree git metadata is outside the writable sandbox; direct `git add` and `lane_commit.py` both fail on index.lock, so an external path-specific commit is required.
