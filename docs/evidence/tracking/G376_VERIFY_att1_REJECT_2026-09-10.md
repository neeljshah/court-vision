VERDICT: REJECT
Candidate: c3b5ba0b6; verified 2026-09-10 by codex-sol against G376 ACCEPTANCE RULE and B1-B10/Q1-Q8 only.
ACCEPTANCE metric: FAIL -- the required corrected G370 M1 denominator is not computed; raw `observed_ticks` feeds the result (`scripts/platformkit/tracking/g376_report.py:42,60,112-125`) while M1 is isolated in `g376_premise.py:35-50`.
ACCEPTANCE before: PASS -- independent premise.csv aggregation gives SEALED34 32158/45842=0.701496, FRESH69 68534/89655=0.764419, and 30/34 non-integral (`premise.json:2-22`).
ACCEPTANCE classification/bar: PASS -- SEALED34 O/D/N/U=0.540487/0.031347/0.428166/0; FRESH69=0.571926/0.022018/0.406057/0 (`classification_summary.json:3-56`).
ACCEPTANCE controls: PASS -- synthetic controls exact and rerun 1000/1000=1.000000, symmetric difference 0 (`controls.csv:2-12`; `rerun_log.txt:46-64`).
ACCEPTANCE denominators: FAIL -- claimed 0.056338/0.037070 are raw-table zero shares, not G370 M1 shares (`g376_report.py:40-63`; `g370_scorer.py:95-118`).
ACCEPTANCE n/uniqueness: PASS -- 34+69 unique sections and 135497/135497 unique (section,frame) ticks (`g376_declared_tick_observations_2026-09-10.md:15-17`).
ACCEPTANCE eye check: PASS -- 10 decile-spaced 80-tick strips, max committed size 5861 bytes (`g376_report.py:68-84`; `summary.json:203-262`).
ACCEPTANCE immutability: PASS -- no src/run_clip/daemon/data/flag edit and route hashes match candidate blobs (`schedule_rule.md:3-12`).
B1 PASS -- every declared tick is partitioned before aggregation; no exclusion (`g376_classify.py:23-45`).
B2 PASS -- additions only apart from the append-only ledger row; no field/status rename or removal; sole importing test found (`test_g376_declared_tick_observations.py:1-103`).
B3 PASS -- absent schedule evidence becomes UNKNOWN, never adverse (`g376_prereg_2026-09-10.md:72-74`; `tests/platformkit/test_g376_declared_tick_observations.py:74-81`).
B4 PASS -- no claim/retry state is introduced (`g376_classify.py:23-45`).
B5 PASS -- deployed route was read/import only and output redirected to scratch (`g376_declared_tick_observations_2026-09-10.md:20-21`).
B6 PASS -- no module moved or retired; all G376 modules are additive (`g376_declared_tick_observations_2026-09-10.md:32`).
B7 PASS -- strips start at rows 0,13549,...,121941, not a head slice (`summary.json:203-262`).
B8 PASS -- no fitted residual or fit-based evidence is used (`g376_prereg_2026-09-10.md:12-14`).
B9 PASS -- denominator is 135497 unique declared ticks, not recycled ids (`ticks.csv:1`; memo:15-17).
B10 PASS -- 0.95/0.05 and exact-control bars match the sealed spec (`g376_prereg_2026-09-10.md:143-152`).
Q1 PASS -- seal recomputed as 32bcad44e602ac870f06e02cf5118272bf1343797906905f0ed4d8d4705173ee; seal commit 3546f3b3e predates metric commit c00d606be (`g376_prereg_2026-09-10.md:172`).
Q2 PASS (not engaged) -- no charged scored comparison (`g376_prereg_2026-09-10.md:12-17`).
Q3 PASS -- sealed bars unchanged and controls use exact equality (`g376_prereg_2026-09-10.md:101-119`).
Q4 PASS (not engaged) -- no OOS score or meta-learner (`g376_prereg_2026-09-10.md:12-14`).
Q5 PASS (not engaged) -- no AHEAD result (`g376_prereg_2026-09-10.md:12-14`).
Q6 PASS -- independent scan of 35 G376 files plus the added ledger row found 0 vocabulary hits (`g376_declared_tick_observations_2026-09-10.md:1-34`; `RESULTS_LEDGER.md:716`).
Q7 PASS -- CONSTRUCT exhaustively enumerates 103 unique sections and all 135497 ticks (`specs/G376_spec.md:41`; `g376_declared_tick_observations_2026-09-10.md:15-17`).
Q8 PASS -- premise remeasured before adjudication and both raw shares exceed 0.10 (`premise.json:2-22`).
LOC PASS -- g376_classify/controls/premise/report/rerun/schedule/snapshot/test = 181/114/95/164/114/180/97/103 lines, all <=300 (each file:1).
TEST PASS -- `python -m pytest tests\platformkit\test_g376_declared_tick_observations.py -q` -> 8 passed in 0.93s.
TEST PASS -- `python -m pytest tests\platformkit\test_loc_rail_scope.py -q` -> 1 passed in 0.81s; importer census found no second test file.
REPRODUCED -- never-scheduled/raw-zero = 19628/21065=0.931783 and 36405/38379=0.948566; pair ratios 26649/28242=0.943595 and 51207/53181=0.962881 (`g376_declared_tick_observations_2026-09-10.md:1,26`).
REPRODUCED CONTRADICTION -- FRESH69 M1 observed=89655-68534=21121, hence M1 zero over producer ticks=(53250-21121)/53250=0.603362, not claimed raw 0.037070 (`premise.json:2-10`; `g376_declared_tick_observations_2026-09-10.md:26`).
CORRECTION DIFF 1: - derive G370 correction from raw `observed_ticks`; + compute per-section `m1_player_frames & evaluated_frames` and aggregate `|E|-|M1_PLAYER_FRAMES & E|`.
CORRECTION DIFF 2: - label 0.056338/0.037070 as G370 M1; + label them RAW, regenerate consequence/summary/memo/ledger, and revise the categorical headline.
2026-09-10 | tracking | G376 | raw tick classes reproduce, but the required G370 M1 corrected denominator is absent; FRESH69 M1 zero over producer ticks is 32129/53250=0.603362, not the raw 0.037070 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: `rerun_log.txt:2` omits required `--log`; `g376_rerun.py:98` rejects the recorded command. Add the actual `--log` and `--summary` paths.
NEW GAP: memo:30 promises pasted vocabulary output but memo:31 is blank and records two test files in one command; record the scan count and per-file commands.
