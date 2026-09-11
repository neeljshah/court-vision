VERDICT: ACCEPT WITH CORRECTIONS
Candidate: `438c0fdd6`; row result remains PARTIAL, protocol not qualified.
PASS ACCEPTANCE premise: independently 60 states, 49 retained/ready/hash+dimension matches, 0 strokes, old controls 19/30, old real 1/30, visibility 22/6/2, and 30 unique even-selected contexts (`input/premise_receipt.json:2`).
PASS ACCEPTANCE controls: sealed 10/30 and named LIMIT 13/30 both-rater admissible vs unchanged 27/30; PARTIAL is correct (`controls/control_verdict.json:2`, `controls/control_verdict_limit.json:2`).
PASS ACCEPTANCE audited recovery after correction: 30/30 accounted, 0/30 and 0/23 visible audited; stable one-to-one pairing is 8 pairs, not claimed 9, and all 8 fail the sealed rule (`per_frame.csv:2`, `pairing.csv:2`).
PASS ACCEPTANCE identity/repeatability: 179/179 manifest entries plus manifest digest match; 49 natives, 180 tiles, and 30 control pixels match receipts; independent metrics reproduce after the pair correction (`SHA256SUMS:1`).
PASS A2-A5/A7: recomputation, even render samples 01/03/05, uniqueness, reader search, and every memo-named evidence path checked (`g388_paint_band_protocol_2026-09-11.md:3`).
PASS B1: fixed 30-control and 30-real denominators retain missing/absent states (`summary.json:11`).
PASS B2: diff is 180 additions plus one ledger append; no field/status removal, rename, or existing-reader behavior change (`scripts/platformkit/tracking/g388_protocol.py:1`).
PASS B3: absent evidence remains charged, including 10 missing terra responses (`controls/control_results.csv:2`).
PASS B4: no claim/reclaim lifecycle is introduced (`scripts/platformkit/tracking/g388_score.py:98`).
PASS B5: PC only; no deployed-tree write is claimed or present (`g388_paint_band_protocol_2026-09-11.md:32`).
PASS B6: no module moved/retired and no import or command reference is orphaned (`scripts/platformkit/tracking/g388_protocol.py:1`).
PASS B7: indices are 30 unique inclusive positions across all 49 retained contexts, not a head slice (`G388_spec.md:20`).
PASS B8: known-band controls use sealed generated truth; no fitted points are treated as independent (`controls/known_points.csv:2`).
PASS B9: units are 30 unique control contexts and 30 unique real contexts (`controls/control_verdict.json:3`, `per_frame.csv:2`).
PASS B10: 27/30, 3 px, 6 px, 60 px, and 8/9 remain unchanged (`scripts/platformkit/tracking/g388_protocol.py:19`).
PASS Q1: prereg seal verifies and commit `6662a3621` predates all premise/score commits (`g388_prereg_2026-09-11.md:90`).
PASS Q2: no charged trial or comparative model metric is present (`g388_paint_band_protocol_2026-09-11.md:1`).
PASS Q3: every acceptance bar is byte-consistent with the spec (`G388_spec.md:20`).
PASS Q4: no OOS comparison or meta-learner is run or claimed (`g388_paint_band_protocol_2026-09-11.md:32`).
PASS Q5: no AHEAD result is claimed (`g388_paint_band_protocol_2026-09-11.md:1`).
PASS Q6: 161 added text files plus the added ledger line have 0 non-opaque vocabulary hits; five digest-substring hits are exempt (`SHA256SUMS:28`, `controls/known_points.csv:20`).
PASS Q7: both sampled decision sets have n=30 and the real draw is even (`G388_spec.md:20`, `G388_spec.md:21`).
PASS Q8: premise was measured before ratings and reproduced here (`input/premise_receipt.json:4`).
PASS LOC: all 8 touched Python files are <=300 lines; maximum is `g388_protocol.py` at 278 (`scripts/platformkit/tracking/g388_protocol.py:1`).
PASS READERS: only `tests/platformkit/test_g388_paint_band_protocol.py` imports a touched G388 module; it was run (`test_g388_paint_band_protocol.py:7`).
PASS MEMO LIMITS: a substantive NOT VERIFIED list is present (`g388_paint_band_protocol_2026-09-11.md:33`).
REPRODUCED: premise exact; controls 10/30 and LIMIT 13/30; repeat p50 13.89 along/0.06 perpendicular-distance change and 9/10 verdicts; real 0/30, 0/23, 8/30 contexts, 8 one-to-one pairs, 0 sealed/audited, family disagreements 19/30; retrospective 1/57 and 4/12. Claimed values match except pair total 9.
TEST: `python -m pytest tests/platformkit/test_g388_paint_band_protocol.py -q` -> 11 passed.
TEST: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed.
TEST: `cd C:\Users\neelj\nba-ai-system && python -m pytest tests/platformkit/test_g388_paint_band_protocol.py -q` -> exit 4, 0 tests; file absent on master.
CORRECTION DIFF: delete reused `pairing.csv:8`; set `per_frame.csv:22` candidate pairs 2 -> 1 and `summary.json:5` total 9 -> 8.
CORRECTION DIFF: memo lines 24-27 and the existing G388 ledger row: 9 -> 8; refresh affected digests. The 0/30 outcome is unchanged.
CORRECTION DIFF: memo line 40: 1 opaque hit -> 5 (four in `SHA256SUMS`, one in `known_points.csv`); 0 non-opaque remains.
RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G388 | controls 10/30 sealed and 13/30 LIMIT vs 27/30; one-to-one audit 0/8 pairs across 8/30 contexts; premise 60 states and 49 native matches | PARTIAL (verified: codex-sol, contract A/B/Q)
NEW GAP: Master lacks the G388 spec test, so contract A1 cannot run there before landing.
NEW GAP: `finalize.py:13` can only emit threshold-passing pairs while committed audit tables were expanded separately; no replay or test checks one-to-one candidate enumeration.
NEW GAP: Repeat p90 values use the higher order statistic and unsigned distance change without naming either convention; vector-component p90/max are 0.90/14.33 px.
NEW GAP: Control pixels and inherited tiles verify now but live only in temporary caches, not the committed matching evidence directory.
