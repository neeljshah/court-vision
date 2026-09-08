VERDICT: REJECT
Candidate: 6dc55b929765bd9a5093083aa092ca34c8f45ca1; verification snapshot: 2026-09-08.
FAIL ACCEPT-metric/resolved versions: the gate prints only mmcv/mmdet; the Python/numpy/cv2/torch probe is four unlabeled values, and resolved runtime mmengine is not printed (G324_spec.md:113-115,129; g324_summary.json:22-31; g324_preflight1.txt:25-26).
PASS ACCEPT-premise/bar: sealed 3,600 s, wheel 35,202,838 B and matching SHA-256, all three commands rc=0, gate clear at 267.8 s; no proxy bar or arm ranking (g324_summary.json:7-36; memo:1,3,7).
PASS ACCEPT-before: G311's 1,800 s close and inherited 2,921 s build are stated separately; production remains unchanged (memo:3,9,38; G324_spec.md:121-124).
PASS ACCEPT-proxies/n: all six cells name 40 decoded frames, every proxy, >=200 full raw rows, one corpus and one seed (memo:17,19-34,52; g324_summary.json:48-385).
PASS ACCEPT-sign/SCREENING: every proxy direction, consistency caveat, symmetric ignorance and no arm ranking are explicit (memo:1,3,30,44-52).
PASS ACCEPT-eye/must-not-move: no render/eye claim; protected hashes match before/after and candidate changes only evidence files (memo:3,38; g324_before_hashes.txt:1-2; g324_after_probes.txt:2-12).
PASS ACCEPT-non-tautology: 40 unique evenly spaced indices per game; zero-frame counts Y/R are 0/0, 1/1, 1/0 and remain in denominators (memo:17,23-28,34; g324_summary.json:48-385).
PASS ACCEPT-evidence: exact 56-line memo path, NOT VERIFIED list, six CSVs, summary/probes/tail and all memo artifact hashes exist and reproduce (memo:44-54; G324_spec.md:143-151).
REPRODUCED premise claimed/measured: 267.8/267.8 s wall; command sum 266.6 s plus 1.2 s wrapper/hash time; wheel size/hash match and gate rc=0 (g324_summary.json:8-36).
REPRODUCED inherited build claimed/measured: 2,921/2,921 s = 1,898 + 1,023 from timestamps (g311_premise_artifact/route_i5_mmcv210_build.txt:12,35,38,59-64; memo:9).
REPRODUCED boxes Y/R and ids Y/R: 343/741 and 321/653; 320/541 and 265/446; 326/729 and 283/608; median length 1 throughout (six raw CSVs; memo:23-28).
REPRODUCED agreement Y-in-R/R-in-Y: .9416909621/.4358974359; .93125/.5508317930; .8926380368/.3991769547, with 323/298/291 matches (six raw CSVs; memo:30).
REPRODUCED single ms Y/R 152.48/2947.78,177.27/2649.94,124.67/2127.75; batch-8 235.08/2092.36,80.19/2489.87,42.66/1950.11; VRAM values match (g324_summary.json:95-385; memo:23-28).
TEST: python -m pytest tests/platformkit/test_g324_rows.py -q -> 5 passed in 0.94s.
PASS importer/LOC/additivity: sole G324 module importer is test_g324_rows.py:16; candidate touches no .py, renames/removes nothing, and only appends ledger/evidence; row modules are 179/138 LOC (RESULTS_LEDGER.md:496; memo:40).
PASS B1: full raw rows and all decoded frames form the denominators; no exclusion (memo:17,34; g324_summary.json:48-385).
PASS B2: no field, status or reader behavior is renamed/removed; the ledger change is append-only (RESULTS_LEDGER.md:496).
PASS B3: no production gate or absent-evidence quarantine changes (memo:3,38).
PASS B4: no claim/retry lifecycle changes (memo:3,38).
PASS B5: compute is recorded under pod scratch and deployed hashes remain fixed (memo:38; g324_after_probes.txt:2-12).
PASS B6: no module is moved/retired; the sole row importer passes (test_g324_rows.py:16-22).
PASS B7: each list has 40 unique indices spanning zero to the measured tail, not a head slice (g324_summary.json:48-385).
PASS B8: no fitted residual or independent score is claimed (memo:3,44-52).
PASS B9: constant track length is disclosed as uninformative; decoded-frame denominators are non-degenerate (memo:17,23-28,48).
PASS B10: 3,600 s, IoU .5/link .3, confidence .3, 40 frames and batch 8 match the seal/spec (g324_summary.json:4-8; g324_apache_arm_rebudget.py:31; g324_arms.py:25).
PASS Q1: prereg was committed alone before run time; LF-normalized seal independently reproduces 19154bcf48... (g324_prereg_2026-09-07.md:1-13,165-167; memo:5).
PASS Q2: no charged trial, K or K-dependent metric exists (memo:1-3).
PASS Q3: 3,600 s and every proxy threshold match prereg/spec/artifact (g324_prereg_2026-09-07.md:10-23,111-121; g324_summary.json:4-8).
PASS Q4: no OOS score or meta-learner exists (memo:3,44-52).
PASS Q5: no AHEAD claim exists; one-corpus scope is explicit (memo:3,52).
PASS Q6: candidate-added prose and ledger have zero standalone restricted-language or barred-figure hits (memo:1-56; RESULTS_LEDGER.md:496).
PASS Q7: sampled n=40 per game exceeds 30 and enumeration is unique/exhaustive (g324_summary.json:48-385; memo:17).
PASS Q8: run-time wheel size/hash/import premise is measured after the sealed prereg and before proxies (g324_summary.json:7-48; memo:5-7).
MINIMAL DIFF: g324_apache_arm_rebudget.py:33 import mmengine, cv2, numpy and torch in the gate and print labeled sys/mmcv/mmdet/mmengine/cv2/numpy/torch versions; rerun the premise probe and append corrected evidence without rewriting ledger history.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | all | G324 | 267.8 s premise and six proxy cells reproduce; resolved runtime mmengine was not printed and the environment probe was unlabeled | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: G324-SECOND-PREMISE-DURABILITY - the extra 416.8 s run appears only in memo/ledger, with no committed transcript (memo:7,42; RESULTS_LEDGER.md:496).
NEW GAP: G324-CKPT-HASH-GUARD - the route records the checkpoint hash before load but does not compare it with the sealed expected hash (g324_apache_arm_rebudget.py:157-163; g324_arms.py:121-124).
NEW GAP: G324-REUSE-FALLBACK - a wheel mismatch returns REUSE REFUSED instead of executing the declared source-build fallback inside the same clock (g324_apache_arm_rebudget.py:64-68,76-80).
