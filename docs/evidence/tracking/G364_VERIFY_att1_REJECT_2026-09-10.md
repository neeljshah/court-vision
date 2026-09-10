VERDICT: REJECT

Candidate c6dd183f4 changes only the memo at `g364_learned_court_presence_2026-09-09.md:26`; full diff reviewed.
ACCEPTANCE PASS (PARTIAL): the sealed 60/60/180 quota is unsatisfiable and PARTIAL is allowed (`G364_spec.md:53`; memo:1,26,34-39).
PREMISE PASS: reproduced 1 positive/12, line-family AUC 0.090909091, surface AUC 1.000000000, and 5/384 NON_COURT = 13.020833 per mille (memo:7-10).
HEADLINES PASS: reproduced kappa 0.916186485 from 228/240 agreement; development 115/240 = 479.166667 per mille; validation 224/122/14 of 360 (memo:20,24,26).
EVIDENCE PASS: 20 development and 30 validation sources are pinned at 1920x1080; 240/360 unique frame keys; 18/18 memo hashes match canonical LF bytes (memo:16,18,28).
EYE CHECK PASS: all 240 sheets are unique 720x370 files, 14,678-57,003 bytes; six evenly spaced samples show only frame identity and pixels (memo:18).
MEMO PASS: the required NOT VERIFIED list is present (`g364_learned_court_presence_2026-09-09.md:34-39`).
TEST PASS: `python -m pytest tests/platformkit/test_g364_learned_court_presence.py -q` -> 6 passed in 0.83s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 0.68s.
IMPORT CENSUS PASS: `git grep -n g364_ -- tests` finds only the spec test (`test_g364_learned_court_presence.py:12-15,73`).
LOC PASS: G364 Python files are 59-207 lines; the test is 85 lines, all <= 300.
B1 PASS: all 240 development and 360 validation-pool rows are counted; six source failures are named (`memo:16,24,26`).
B2 PASS: schema is additive and all G364 field readers were checked (`g364_sampler.py:92-104`; `g364_score.py:39-55`).
B3 PASS: absent sources are recorded, and no consumer gate exists (`memo:16,35-38`).
B4 PASS: PARTIAL creates no claimable production item (`memo:1,34-39`).
B5 PASS: pod work is recorded as scratch-only with deployed trees untouched (`memo:5`).
B6 PASS: no module was moved or retired; surviving G364 imports resolve (`test_g364_learned_court_presence.py:12-15,73`).
B7 PASS: the exact interior formula holds for every one of 50 sections (`g364_sampler.py:13-22`; memo:18).
B8 PASS: fitted-point results are explicitly excluded as held-out evidence (`memo:22,35`).
B9 PASS: denominators are 240 and 360 unique frame keys, not recycled units (`memo:18,24,26`).
B10 PASS: threshold 0.30 and all six candidates match the seal (`g364_prereg_2026-09-10.md:18-24`; `g364_train.py:15-16`).
Q1 PASS: seal recomputes and commit b02b7ecd3 predates fitting and validation (`g364_prereg_2026-09-10.md:61`; memo:12).
Q2 PASS: no charged comparison or scored claim exists (`memo:1,26,34`).
Q3 PASS: the frozen bar, head, and threshold were not moved (`memo:22,26`).
Q4 PASS: no held-out outcome was scored; the future evaluator contract remains sealed (`g364_prereg_2026-09-10.md:43-47`; memo:34-35).
Q5 PASS: no AHEAD claim exists (`memo:1,34`).
Q6 FAIL: the audit sentence itself contains six prohibited vocabulary tokens in prose (`memo:32`).
Q7 PASS: no held-out metric is scored; the 360-frame pool is exhaustive and unique (`memo:26`).
Q8 PASS: the premise was re-measured first and independently reproduced here (`memo:7-10`).
CORRECTION (minimal): at memo:32 replace the six-token enumeration with `Q6 automated scan: no prohibited vocabulary in row prose.`
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-10 | tracking | G364 | premise 1/12 and reach 5/384 reproduced; PARTIAL quota 14/180; Q6 prose failure | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: `g364_predict.py:27-29` archives fixed-position differences, not top-two probability margins; 600/600 stored margins disagree although every categorical prediction reproduces.
NEW GAP: candidate memo line 26 fails `git diff --check` for trailing whitespace; normalize only that line ending.
