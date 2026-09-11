VERDICT: REJECT
CANDIDATE PASS: reviewed d8e299b03 stat and full 358064035..d8e299b03 diff; 68 touched paths, no rename/delete, `git diff --check` clean.
ACCEPTANCE-RAW PASS: 300 unique keys, 600 answers/20 archives, no duplicate/missing ids, 299 scored pairs, round 1 n=29, round 8 n=30; invalid coordinate remains a valid label/box (`summary.json:35-68`; `confusion_by_round.csv:2,9,12`).
ACCEPTANCE-CENTRE PASS: all 125 gaps retained, median 24.021 px, nearest-rank p90 292.139 px, max 1415.278 px, 288 valid diameters, 115/115 unique conflicts categorized (`summary.json:38-68`; `reason_categories.csv:1`).
ACCEPTANCE-EXPLANATION PASS: round 8 reproduces 4 SLIPPED/2 ALIGNED/3 strict-next versus other rounds 3/53/1; reason lead exceeds same only in round 8; even visual checks support the binding diagnosis (`binding_offset.csv:2-11`; `eye_index.csv:37-59`).
ACCEPTANCE-CONTROLS PASS: exhaustive 30 unique scene-layout pairs, 20 VISIBLE/5 ABSENT/5 UNKNOWN, exact bindings, native scale, all 29 adjacent pairs distinguishable; two runs match 13 tables and 38 renders (`control_answers.csv:2-31`; `repeats.json:2-3`).
EVIDENCE PASS: all named paths exist; 56/56 input hashes, 300/300 sheet hashes, and 61/61 manifest hashes independently match; memo has NOT VERIFIED at `g403_ball_rater_failure_controls_2026-09-11.md:38-44`.
REPRODUCED: claimed/measured pooled kappa 0.750519/0.750519; round-8 kappa 0.360465/0.360465; gaps 125/125; median 24.021/24.021; diameters 288/288; conflicts 115/115 (`summary.json:53-68`).
REPRODUCED: settled states 116 VISIBLE/126 ABSENT/58 UNKNOWN and audit 12 NON_PLAY/17 PLAY/1 UNCLASSIFIED; claimed 0.400, measured 0.400 (`summary.json:86-94`).
B1 PASS: denominators retain the invalid answer separately and every raw both-VISIBLE pair; no post-result exclusion (`answer_binding.csv:1`; `gaps.csv:1`).
B2 PASS: candidate is additive; no field/status was renamed or removed, and the only existing test importer of a touched module is the focused file (`test_g403_ball_rater_controls.py:111`).
B3 PASS: no absent-evidence quarantine or production gate was added (`g403_replay.py:1-193`).
B4 PASS: no claim/retry path was added (`summary.json:21-34`).
B5 PASS: no pod job or deployed-tree write (`summary.json:24,34`).
B6 PASS: no moved/retired module and no orphaned import (`g403_build.py:1`; `g403_package.py:1`).
B7 PASS: audit indices are evenly 5,15,...,295; verifier viewed all audit/round-8 sheets plus even control/conflict samples (`shot_claim_audit.csv:2-31`; `eye_index.csv:2-59`).
B8 PASS: binding evidence is raw contrast and the controls are explicitly CONSTRUCT, not independent real-image truth (`g403_ball_rater_failure_controls_2026-09-11.md:22-23`).
B9 PASS: 300 unique keys, 115 unique conflict keys, 30 unique audit keys and 30 unique controls; no recycled/constant denominator (`summary.json:35-68`; `control_answers.csv:2-31`).
B10 PASS: kappa bar remains 0.6, centre bar 13.75 px, native scale 1.0 and 0.5-diameter rule unchanged (`confusion_by_round.csv:2-12`; `instructions.md:36-42`).
Q1 PASS: preregistration, A1 amendment and instructions seals rehash; prereg and A1 commits precede candidate measurement commit (`prereg.md:33`; `amendment_A1.md:50`; `instructions.md:59`).
Q2 PASS: retrospective diagnostic has no charged trial or scored comparison (`prereg.md:29-30`; `summary.json:21-34`).
Q3 PASS: all acceptance bars match the upstream G400 values (`confusion_by_round.csv:2-12`; `summary.json:41-49`).
Q4 PASS: no OOS comparison or meta-learner is claimed (`g403_ball_rater_failure_controls_2026-09-11.md:1,22-23`).
Q5 PASS: no AHEAD claim or two-corpus claim is made (`g403_ball_rater_failure_controls_2026-09-11.md:22-23`).
Q6 FAIL: full 29-file touched-text census finds one non-opaque index-9 hit in scanner source; saved scan covered only 22 evidence files and missed its own source (`g403_q6_scan.py:14`; `q6_scan.json:92-95`).
Q7 PASS: all 30 CONSTRUCT controls are enumerated and the separate eye audit has n=30 even cards (`control_answers.csv:2-31`; `shot_claim_audit.csv:2-31`).
Q8 PASS: premise was independently replayed before disposition and exactly holds (`summary.json:35-68`).
TEST PASS: `python -B -m pytest tests/platformkit/test_g403_ball_rater_controls.py -q -p no:cacheprovider --basetemp=C:\Users\neelj\nba-track-a3\.pytest_tmp_g403_verify` -> 10 passed in 2.02s; this is the sole importer test.
TEST FAIL A1: same command from `C:\Users\neelj\nba-ai-system` -> 0 tests; master c0d188075 lacks the test path, so candidate-only execution is reported rather than hidden.
LOC PASS: touched Python files are 203/158/202/103/127/193/138 lines, all <=300 (`g403_build.py:1`; `test_g403_ball_rater_controls.py:1`).
CORRECTION 1: `g403_q6_scan.py:14` construct index-9 entirely from character codes; scan all 29 touched text paths, then refresh `q6_scan.json`, repeats, hashes and memo.
CORRECTION 2: `g403_package.py:15-18,85` resolve adjudicated keys from `adjudications.csv`; 8/30 saved `settled_label` cells are not final G400 states. Regenerate the audit and dependent hashes; add an equality test.
CORRECTION 3: memo line 25 `36` -> `38`; memo/summary linear p90 `287.386` -> `287.385` when calculated from unrounded raw gaps, or label the current value as computed after 3-decimal gap rounding.
2026-09-11 | tracking | G403 | premise/headlines reproduce; Q6 index-9 source hit; 8/30 audit settled labels incorrect | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: `input_hashes.csv` omits G400 batch receipts and the 300 individual sheet objects; verifier independently found 300/300 sheet hashes valid, but the candidate audit trail does not retain that check.
NEW GAP: contract A1 cannot run pre-landing here because master lacks the G403 test path; define a read-only candidate-on-master test procedure for verifier-only worktrees.
