VERDICT: REJECT
Candidate: bafecb504f1d64a3c9e773e5757ca754ac6d1f01; scope is G386_spec.md:14-23 plus B1-B10 and Q1-Q8.
ACCEPTANCE PASS: attempts.csv:2-31, receiver_receipts.csv:2-31, pixel_checks.csv:2-31 and faults.csv:2-8 reproduce the permitted PARTIAL result: one control bar is unmet and not lowered.
ACCEPTANCE FAIL: G386_spec.md:22,24 requires historical identities not move and names common receipts; bafecb504 deletes common_receipts/pc_receiver_receipt.csv:1-34, while memo:3 confirms removal.
PREMISE PASS: census.csv:2-1262 independently gives 51/1,261 retained sections over 22/196 videos, including 18 live; the three named identity tools have no receiver/readback implementation (memo:5).
HEADLINE PASS: attempts.csv:2-31 gives 30/30 CAPTURED; draw.csv:2-31 gives 30 sections/21 videos and 30 full_replay_source contracts; receipts reproduce 30/30 acknowledgement, byte match, retention, PC readback and decode (memo:12-19).
RETENTION PASS: all 30 retained_path objects exist now; bounded streaming re-hash gives 30/30 matches, 2,323,546,523 bytes total, max object 100,578,787 bytes; native-frame re-decode gives 30/30 stored digests (receiver_receipts.csv:2-31; pixel_checks.csv:2-31).
ROTATION PASS: filtering rotation_recheck.csv:2-376 to the 30 sealed attempt IDs gives present counts 30/29/27/17/17 and live counts 11/11/9/0/0 at minutes 0/15/30/45/60 (memo:23).
RENDERS PASS: 30 files, 30 unique names/digests, all 1920x1080; evenly inspected a01,a07,a13,a18,a24,a30, all distinct native broadcast frames (summary.json:106-109,128-131).
NOT VERIFIED PASS: explicit list is present at memo:25-31.
LOC PASS: bafecb504 touches no .py; supporting files are 259/122/124/173 LOC and the test is 174, each <=300.
TEST PASS: `python -m pytest tests/platformkit/test_g386_pin_copy_one_pass.py -q -p no:cacheprovider` -> 14 passed in 1.39s.
IMPORTER PASS: candidate touches no module; test_g386_pin_copy_one_pass.py is the only existing test importing the four G386 modules and was run alone.
B1 PASS: every sealed attempt and every control remains named; no row is excluded (attempts.csv:2-31; faults.csv:2-8).
B2 FAIL: deleting common_receipts/pc_receiver_receipt.csv:1-34 removes its eight-field receipt schema and old-path behavior without an alias; receiver_receipts.csv is a differently named schema and memo:3 acknowledges replacement.
B3 PASS: absent, changed, short and mismatched inputs remain distinct non-CAPTURED states, never a production quarantine (g386_pin_copy.py:112-156).
B4 PASS: no claim queue is added; reused-name retries have distinct version IDs and release requires an acknowledged CAPTURED receipt (g386_pin_copy.py:156-171; faults.csv:7-8).
B5 PASS: candidate changes evidence only; memo:31 records no deployed-tree write, restart, flag or registry change.
B6 PASS: no module is moved or retired; the only deletion is the receipt artifact identified under B2.
B7 PASS: recomputed even indices are 0,2,3,...,47,48,50 across all 51 retained rows, exactly matching draw.csv:2-31 (memo:6).
B8 PASS: this infrastructure measurement fits no model and claims no residual as independent evidence (g386_prereg_2026-09-10.md:34-42).
B9 PASS: source_identity.csv:2-31 and summary.json:128-131 reproduce 30 unique sections, source digests, version IDs, render names and retained-frame digests.
B10 PASS: every bar remains byte-consistent with G386_spec.md:17-23; 6/7 controls is reported PARTIAL (memo:2,17,24).
Q1 PASS: prereg and amendment blob prefixes reproduce seals 517122d0... and 3c092fc6...; commits 7c01d57e3 and d993f48cb predate census_stamp.json:2-12.
Q2 PASS (N/A): the prereg states no scored comparison and there is no charged trial or K (g386_prereg_2026-09-10.md:34-42).
Q3 PASS: the failed control is disclosed against the unchanged exact-controls bar (memo:17,24).
Q4 PASS (N/A): no OOS comparison or meta-learner is scored (g386_prereg_2026-09-10.md:34-42).
Q5 PASS (N/A): no AHEAD result is claimed (memo:1-2).
Q6 PASS: character-built scan of all G386 text artifacts, memo and G386 ledger row returns 0 non-opaque hits (memo:33).
Q7 PASS: sampled n=30 distinct sections over 21 videos; seven constructed faults are separate (draw.csv:2-31; faults.csv:2-8).
Q8 PASS: premise census precedes the draw and measurement; 51/1,261 and 22 videos reproduce independently (memo:5-8; census_stamp.json:2-12).
CORRECTION 1: restore common_receipts/pc_receiver_receipt.csv byte-for-byte from 23cd2e397 and retain its old path as the historical alias; do not count it in the A1 result.
CORRECTION 2: memo:3 say the old receipt is preserved but excluded; memo:39 add its a08a66f6... digest beside .gitkeep. No measured number changes.
2026-09-11 | tracking | G386 | premise 51/1,261 retained over 22 videos; sealed 30/21 draw reproduced; 30/30 captures and retained-object readbacks; native frames 29 MATCH plus 1 ORIGINAL_ABSENT; controls 6/7; historical receipt removed | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: contract A1 cannot run this lane test in master before landing because master 6e849d214 lacks the test and all four G386 modules; this verification ran the candidate worktree test.
NEW GAP: reader_contract.csv:2-114 archives matched readers and zero-reader sentinels but not the full scanned-path census, so memo:27's 426-module denominator is not independently reconstructible.
