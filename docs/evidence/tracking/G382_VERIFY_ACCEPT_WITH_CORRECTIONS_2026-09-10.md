VERDICT: ACCEPT WITH CORRECTIONS
Candidate: 9dc949775; full 61-path commit diff reviewed; only this verifier memo is added.
ACCEPTANCE PASS - 60 unique planned frames = 49 retained + 11 decode failures; 49 dual-rated; all unique strokes/supports classified; repeat receipts match; no fit (g382_court_stroke_specificity_2026-09-10/summary.json:3).
PREMISE PASS - independently reproduced G379 0/6 sections and 0/352 raw acceptances; no earlier quantitative receipt at the pre-measurement base (g379_broadcast_geometry_2026-09-10/summary.json:1).
B1 PASS - raw enumeration includes all 6,860 unique strokes and 460,484 unique supports in each mode; no post-filter denominator (g382_court_stroke_specificity_2026-09-10/strokes.csv:1).
B2 PASS - modified CSV headers and mask JSON keys are unchanged; final_area_px remains additive and all readers/importers were surveyed (scripts/platformkit/tracking/g382_adjudicate.py:18).
B3 PASS - absent mask coverage remains UNKNOWN and decode failures remain explicit, never a pass (scripts/platformkit/tracking/g382_masks.py:12).
B4 PASS - this audit has no claim/reclaim path; incomplete rater coverage remains INCOMPLETE (scripts/platformkit/tracking/g382_adjudicate.py:181).
B5 PASS - pod commands are measurement-only and the sealed protocol forbids deployment (g382_court_stroke_specificity_2026-09-10/g382_prereg_2026-09-10.md:11).
B6 PASS - no module moved or retired; the sole test importer remains live (tests/platformkit/test_g382_court_stroke_specificity.py:71).
B7 PASS - 30 indices span 0..59 with gaps 2/3; five selected failures have explicit cards (scripts/platformkit/tracking/g382_render.py:24).
B8 PASS - no fitting or residual-to-fit evidence is used (g382_court_stroke_specificity_2026-09-10/g382_prereg_2026-09-10.md:105).
B9 PASS - uniqueness is 60/60 frames, 6,860/6,860 strokes, and 460,484/460,484 supports (g382_court_stroke_specificity_2026-09-10/summary.json:11).
B10 PASS - route files are byte-unchanged from the base; 0.80 cut and 2 px dilation match the seal (scripts/platformkit/tracking/g382_score.py:18).
Q1 PASS - seal 252ca46be4e8f8648283dfdb6f4056bdf3de8e83ff61729d6601087798f45ed8 recomputes; seal commit d04af9229 predates first measurement 2c3f1c9b1 (g382_court_stroke_specificity_2026-09-10/g382_prereg_2026-09-10.md:122).
Q2 PASS - no charged comparative trial applies (g382_court_stroke_specificity_2026-09-10/g382_prereg_2026-09-10.md:105).
Q3 PASS - every binding bar is unchanged (g382_court_stroke_specificity_2026-09-10/g382_prereg_2026-09-10.md:97).
Q4 PASS - no OOS or meta-learner claim applies (g382_court_stroke_specificity_2026-09-10/g382_prereg_2026-09-10.md:105).
Q5 PASS - no AHEAD claim is made; scope is explicitly limited (g382_court_stroke_specificity_2026-09-10.md:41).
Q6 PASS - independent scan of 220 text inputs plus the committed ledger addition found 0 findings (g382_court_stroke_specificity_2026-09-10/q6_scan.json:297).
Q7 PASS - the 60-frame construct and every nested stroke/support are exhaustively enumerated (g382_court_stroke_specificity_2026-09-10/frames.csv:1).
Q8 PASS - premise re-measured first and remains true (g382_court_stroke_specificity_2026-09-10.md:6).
TEST PASS - `python -m pytest tests/platformkit/test_g382_court_stroke_specificity.py -q` -> 8 passed in 1.15s; this is the only existing test file importing the touched module.
LOC PASS - scripts/platformkit/tracking/g382_adjudicate.py:1 = 199; tests/platformkit/test_g382_court_stroke_specificity.py:1 = 99; both <= 300.
REPRODUCED - claimed vs measured: strokes 0/6,860 to 20/6,860 = 0 to 0.002915; painted supports 163/460,484 to 4,861/460,484 = 0.000354 to 0.010556; conservative non-court categories 128,552/460,484 = 0.279167; repeats true in both modes (g382_court_stroke_specificity_2026-09-10/repeats.json:2).
NOT VERIFIED PASS - explicit limitations list is present (g382_court_stroke_specificity_2026-09-10.md:38).
CORRECTION - g382_court_stroke_specificity_2026-09-10.md:36: replace the no-failure-card sentence with: "The evenly spaced set includes five decode failures (4, 24, 39, 49, 59); those are explicit missing-frame cards, and 25 cards carry pixels."
CORRECTION - g382_court_stroke_specificity_2026-09-10.md:6: insert "LF-normalised" before the stated SHA-256 and 6,196-byte size; the CRLF checkout is 6,396 bytes.
2026-09-10 | tracking | G382 | 49/60 frames; 6,860 unique strokes and 460,484 unique supports; painted-stroke share 0/6,860 to 20/6,860; painted-support share 163/460,484 to 4,861/460,484; repeat receipts identical | PARTIAL (verified: codex-sol, contract A/B/Q)
NEW GAP: Step 5's dilated continuous-support aggregate is absent from the memo; raw rows measure 163/460,484 conservative and 5,350/460,484 union, distinct from the union base-label count (scripts/platformkit/tracking/g382_score.py:88).
NEW GAP: Linked-worktree Git metadata is outside the writable root; targeted git add and the sanctioned lane_commit.py both failed at index.lock, so an external path-specific committer must commit this sole memo.
