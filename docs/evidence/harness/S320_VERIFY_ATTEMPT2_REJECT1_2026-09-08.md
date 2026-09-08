VERDICT: REJECT
Scope: candidate 397ad6348; S320 ACCEPTANCE RULE plus contract B1-B10 and Q1-Q8 only.
ACCEPTANCE FAIL: memo says CLEAN while availability and polarity are NOT_VERIFIED; the rule requires PARTIAL when a check could not run (S320_timestamp_artifact_audit_2026-09-08b.md:1,15-17,40-42; S320_spec.md:50-62).
PREMISE PASS: master has only the prior infeasible attempt with 0 replayed states; no landed frozen-model deletion/delay replay exists (master:docs/evidence/harness/S320_VERIFY_2026-09-08.md:3,32).
REPRODUCTION PASS: claimed/reproduced 465249 ticks, 1593 games, 2 seasons, 271154 clock-zero ticks (0.582814793799), 63 strata, 313 unique sealed pairs, 40 terminal-mask flags and one final-tick flag (memo:3-25; states.csv:1; audit.csv:1).
REPLAY PASS: claimed/reproduced N/M0 n=313 each, max prefix delta 0 with 0 changed, max delayed deltas 0.337200/0.335000 with 211 changed each, and 0 untraced changes (memo:29-38; replay.csv:1).
ARTIFACT PASS: all named paths exist; LF hashes reproduce as states 6f8f617e..., audit c1ad37b3..., replay eef08eef..., and prereg seal a735f99d... (memo:48-54; prereg:137).
B1 PASS: all 63 strata are censused before selection and no failing state is excluded (s320_state_audit.py:75-90; prereg:35-114).
B2 FAIL: sealed delta_b/delta_c and prior replay aliases are removed, not retained; replay.csv substitutes delta_b_micro/delta_c_micro (prereg:124-125; replay.csv:1; s320_state_audit.py:159-163,222-226; master:s320_state_audit.py:143-145; contract:21).
B3 PASS: absent received_at and side/home evidence yields NOT_VERIFIED, never ACCEPTED (s320_state_audit.py:121-135).
B4 PASS: the local audit route creates no claim/retry lifecycle (s320_state_audit.py:200-239).
B5 PASS: execution is recorded as local and no deployed tree is touched (memo:2,46).
B6 PASS: no module is moved or retired; the focused test imports the retained route (test_s320_state_audit.py:9-11).
B7 PASS: SHA-256 ranking follows the full stratum census, not a head slice (s320_state_audit.py:75-90).
B8 PASS: no fitted-point residual is offered as evidence; the evidence is replay invariance (memo:29-38).
B9 PASS: 313/313 state pairs are unique and both model denominators contain 313 states (states.csv:1; memo:8-10,29).
B10 PASS: 5 states/stratum, 60 seconds, and the zero-change bar match the amended spec (s320_state_audit.py:14-17; prereg:129-133).
Q1 PASS: prereg seal recomputes and commit a4e4b8c95 precedes measurement commit 7186cbaa4 (prereg:137).
Q2 PASS: no trial is charged and the candidate stack changes no shared register file (prereg:7-8; memo:46).
Q3 PASS: the amended n and replay bars are unchanged (S320_spec.md:79-87; prereg:129-133).
Q4 PASS: no OOS outcome comparison or meta-learner result is claimed (memo:43-46).
Q5 PASS: no AHEAD result is claimed (memo:43-46).
Q6 PASS: all seven candidate files are ASCII; independent restricted-vocabulary and figure scan has 0 non-exempt hits (memo:55-57).
Q7 PASS: n=313 is a stratified sample over every non-empty stratum and exceeds the sampling rail (memo:8-11).
Q8 PASS: premise independently remeasured from the named 2829826-byte parquet using selected columns (memo:3-7).
ADDITIVITY FAIL: reader census finds only test_s320_state_audit.py, but updating that reader does not supply aliases for removed fields or behavior (test_s320_state_audit.py:9-11,49-52; s320_state_audit.py:159-163).
LOC PASS: touched Python files are 244 and 98 lines; repository LOC rail passes (s320_state_audit.py:244; test_s320_state_audit.py:98).
MEMO PASS: candidate memo is 59 lines and its NOT VERIFIED list starts at line 40 (memo:40-46).
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_s320_state_audit.py -q -p no:cacheprovider --confcutdir=tests\platformkit` -> 7 passed in 3.66s (candidate, local).
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_loc_rail_scope.py -q -p no:cacheprovider --confcutdir=tests\platformkit` -> 1 passed in 1.08s (candidate, local).
TEST: in `C:\Users\neelj\nba-ai-system`, `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_s320_state_audit.py -q -p no:cacheprovider --confcutdir=tests\platformkit` -> 5 passed in 0.75s (master, local).
TEST: in `C:\Users\neelj\nba-ai-system`, `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_loc_rail_scope.py -q -p no:cacheprovider --confcutdir=tests\platformkit` -> 1 passed in 1.41s (master, local).
IMPORT CENSUS PASS: test_s320_state_audit.py is the only test importing the touched module; it ran alone on candidate and master (test_s320_state_audit.py:9-11).
CORRECTION: memo:1,58 CLEAN -> PARTIAL; restore sealed delta_b/delta_c and prior replay aliases additively, retaining micro fields only as extras.
NOT VERIFIED:
- Availability beyond tick order and target polarity; the source has no received_at, side, or home fields (memo:3-7,40-42).
- Any deployment, flag, register update, or broader calibration result (memo:46).
2026-09-08 | nba in-game calibration | S320 | 313 states across 63 strata; 0 prefix changes; 211 delayed changes per model traced; availability and polarity not verified; replay schema non-additive | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: N is a fresh median-cut row fit, not the landed S310/S309 grouped CPCV null named by the method; reconcile identities before reuse (s320_state_audit.py:173-186; s310_tail_beta_offset.py:195-196).
NEW GAP: actual N/M0 predictors filter at state time internally, so full/prefix equality is structural; the planted-future test exercises a substitute callback, not either reported model (s320_state_audit.py:145-170; test_s320_state_audit.py:47-52).
