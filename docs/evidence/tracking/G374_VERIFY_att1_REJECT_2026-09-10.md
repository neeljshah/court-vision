VERDICT: REJECT
Candidate e397201db: stat and full one-line memo diff reviewed; the row payload from master was also audited.
ACCEPTANCE PASS AS PARTIAL: precision/recall clear their bars, but ABSTAIN is 14/60, so PARTIAL correctly names the unmet bar (G374_spec.md:34-42; memo:1).
PREMISE PASS: committed model bytes reproduce head a2a08eaac5e79315e329308b5d1ddaff4aede200b39039900932ee492dff966e, threshold 0.30, pool 360 = 224/122/14, one bound digest, pinned extractor, and empty game overlap (memo:7).
HEADLINES PASS: claimed/reproduced n/TP/predicted/reference = 300/178/185/184; precision 0.962162 [0.923969,0.981553], recall 0.967391 [0.930695,0.984971], abstention 14/300, agreement 293/300, kappa 0.954314 (memo:13,15).
PER-COMPETITION PASS: all eight claimed n/predicted/TP/reference counts and six-decimal precision/recall values reproduce (memo:17-22).
EYE CHECK PASS: 30 unique rows contain all 14 ABSTAIN plus 16 strict-interior scored rows; all three composites were inspected and are legible (memo:26; g374_eyecheck.py:23-33).
EVIDENCE PASS: all named outputs exist; 10/10 listed artifact hashes match committed bytes; 300 unique sheets are below 200 KB (memo:35).
ADDITIVITY PASS: no field, status, or reader behavior is renamed or removed; the candidate itself changes prose only (memo:13; candidate diff).
LOC/MEMO PASS: implementation/test LOC are 97/88/118/78/81/125, all <=300; memo is 44 lines and NOT VERIFIED begins at memo:39.
TEST PASS: `python -m pytest tests/platformkit/test_g374_court_presence_validation.py -q` -> 6 passed in 1.97s (candidate).
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 1.19s (candidate).
TEST MASTER UNAVAILABLE: `python -m pytest tests/platformkit/test_g374_court_presence_validation.py -q -p no:cacheprovider` -> 0 tests in 0.00s, exit 4; file absent on master 8d68fffd1.
IMPORT CENSUS PASS: `git grep -l g374_ HEAD -- tests` finds only the passing spec test (test_g374_court_presence_validation.py:9-12).
B1 PASS: draw is label-independent; all 60 excluded keys are uniquely named and disjoint from the 300 selected keys (memo:11; excluded.csv:1).
B2 PASS: outputs and modules are additive, and every G374 reader/importer was surveyed (g374_score.py:15-16; g374_eyecheck.py:48-80).
B3 PASS: absent pinned inputs were restored and digest-checked, not classified as bad evidence (memo:9; g374_recover.py:22-38).
B4 PASS: the unwired PARTIAL row creates no claim/reclaim lifecycle (memo:44).
B5 PASS: pod work was scratch-only and deployed trees were untouched (memo:33).
B6 PASS: no module moved or retired; all G374 imports resolve in the passing spec test (test_g374_court_presence_validation.py:9-12).
B7 PASS: the draw and eye check use seeded strict-interior spacing, not a head slice (g374_quota.py:32-45; g374_eyecheck.py:23-33).
B8 PASS: development values are explicitly labelled in-sample and not evidence (memo:24).
B9 PASS: denominators are 300 unique frame keys over 30 sections, 15 games, and 8 competitions (memo:11,15).
B10 PASS: candidate e397201db changes no harness threshold or gate value from master (candidate diff).
Q1 PASS: prereg seal 6556c4a6 and amendment seal ff10a4a4 recompute; seal-only commits 192abcaf2/e89b9e32 precede scoring commit baeb410c0 (memo:5).
Q2 PASS: no charged comparison or launch count applies to this static classifier audit (g374_prereg_2026-09-10.md:55-59).
Q3 FAIL: spec requires >=60 in every predicted stratum, but scorer checks only COURT/NON_COURT and archives true despite ABSTAIN=14 (G374_spec.md:37-38; g374_score.py:60-61; summary.json:3,13-15).
Q4 PASS: no predictive OOS series or meta-learner is scored; the frozen static classifier uses a game-disjoint validation set (g374_prereg_2026-09-10.md:55-59; memo:7).
Q5 PASS: no comparative advancement status is claimed (memo:1,40-44).
Q6 PASS: independent exact-token scan of row prose, tabular evidence, code, and test returns zero restricted-language or retracted-figure hits (memo:30-31).
Q7 PASS: the scored set has 300 unique frames; the below-rail ABSTAIN stratum is explicitly reported as the unmet bar (summary.json:6,13; memo:1,40).
Q8 PASS: the whole-pool premise was remeasured first and independently reproduced from committed input bytes (memo:7; g374_premise.py:48-70).
CORRECTION minimal: g374_score.py:60-61 use `min(summary["predicted_counts"].values()) >= 60`; test:93 assert the bar is false; regenerate summary.json:3 as false.
CORRECTION display-only: memo:1 `38` -> `38.888889`; memo:9 source range -> `57,018,293 to 100,578,787 bytes`; memo:13 sheet range -> `19,490 to 59,293 bytes`; memo:28 LOC range -> `78 to 125 lines`.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-10 | tracking | G374 | premise TRUE 224/122/14; precision 0.962162, recall 0.967391, kappa 0.954314; PARTIAL at ABSTAIN 14/60; archived bar scope fails Q3 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: memo:13 claims 12 RAM-gate holds, but no named archived driver log exists to independently reproduce that count.
NEW GAP: master 8d68fffd1 lacks the G374 module and spec test, so contract A1 master replay is unavailable before landing.
NEW GAP: local CRLF checkout changes text-file byte hashes and makes g374_premise.py:51-67 reject the committed model copy; canonical committed LF bytes reproduce the sealed digest.
