VERDICT: REJECT
Candidate `2f1eb0b29`; full stat and diff reviewed.
ACCEPTANCE FAIL: the sealed score uses 2 sections x 20 evaluated frames, not 4 x >=60; two sections are absent and one scored section bypasses the production preflight (`G336_spec.md:52-63`; memo:7-27; `g336_run.py:69-80`).
ACCEPTANCE FAIL: HSV is forced although route OSNet vectors exist, and the disclosed deployed-tree writes violate must-not-move (`G336_spec.md:32-35,60-61`; `g336_capture.py:23-32`; memo:18,40,51).
ACCEPTANCE PASS: trace, tables, PARTIAL label, 58-line memo, wall time, hashes, and NOT VERIFIED list are present (`G336_spec.md:52,62-70`; memo:1,18-58).
A1 PASS: candidate paths overlaid on isolated master and the sole importing test file passed 6/6.
A2 PASS: all headline fragmentation values and qualifying counts independently reproduce from per-instance and evaluator CSVs; premise reproducibility is a NEW GAP below.
A3 PASS: eye check is optional and no render claim is made (`G336_spec.md:59`).
A4 PASS: sealed instances 407/407 unique and ticks 40/40 unique; dev240 instances 2318/2318 and ticks 291/291 unique.
A5 PASS: tracked-reader search finds only `g336_run.py:12-16`, `g336_capture.py:110`, and `test_g336_track_id_continuity.py:4-9`; the test passed.
A6 PASS: no candidate landing was performed; this verifier memo is committed by explicit pathspec only.
A7 PASS: all nine committed evidence files exist (120,913 bytes total); all claimed LF hashes and three route-code hashes reproduce (`memo:42,56`).
B1 PASS: the unequal observation sets and every excluded count are named (`memo:45`).
B2 FAIL: `capture_section` changes its return from 3 to 4 values and the prior stdout `ms` field is removed rather than aliased (`g336_capture.py:35-37,99,142-146`).
B3 PASS: refused sections are explicitly recorded rather than silently quarantined (`g336_run.py:77-91`; `premise.csv:2-3`).
B4 PASS: no claim lifecycle is introduced (`2f1eb0b29` full diff).
B5 FAIL: the candidate discloses three writes under the deployed pod tree before verification (`memo:51`; `G336_spec.md:12-14`).
B6 PASS: no module was moved or retired; every tracked importer resolves.
B7 PASS: complete CSVs were read, not head slices; uniqueness is reported above.
B8 PASS: the association and label-free summaries fit no model (`g336_track_id_continuity.py:49-157`).
B9 PASS: denominators are named evaluated-frame counts times the fixed ten slots, while instance counts vary (`g336_track_id_continuity.py:145-157`).
B10 FAIL: the harness replaces the production preflight gate with an unconditional pass and scores bypassed sections (`g336_capture.py:77-89`; `g336_run.py:69-76`).
Q1 FAIL: seal `5dd6fa1c2e4c210d708adac95a0f2812bf68b7ab69cafa055317af030cb676da` reproduces and predates the sealed run, but the scored cap-240 comparison is outside the cap-60 prereg (`prereg:13-18,58`; memo:29-38).
Q2 PASS (N/A): this row defines no charged trial or K (`prereg:1-58`).
Q3 PASS: the >=30 pct on >=3/4 bar is byte-identical in spec and prereg and is reported unmet (`G336_spec.md:55-57`; `prereg:47-50`; memo:27,38`).
Q4 PASS: per-tick paired records pass through symmetric-embargo CPCV and independently sum to every reported fragmentation ratio (`g336_track_id_continuity.py:160-190`; `g336_run.py:127-136`).
Q5 PASS (N/A): no AHEAD claim is made (`memo:1,27,38`).
Q6 PASS: automated restricted-language scan of candidate additions found 0 matches.
Q7 FAIL: sealed scored cells have n=20, below both the >=30 scored rail and the spec's >=60 (`memo:20-25`; `G336_spec.md:58`).
Q8 PASS: same-day row; the harness computes and gates the premise before comparison (`g336_run.py:86-105`).
TEST: `python -m pytest tests/platformkit/test_g336_track_id_continuity.py -q -p no:cacheprovider` -> 6 passed in candidate cwd.
TEST MASTER: same command in isolated master with candidate paths overlaid -> 6 passed.
TEST DIFFERENTIAL: same command with candidate test over pre-candidate `bf8a396e7` -> 1 collection error (new `RouteRefused` symbol absent).
LOC PASS: `g336_capture.py` 150, `g336_run.py` 152, `g336_track_id_continuity.py` 199, test 83; all <=300.
REPRO: sealed claimed/measured 0/2, 0.045->0.060 and 0.065->0.220; dev240 claimed/measured 1/4, improvements 36.67, 47.62, 20.69, -100.00 pct, with only the first satisfying all checks.
CORRECTIONS: delete `g336_run.py:69-80`; retain `ms=<wall>` as an alias at `g336_capture.py:145`; void both runs, seal cap >=180 before scoring, rerun scratch-only without deployed-tree writes, and archive premise-source rows.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G336 | sealed n=20 on 2 sections: fragmentation 0.045->0.060 and 0.065->0.220; declared rerun 1/4 clears the unchanged bar; B2/B5/B10/Q1/Q7 fail | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: exact premise inputs are not archived: `g336_run.py:93-99` reads route tracking rows, while `instances.csv` stores a different matched-observation set (`g336_run.py:113-138`; memo:45); its baseline proxy remeasures 9/13 instances with medians 10/1 versus premise 10/13 and 10.5/3.
NEW GAP: runtime is not like-for-like because baseline timing includes its appearance computation and candidate timing does not (`memo:50`).
NEW GAP: the four named pod videos were unavailable to this verifier, so their bytes and resolutions were not independently reopened; committed artifact and code hashes did reproduce.
