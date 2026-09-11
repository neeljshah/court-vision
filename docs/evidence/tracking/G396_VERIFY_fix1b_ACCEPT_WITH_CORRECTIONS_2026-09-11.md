VERDICT: ACCEPT WITH CORRECTIONS
Candidate: e61308810521751e4d134c65ca610a61d010dcba; full 94-path diff reviewed (52 added, 42 modified, 0 deleted/renamed).
PREMISE PASS: independently reproduced 60 G392 rows, sol 30, terra 20, joint 20, real_scored=false, 49 retained natives, 30 contexts, 180 tiles, 11 failures, and 0 prior permitted dispatches (spec:5; memo:5).
REPRODUCTION PASS: raw qualification answers reproduce Astra 30/30, Sol 27/30, joint 27/30, 30 unique controls and all 60 responses (qualification/summary.json:2).
REPRODUCTION PASS: raw real answers reproduce 25 VISIBLE and 5 ABSENT per rater, 46/42 fragments, 6 pairs, 3 audited passes, 3/30 all-state and 3/22 visible-conditioned accounting (real_summary.json:2).
REPRODUCTION PASS: landed, repeat_1 and repeat_2 inventories are the same 108 unique paths and all 108 byte digests match; all five tree digests reproduce the claims (repeats.json:21).
ACCEPTANCE-1 PASS: both fixed raters and the joint set clear 27/30 with the sealed point clauses and no retry (spec:21; eligibility.json:2).
ACCEPTANCE-2 PASS: two qualified raters account for 30/30 retained states and all 6 pairs have independent 9-point audits under the fixed rules (spec:22; memo:23).
ACCEPTANCE-3 PASS: identities, pixel/truth disjointness, blindness receipts and score/render reproduction hold; no production or fitter change (spec:23; memo:29).
EYE/EVIDENCE PASS: even indices 001/006/012/018/024/030, all 6 cards and all 12 strips agree with tables; all 357 unique SHA256SUMS paths exist and match, with no self-entry (memo:29; SHA256SUMS:1).
LOC PASS: g396_finish.py:121, g396_render.py:237 and test_g396_third_rater_paint.py:100 are <=300.
ADDITIVITY PASS: all 42 replaced images are retained byte-exact under renders_pre_fix1b; existing repeat fields and default CLI behavior remain; no field/status/path was removed (g396_finish.py:60; g396_render.py:175).
MEMO LIMITS PASS: substantive NOT VERIFIED list and explicit scope boundary are present (memo:31-38).
TEST PASS: `python -m pytest tests/platformkit/test_g396_third_rater_paint.py -q` -> 10 passed in 0.71s; `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 0.63s.
TEST SCOPE PASS: repository search finds no existing test importing touched modules g396_finish or g396_render (test_g396_third_rater_paint.py:6-7).
B1 PASS: every state remains in the 30-state denominator and the 22-state conditional denominator is named (real_summary.json:3-17).
B2 PASS: new repeat fields are additive and their only reader is checked; no old field/status is removed (repeats.json:2-70; test_g396_third_rater_paint.py:88-100).
B3 PASS: missing control output fails while ABSENT/UNKNOWN real states remain accounted (g396_protocol.py:54-60; real_summary.json:13-17).
B4 PASS: dispatch state is terminal and retry/substitution remains forbidden (eligibility.json:15-17).
B5 PASS: PC-only evidence records no pod or production deployment (memo:36-38).
B6 PASS: no path is deleted/renamed and both extended modules remain directly runnable (g396_finish.py:120-121; g396_render.py:236-237).
B7 PASS: all 30 controls/states are enumerated and the verifier sample is evenly spread (spec:21-23; memo:29).
B8 PASS: controls use frozen truth and no fitted displacement or post-score correction (g396_prereg_2026-09-11.md:35-48).
B9 PASS: qualification has 30 unique controls and real accounting has 30 unique contexts (qualification/summary.json:3; real_summary.json:13).
B10 PASS: candidate changes no gate constant; 27, 3 px, 60 px, 6 px and 8/9 match the spec (g396_protocol.py:7-13; spec:21-23).
Q1 PASS: seal 18124321ca2b0daf315283e16ec79f06c5498cd2bb6948bd65f2893c2976dd12 verifies and commit 8ee65b437 predates metrics (g396_prereg_2026-09-11.md:66; memo:42).
Q2 PASS (N/A): this row introduces no charged trial or multiplicity claim (memo:38).
Q3 PASS: all preregistered bars are unchanged (g396_prereg_2026-09-11.md:42-56; g396_protocol.py:7-13).
Q4 PASS (N/A): no OOS comparison or meta-learner is scored (memo:38).
Q5 PASS (N/A): no AHEAD result is reported (memo:38).
Q6 PASS: independent scan of candidate document additions and the new ledger line finds 0 non-opaque hits (q6_fix1b_scan.json:101-103).
Q7 PASS: both 30-control sets and all 30 real contexts are exhaustively enumerated (spec:9-17; memo:9-27).
Q8 PASS: the premise receipt was committed before practice, qualification and real scoring (g396_prereg_2026-09-11.md:17-25; memo:3-5).
CORRECTION DIFF: memo:60 `(9 passed)` -> `(10 passed)`.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G396_2 | premise 49/30/180 with 11 failures; qualification Astra 30/30, Sol 27/30, joint 27/30; real accounting 3/30 and 3/22; render replay 108/108 | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: requested specs/G396_2_spec.md is absent from all history; the tracked preregistration cites specs/G396_spec.md:6.
NEW GAP: spec:24 names input_manifest.csv, control_disjointness.csv and raw_answers/, while the artifact uses differently named equivalents.
NEW GAP: master lacks tests/platformkit/test_g396_third_rater_paint.py, so contract A1 cannot run there before landing.
NEW GAP: test_g396_third_rater_paint.py:88-100 checks keys and row count but not digest equality or identical values, and imports neither touched module.
NEW GAP: g396_render.py:161-167 fixes clipped-strip crosshairs at (125,125); native points with x<125 in G396_013/G396_020 are shifted in strips, while audit cards retain native coordinates.
