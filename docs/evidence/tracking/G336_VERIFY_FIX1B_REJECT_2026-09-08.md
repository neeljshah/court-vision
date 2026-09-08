VERDICT: REJECT
Candidate: 38391e07852ff187fc4048c878967056e1326914; scope checked from full diff and 16-path stat.
ACCEPTANCE RULE PASS: honest PARTIAL / BAR NOT MET is forced by 2 of 4 REFUSED sections; memo:1,29 and metrics.csv:2-5.
PREMISE PASS: independent premise_rows.csv recompute = nba_0081 10 slots/77 instances/median 3/n=180/1206 rows; wnba_5l4 10/151/4/n=180/1090, matching memo:9-18.
HEADLINE PASS: independent instances.csv plus evaluator_records.csv recompute = 0.037777778 -> 0.016666667 (55.88 pct, n=180) and 0.069101124 -> 0.047752809 (30.89 pct, n=178), matching memo:1,22-29.
ARTIFACT PASS: 6 of 6 LF SHA-256 values match memo:50; all 2296 premise, 3526 instance, and 358 evaluator data rows are unique.
B1 PASS: excluded observations are named for both sections at memo:42 and applied equally at g336_run.py:113.
B2 FAIL: capture_section removed the optional bypass input and the bypassed_exit_4 status without an alias; g336_capture.py:56 and memo:3. CSV columns themselves are additive.
B3 PASS: all four sealed inputs were present and route refusals are explicit, not missing evidence; memo:7,14-16.
B4 FAIL: cached metadata is reused whenever meta["scored"] is true without rejecting the now-void bypassed status; g336_run.py:83-89 and memo:3.
B5 FAIL: attempt 1 wrote three panorama caches in the deployed tree and left them there; g336_track_id_continuity_2026-09-08.md@2f1eb0b29:51.
B6 PASS: no module moved or retired; active imports remain at g336_run.py:13-17 and test_g336_track_id_continuity.py:4-11.
B7 PASS: no render exists and all rows of each sealed scored window are used; memo:35 and metrics.csv:2-5.
B8 PASS: the evaluator returns frozen arm values and fits no model; g336_track_id_continuity.py:178-191.
B9 PASS: numerator uses G310-split instances rather than recycled slot ids; g336_track_id_continuity.py:109-121,152.
B10 PASS: MAX_COST/MAX_AGE and the acceptance bar did not move; g336_track_id_continuity.py:14 and g336_prereg_fix1b_2026-09-08.md:90-95.
Q1 PASS: amendment seal recomputed exactly and commit fda491ca8 precedes candidate scoring commit; g336_prereg_fix1b_2026-09-08.md:97.
Q2 PASS (not applicable): G336 specifies no charged trial ledger; G336_spec.md:55-66.
Q3 PASS: the copied bar is unchanged; g336_prereg_fix1b_2026-09-08.md:90-95 and G336_spec.md:55-63.
Q4 PASS: symmetric-embargo CPCV is invoked per arm and archived means reproduce each fragmentation value; g336_track_id_continuity.py:178-191.
Q5 PASS (not applicable): the result is PARTIAL, not AHEAD; memo:1.
Q6 PASS: candidate-addition vocabulary scan found 0 restricted-term and 0 restricted-figure hits; memo:52.
Q7 PASS: scored cells contain exhaustive n=180 and n=178 ticks; metrics.csv:2-5 and evaluator_records.csv:2.
Q8 PASS: the premise and stop rule execute before association scoring; g336_run.py:123-145.
TEST PASS: `python -m pytest tests/platformkit/test_g336_track_id_continuity.py -q` -> 10 passed in 6.30s. Import census found this single test file for all 3 touched modules.
LOC PASS: g336_capture.py 166; g336_run.py 193; g336_track_id_continuity.py 211; test_g336_track_id_continuity.py 126, all <= 300.
MEMO PASS: 52 lines <= 60 and NOT VERIFIED starts at memo:39; all six named committed evidence files exist.
CORRECTION DIFF: at g336_run.py:87 map legacy bypassed_exit_N to refused_exit_N and continue before testing meta["scored"].
CORRECTION DIFF: at g336_capture.py:56 retain `bypass_preflight=False` as a compatibility input, but reject True without changing the production preflight.
CORRECTION DIFF: change cap defaults 240 -> 540 at g336_run.py:72 and g336_capture.py:154 to match the sealed amendment at prereg:32.
2026-09-08 | tracking | G336 | premise 77/151 instances; fragmentation 55.88/30.89 pct lower on 2 scored sections, 2 REFUSED, bar not met; legacy void cache remains reusable | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: archive per-observation bbox, signature, arm assignment, and timing inputs; instances.csv lacks these, so the claimed switch, appearance, and runtime cells at memo:1,29-31 cannot be independently recomputed.
NEW GAP: repair the trace citation at memo:20; unified_pipeline.py:4352 is a method definition, while the emitted player_id field is at unified_pipeline.py:2028.
