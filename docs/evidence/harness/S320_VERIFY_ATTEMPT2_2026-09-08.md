VERDICT: REJECT
Candidate: d87f6047c; verifier: codex-sol; scope: S320 ACCEPTANCE RULE plus B1-B10 and Q1-Q8.
ACCEPTANCE FAIL: required N is the landed chronological-fold, whole-game, 24 h-embargo null, but this row freshly fits a median-date single-cut calibrator and admits the identity mismatch (S320_spec.md:35-39,50-58; s320_state_audit.py:173-195; S320_timestamp_artifact_audit_2026-09-08b.md:18,25).
ACCEPTANCE FAIL: VERSION b allowed only the landed route's selection-rule fix, while the candidate state changes its API, audit behavior, fit, replay, and writer (S320_spec.md:57,87-88; s320_state_audit.py:97-233).
PREMISE PASS: independently read selected parquet columns: 2829826 bytes, 465249 ticks, 1593 games, 2 derived seasons (starts 2024/2025), periods 1-6, and 271154 clock-zero ticks/share 0.582814793799; period/game_clock_s form the S309 mask and status/received_at/side/home are absent (S320_timestamp_artifact_audit_2026-09-08b.md:3-5,16).
REPRODUCTION PASS: claimed/reproduced n=313 unique pairs, 63 strata (62x5 + 1x3); audit A/NV/V = availability 0/313/0, status 273/0/40, polarity 0/313/0, duplicate 313/0/0, settlement 312/0/1; every check x stratum is present (memo:7-16; states.csv:1; audit.csv:1).
REPRODUCTION PASS: claimed/reproduced N max/change b=0/0 and c=0.337200/211; M0 b=0/0 and c=0.335000/211; 0 replay violations and 0 changed rows without a delay-window record (memo:18-23; replay.csv:1).
ARTIFACT PASS: all named paths exist; sizes/LF hashes reproduce as states 22064/6f8f617e..., audit 164770/c1ad37b3..., replay 78001/496149df..., source 2829826/5ea6498d..., prereg seal a735f99d... (memo:3-7,34-37; prereg.md:137).
ADDITIVITY FAIL: d87's CSV delta is additive and all 626 parent rows retain shared values, but versus landed master `prefix_replay` renames keyword `arm` and removes nine returned fields without aliases (master:s320_state_audit.py:126-146; candidate:s320_state_audit.py:145-164).
LOC PASS: touched s320_state_audit.py is 248 lines <=250/300; repository LOC rail passes (S320_spec.md:29,68; test_loc_rail_scope.py:5,151-177).
MEMO PASS: 42 lines <=60, EYE CHECK NONE, and a NOT VERIFIED list is present (S320_timestamp_artifact_audit_2026-09-08b.md:24,26-32).
B1 PASS: hash-ranked selection is sealed before audit and excludes no failing result (prereg.md:29-35; s320_state_audit.py:87-98).
B2 FAIL: landed return names/keyword are removed without aliases; current-reader grep found only the updated focused test (VERIFIER_CONTRACT.md:21; master:s320_state_audit.py:126-146; test_s320_state_audit.py:9-11,48-53).
B3 PASS: absent timing/polarity evidence yields NOT_VERIFIED, never ACCEPTED or quarantine (s320_state_audit.py:117-131; memo:26-28).
B4 PASS: no claim/retry lifecycle exists in the route (s320_state_audit.py:199-233).
B5 PASS: candidate reports local execution and no deployed-tree change (memo:2,32-33).
B6 PASS: no module moved/retired; sole test importer was run (test_s320_state_audit.py:9-11).
B7 PASS: deterministic whole-stratum hash sampling, not a head slice (s320_state_audit.py:87-98).
B8 PASS: replay equality is not presented as an independent calibration residual (memo:18-25,30-32).
B9 PASS: 313 unique game/state pairs across 63 nonconstant strata; source has 0 duplicate game_id/ts keys (memo:7; states.csv:1).
B10 PASS: seed=32020260908, delay=60, 5/stratum, and stated bars match the sealed values (s320_state_audit.py:12-16; prereg.md:129-132).
Q1 PASS: seal a735f99d... recomputes; prereg commit a4e4b8c95 predates first metric commit 7186cbaa4 (prereg.md:137; memo:6).
Q2 PASS: no comparative trial was charged or performance metric scored (prereg.md:118-119; memo:32).
Q3 PASS: no stated bar/threshold moved (S320_spec.md:54-62,79-88; prereg.md:129-132).
Q4 PASS: no OOS performance comparison or meta-learner is claimed; replay is an as-of identity audit (prereg.md:112-119; memo:18-25).
Q5 PASS: no AHEAD claim exists (memo:26-32).
Q6 PASS: candidate files decode as ASCII and restricted language appears only in the memo's explicit retraction context (memo:38-42).
Q7 PASS: sampled n=313 >=30 and exact sealed selection reproduces (memo:7; states.csv:1).
Q8 PASS: premise was measured before scoring and no earlier landed nonempty replay exists (S320_spec.md:20-23; prereg.md:5-10; memo:3-7).
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_s320_state_audit.py -q -p no:cacheprovider --confcutdir=tests\platformkit` -> 7 passed in 1.99s (local; sole importer file).
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_loc_rail_scope.py -q -p no:cacheprovider --confcutdir=tests\platformkit` -> 1 passed in 0.67s (local).
TEST NOTE: normal conftest setup returned 7 temp-directory ACL errors before test bodies; `/c/Users/neelj/bin/pod_run a12 -- python -m pytest tests/platformkit/test_s320_state_audit.py -q -p no:cacheprovider` could not start because Git Bash CreateFileMapping was denied, so no pod result is claimed.
CORRECTION: preserve `arm` and all landed return fields as aliases; use the exact landed N required by S320_spec.md:35-36; revert landed-route changes beyond the selection fix; regenerate replay/memo and rerun both files.
NOT VERIFIED: availability, polarity, the required landed-N replay, or normal-conftest/pod execution (memo:25-32).
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | in-game calibration | S320 | n=313 artifact replay reproduced, but N is not the specified landed chronological-fold null and the landed route is non-additive | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: the prereg seals a deterministic rule/census, but the exact selected pair list and its digest were not embedded before audit (S320_spec.md:26-28; prereg.md:29-35,137).
NEW GAP: no test exercises write_report's sealed CSV header or alias preservation; current tests inspect only in-memory prefix_replay fields (s320_state_audit.py:199-233; test_s320_state_audit.py:48-53).
