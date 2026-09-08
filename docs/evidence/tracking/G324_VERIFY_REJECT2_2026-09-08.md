VERDICT: REJECT
Candidate: 0fef385fb1bd204f433e9802c0f836baa77ba89d; verification snapshot: 2026-09-08.
FAIL ACCEPT-evidence: the required memo is 65 lines, above its 60-line cap (G324_spec.md:143; g324_apache_arm_rebudget_2026-09-07.md:65).
PASS ACCEPT-premise/bar: sealed 3,600 s; pinned wheel size/hash; all three steps rc=0; gate cleared at 267.8 s; no proxy bar or arm ranking (g324_summary.json:7; memo:1-13).
PASS ACCEPT-metrics/n/non-tautology: all six 40-frame cells, every proxy, full raw rows >=200, unique tail-spanning indices, and zero-box frames retained (memo:15-36; g324_summary.json:48).
PASS ACCEPT-sign/SCREENING/eye: every direction and caveat is explicit; no labels, renders, eye check, or arm ranking (memo:1-3,32-34).
PASS ACCEPT-resolved/checkpoint/licences: labeled seven-package probe and ops import exist; checkpoint guard precedes load; URLs and bytes are named (memo:9,13; g324_import_gate_labeled.txt:11; g324_apache_arm_rebudget.py:193).
PASS ACCEPT-must-not-move/NOT VERIFIED: protected hashes match, candidate touches no gated tree, and the list exists (memo:40,46-54; g324_summary.json:383).
REPRODUCED premise claimed/measured: 267.8/267.8 s; steps total 266.6 s plus 1.2 s wrapper/hash time; wheel 35,202,838 B and hash match (g324_summary.json:7-36).
REPRODUCED second premise claimed/measured: 416.8/416.8 s; steps total 415.3 s plus 1.5 s wrapper/hash time (g324_premise_run2_transcript.txt:21).
REPRODUCED inherited build claimed/measured: 2,921/2,921 s = 1,898 + 1,023 from timestamps (route_i5_mmcv210_build.txt:12,35,38,59; memo:11).
REPRODUCED boxes Y/R and ids Y/R: 343/741 and 321/653; 320/541 and 265/446; 326/729 and 283/608; median length 1 throughout (six raw CSVs; memo:25-30).
REPRODUCED agreement Y-in-R/R-in-Y: .9416909621/.4358974359; .93125/.5508317930; .8926380368/.3991769547, with 323/298/291 matches (six raw CSVs; memo:32).
REPRODUCED timing/VRAM: single 152.48/2947.78,177.27/2649.94,124.67/2127.75; batch 235.08/2092.36,80.19/2489.87,42.66/1950.11; all six VRAM values match (g324_summary.json:95; memo:25-30).
TEST: python -m pytest tests/platformkit/test_g324_rows.py -q -> 6 passed in 1.51s.
TEST: python -m pytest tests/platformkit/test_loc_rail_scope.py -q -> 1 passed in 0.67s.
PASS importer/LOC: the sole test importer is test_g324_rows.py:96; module is 213 lines, below 300 (g324_apache_arm_rebudget.py:1-213).
PASS B1: full raw rows and all decoded frames form denominators; no exclusion (memo:19,36; g324_summary.json:48).
FAIL B2: mismatch previously emitted a distinct verdict status, now removed without an alias; this changes status behavior despite no reader hit (0fef385fb~1:scripts/platformkit/tracking/g324_apache_arm_rebudget.py:65; g324_apache_arm_rebudget.py:99-108).
PASS B3: no absent-evidence quarantine is introduced (g324_apache_arm_rebudget.py:99-108,184-187).
PASS B4: no claim/retry lifecycle is introduced (memo:3,60).
PASS B5: compute stayed in pod scratch and deployed hashes remained fixed (memo:40).
PASS B6: no module moved or retired; the only test importer passes (test_g324_rows.py:92-119).
PASS B7: each frame list has 40 unique indices spanning zero through the measured tail (memo:15-19; g324_summary.json:48).
PASS B8: no fit or independent score is claimed (memo:3,46-54).
PASS B9: constant track length is disclosed as uninformative; decoded-frame denominators vary honestly (memo:23-32,50).
PASS B10: 3,600 s, IoU .5/link .3, confidence .3, 40 frames and batch 8 remain sealed (g324_prereg_2026-09-07.md:10-23,111-121; g324_apache_arm_rebudget.py:32).
PASS Q1: prereg-only commit fac1ba8f0 predates measurement; LF-normalized seal reproduces 19154bcf48... (g324_prereg_2026-09-07.md:1-8,165-167).
PASS Q2: no charged trial or K-dependent metric exists (memo:1-3).
PASS Q3: the premise bar and every proxy threshold match the prereg/spec/artifact (g324_prereg_2026-09-07.md:10-23,111-121; g324_summary.json:4-8).
PASS Q4: no OOS score or meta-learner exists (memo:3,46-54).
PASS Q5: no AHEAD claim exists; one-corpus scope is explicit (memo:3,54).
PASS Q6: candidate-added text has zero restricted-language and barred-number hits (candidate diff; memo:60-65).
PASS Q7: sampled n=40 per game exceeds 30; each enumeration is unique and spans its declared set (g324_summary.json:48; memo:19).
PASS Q8: wheel size/hash/import premise was measured after prereg and before proxies (g324_summary.json:7-48; memo:5-9).
MINIMAL DIFF: delete any five blank memo lines so the unchanged content fits the 60-line evidence cap.
MINIMAL DIFF: on mismatch add `reuse_status` carrying the former status as an alias, retain `verdict` for the premise outcome, and assert both in test_g324_rows.py:113-119.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | all | G324 | 267.8 s premise and six proxy cells reproduce; mismatch status is not additive and memo is 65 lines | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: G324-FALLBACK-INSTALL-IDENTITY - the source path targets a populated prefix without replacement and gate_ok ignores build-step rc, so a stale import can mask a failed build; the real mismatch path remains unexercised (g324_apache_arm_rebudget.py:74-108; test_g324_rows.py:105-119).
