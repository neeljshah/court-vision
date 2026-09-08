VERDICT: REJECT
Candidate: 89bba69fd; verification snapshot: 2026-09-07.
FAIL ACCEPT-metric/bar: premise false was declared at 1,736/1,800 s while the compatible build had been killed still compiling at 1,643 s; the sealed 30-minute condition was never observed (g311_apache_detector_arm_2026-09-07.md:3,9,20-22; g311_premise3.txt:1-2,13-29; G311_spec.md:36-46,86-96).
PASS ACCEPT-before: parent-tree census found 0 RTMDet runtime backends, 2 concrete backends, and 1 non-AGPL backend, YoloxOnnxBackend (scripts/platformkit/detection/shim.py:110-212; MODEL_LICENSES.md:1-14; G311_spec.md:91-93).
PASS ACCEPT-n: no arm ran and no proxy denominator arose after the premise stop; the three intended clips are named (g311_apache_detector_arm_2026-09-07.md:37-40; G311_spec.md:97-98).
PASS ACCEPT-eye: no renders, labels, or detector comparison are claimed (g311_apache_detector_arm_2026-09-07.md:3-7,37; G311_spec.md:99-100).
PASS ACCEPT-must-not-move: candidate adds nine files and appends two lines only; protected trees and existing thresholds are unchanged (g311_apache_detector_arm.py:1-10; G311_spec.md:101-104).
REPRODUCED: claimed elapsed 1,736 s equals 22:38:51Z minus 22:09:55Z; it is 64 s short of 1,800. The active build stopped at 1,643 s, leaving 157 s (g311_apache_detector_arm_2026-09-07.md:3,9; g311_premise3.txt:1-2).
REPRODUCED: the 4,314-byte LF-normalized prereg prefix hashes to df8cfa89e76a05e5bfb5d57ecf9998289761f79efa051a44b4a12619bc145eff; the log reports checkpoint 224,299,609 bytes and SHA-256 229f527ca88498e8894a778a62a878a322b4a3ea2cae09ea537d34b7e907792b (g311_prereg_2026-09-07.md:86-87; g311_premise2.txt:33-36).
TEST: `python -m pytest tests/platformkit/test_g311_proxies.py -q` -> 7 passed in 1.63s (test_g311_proxies.py:20-81).
TEST: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 1.09s (test_loc_rail_scope.py:1-28).
PASS reader/LOC: exhaustive test import scan found only test_g311_proxies.py; touched Python files are 256 and 81 lines, both <=300 (test_g311_proxies.py:9-17; g311_apache_detector_arm.py:1-256).
PASS NOT VERIFIED: the memo explicitly lists the unfinished build, unloaded checkpoint, and unrun video harness (g311_apache_detector_arm_2026-09-07.md:56-62).
PASS B1: no proxy rows were filtered or scored (g311_apache_detector_arm_2026-09-07.md:3-7,37).
PASS B2: schema and reader behavior are additive; no field or status was renamed or removed (g311_apache_detector_arm.py:227-250; test_g311_proxies.py:9-17).
PASS B3: no absent-evidence quarantine or production gate was added (g311_apache_detector_arm.py:214-252).
PASS B4: no claim or retry lifecycle changed (g311_apache_detector_arm.py:214-252).
PASS B5: pod work stayed in per-worktree scratch and the deployed tree was untouched (g311_apache_detector_arm_2026-09-07.md:10-12,45-49).
PASS B6: no module, import, test, or command was moved or retired (g311_apache_detector_arm.py:1-10; test_g311_proxies.py:1-17).
PASS B7: no rows or renders were sampled after the premise stop (g311_apache_detector_arm_2026-09-07.md:3-7,37).
PASS B8: no model fit or residual is evidence here (g311_apache_detector_arm_2026-09-07.md:56-62).
PASS B9: no proxy denominator exists; elapsed seconds are direct clock readings (g311_premise.txt:1-12; g311_premise3.txt:1-2,29).
PASS B10: no existing harness threshold changed; added IoU 0.5 matches the spec (g311_apache_detector_arm.py:25-26; G311_spec.md:64-69).
PASS Q1: no scored comparison exists; the embedded prereg seal independently reproduces (g311_prereg_2026-09-07.md:72-87).
PASS Q2: no charged trial or K-dependent metric exists (g311_apache_detector_arm_2026-09-07.md:3-7).
FAIL Q3: the effective premise window ended at 1,736 s, not the sealed 1,800 s, with an eligible route still unresolved (g311_apache_detector_arm_2026-09-07.md:3,20-22; g311_premise3.txt:1-2; G311_spec.md:36-46).
PASS Q4: no OOS score or meta-learner exists (g311_apache_detector_arm_2026-09-07.md:3-7,37).
PASS Q5: no AHEAD claim exists (g311_apache_detector_arm_2026-09-07.md:3-7).
PASS Q6: restricted-language and retracted-figure scans are clear (g311_apache_detector_arm_2026-09-07.md:1-62).
PASS Q7: no sampled or scored metric exists; reproduction replaces the eye check (g311_apache_detector_arm_2026-09-07.md:3-7,37).
PASS Q8: parent-tree premise census was rerun first and matches the stated backend counts (scripts/platformkit/detection/shim.py:110-212; G311_spec.md:91-93).
MINIMAL CORRECTION: no text-only diff can cure the early stop; rerun route (i) through elapsed >=1,800 s or a terminal error, then update memo:3,9,20-22 and its ledger row from the new artifact.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-07 | all | G311 | premise-false evaluation stopped at 1,736/1,800 s; compatible build terminated still compiling at 1,643 s with 157 s remaining | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: G311-EVIDENCE-PATH - memo:21 names route_i3_mmcv210_build.log, but the committed file is route_i3_mmcv210_build.txt.
NEW GAP: G311-MEMO-LIMIT - g311_apache_detector_arm_2026-09-07.md is 62 lines versus the <=60 evidence limit at G311_spec.md:108.
NEW GAP: G311-PROBE-ARCHIVE - memo:42-46 summarizes GPU and disk probes, but the verbatim outputs required by G311_spec.md:108-110 are not archived.
NEW GAP: G311-HARNESS-RAILS - g311_apache_detector_arm.py:179-204 times warm-up calls, and :236 silently drops failed decodes; a future proxy run would not meet G311_spec.md:59-60,68.
NEW GAP: G311-ASCII-LOGS - g311_premise.txt and g311_premise2.txt contain 84 non-ASCII code points despite G311_spec.md:118.
