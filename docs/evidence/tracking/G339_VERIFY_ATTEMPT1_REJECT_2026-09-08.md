VERDICT: REJECT
Candidate: `fbbab4784`; verification date 2026-09-08; interpreter Python 3.10.0.
ACCEPTANCE PREMISE PASS: feature has inline coordinates (`src/features/feature_engineering.py:79`); `src/sim/` has no ball-table or joined-table call site (`src/sim/basketball_sim.py:95`).
ACCEPTANCE CENSUS FAIL: claimed 37 = 22/10/3/2 (`memo:15-18`; `readers.csv:2-38`), but semantic readers `scripts/cv_fix_anchor_intel.py:61-77` and `scripts/platformkit/tracking/g195_cv2_rng_route_determinism.py:26-47` are omitted; the bar says none skipped (`g339_prereg_2026-09-08.md:11`).
ACCEPTANCE CENSUS FAIL: memo claims 8 frame joins (`memo:15`); `joins_on_frame=yes` occurs 7 times in `readers.csv:2-38`.
ACCEPTANCE WRITER PASS: separate seven-field ball output and player output reproduce (`src/pipeline/unified_pipeline.py:1982-1991,4020-4042`; `memo:26-27`).
ACCEPTANCE JOIN PASS: claimed/reproduced wnba_05 907/1000, 93 absent, distance n=904; wnba_02 803/1000, 197 absent, distance n=803; all extrema/quantiles exact (`join_report.csv:2-3`; `ball_join.py:37-80`).
ACCEPTANCE PROPOSAL/LIMITS PASS: concrete consumer and columns (`G339_PROPOSED_ball_join_consumer.md:3-15`); `NOT VERIFIED` exists (`memo:51-56`); EYE CHECK NONE (`memo:41`).
A1 FAIL: master lacks both G339 module and test (`git cat-file -e` exit 128); absolute-path pytest resolves the candidate tree, so it is not a master-code rerun.
A2-A4 PASS: direct full-file reruns match; raw ball rows/unique frames are 1000/1000 for each source; no render decision set (`join_report.csv:2-3`).
A5 FAIL / A6 NOT RUN / A7 FAIL: reader census omissions above; user scope forbids landing; four relative input paths in `memo:9,34` are absent here, though matching files under master `data/tracking/` reproduced by digest.
TEST: `python -m pytest tests/platformkit/test_g339_ball_join.py -q -p no:cacheprovider` -> 1 passed.
TEST: from master, `python -m pytest C:\Users\neelj\nba-track-a13\tests\platformkit\test_g339_ball_join.py -q -p no:cacheprovider --rootdir=C:\Users\neelj\nba-ai-system` -> 1 passed via candidate resolution, not credited to A1.
TEST: same command plus `--import-mode=importlib` -> 1 passed via candidate resolution, not credited to A1.
LOC PASS: candidate touches no `.py`; cumulative G339 files are 100 LOC harness and 31 LOC test, both <=300 (`ball_join.py:1-100`; `test_g339_ball_join.py:1-31`).
B1 PASS: union-frame denominator precedes all counts; no row exclusion (`ball_join.py:39-80`).
B2 PASS: report header only adds fields and its sole reader is updated (`join_report.csv:1`; `memo:35`); no reader behavior changed.
B3 PASS: no absence gate was added (`ball_join.py:37-63`).
B4 PASS: no claim lifecycle exists (`ball_join.py:37-80`).
B5 PASS: local reads only; no deployed-tree write (`memo:5,34`).
B6 PASS: no module moved or retired (`ball_join.py:1`).
B7 PASS: both complete 1000-row tables were read (`memo:34`; `join_report.csv:2-3`).
B8 PASS: descriptive join, no fit (`memo:46`).
B9 PASS: 2000 raw rows are 2000 unique frame keys; denominators vary (`join_report.csv:2-3`).
B10 PASS: candidate changes no harness bar (`g339_prereg_2026-09-08.md:10-11`).
Q1 PASS: prefix digest equals embedded `c7076a...c2dee`; prereg commit `dc2939d4` predates measurement (`g339_prereg_2026-09-08.md:14`).
Q2 PASS: no charged trial (`memo:46`).
Q3 PASS: sealed bar unchanged (`g339_prereg_2026-09-08.md:10-11`).
Q4 PASS: no OOS score or meta-learner (`memo:46`).
Q5 PASS: no AHEAD claim (`memo:46`).
Q6 PASS: candidate-added memo, report, and ledger line scan is clear (`memo:58`).
Q7 FAIL: construct enumeration is not exhaustive because confirmed semantic readers are absent (`memo:20`; sources above).
Q8 PASS: premise was remeasured and remains true (`memo:7`).
CORRECTION DIFF: add the two omitted reader rows above, rerun the six-pattern semantic census, then replace the 37 and per-class totals (`readers.csv:2-38`; `memo:15-20`).
CORRECTION DIFF: `memo:15` change `8 join by frame` to `7 join by frame` for the current CSV.
CORRECTION DIFF: replace stale `memo:9` no-source statement with the exact master data paths and reproduced ball digests `805c6479...ca1d` / `79537a95...b8510`, consistent with `memo:34`.
2026-09-08 | tracking | G339 | joins 907/1000 and 803/1000 reproduced; census artifact has 37 rows but at least 2 semantic readers are omitted and frame-join count is 7 versus claimed 8 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: the four-class census has no truthful bucket for EventDetector's runtime `ball_pos`; it is not table-reading but is not ball-blind (`src/tracking/event_detector.py:194-234`).
NEW GAP: contract A1 is not executable before landing when master lacks the candidate module/test; an absolute test path imports the candidate tree.
