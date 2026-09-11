VERDICT: REJECT
Candidate: fead21999f31c18c02b8183207683b204de6bc63; full 207-path diff reviewed (201 added, 6 modified, 0 deleted/renamed).
PREMISE PASS: independently rehashed the G387 census/cache and reproduced 49 retained natives, 30 contexts, 180 tiles, 11 parent failures, 30 controls, Sol 30, Terra 20, joint 20, and real_scored=false.
REPRODUCTION PASS: raw qualification answers reproduce Astra 30/30, Sol 27/30, joint 27/30 on the same 30 fresh controls with all 60 answers present.
REPRODUCTION PASS: raw real answers reproduce 25 VISIBLE and 5 ABSENT/UNKNOWN states per rater, 6 candidate pairs, 3 audited passes, 3/30 all-state accounting, and 3/22 conditional-visible accounting.
ACCEPTANCE-1 PASS: Astra, Sol, and joint clear the frozen 27/30 bar; 3 px, finite band, 60 px span, frozen instructions, and no retry are evidenced.
ACCEPTANCE-2 PASS: two qualified raters classified all 30 retained states; all 6 compatible pairs were independently audited at 3 px and 3/6 passed the 8-of-9 rule.
ACCEPTANCE-3 FAIL: exact IDs, blindness, and score/table replay are evidenced, but repeats.json contains no render digests and the repeat tree contains no renders; fresh-process render-byte identity is not demonstrated.
EYE CHECK PASS: inspected qualification 001/006/012/018/024/030, real renders 001/006/012/018/024/030, all 6 audit cards, and all 12 rater audit strips; displayed adjudications agree with the tables.
EVIDENCE HASH PASS: independently checked all 313 SHA256SUMS entries; 0 missing and 0 digest mismatches, with the manifest correctly excluding itself.
LOC PASS: g396_finish.py 55, g396_q6_scan.py 61, g396_render.py 150, and test_g396_third_rater_paint.py 85; all are <=300 LOC.
ADDITIVITY PASS: no candidate deletion/rename, production change, feature-flag enablement, or data/registry write; retained states and existing outputs remain additive.
MEMO LIMITS PASS: memo:31-36 provides a substantive NOT VERIFIED list and memo:38 states the production boundary.
TEST PASS: python -m pytest tests/platformkit/test_g396_third_rater_paint.py -q -> 9 passed in 0.70s.
TEST PASS: python -m pytest tests/platformkit/test_loc_rail_scope.py -q -> 1 passed in 0.63s.
TEST SCOPE PASS: no test imports g396_finish, g396_q6_scan, or g396_render, so there are no additional importer tests to run.
B1 PASS: all 30 real states are retained; the visible-only denominator is separately labeled and was preregistered before scoring.
B2 PASS: the candidate removes no schema field/status and repository search finds no reader of the three modified implementation modules.
B3 PASS: missing control responses fail qualification; ABSENT/UNKNOWN real responses remain accounted for.
B4 PASS: there is no claim/reclaim path.
B5 PASS: the artifact is PC-only and makes no production or deploy change.
B6 PASS: there are no deleted or renamed paths and no orphaned reader.
B7 PASS: visual checks use spread indices and the quantitative accounting covers all 30 controls and all 30 real states.
B8 PASS: the controls are generated from frozen truth and no fitted offset or post-hoc correction is used.
B9 PASS: qualification has 30 unique controls and real accounting has 30 unique contexts.
B10 PASS: the 27/30, 3 px, finite-band, 60 px, 6 px, and 8-of-9 constants match the frozen spec; the protocol/spec diff is empty.
Q1 PASS: the independently verified seal predates metric-bearing artifacts.
Q2 PASS: no charged-trial or multiplicity claim is introduced.
Q3 PASS: preregistered bars are unchanged.
Q4 PASS: no OOS candidate or meta-learner is involved.
Q5 PASS: no AHEAD result is reported.
Q6 PASS: independent scan of the intended 217-file candidate scope found 0 non-opaque reserved-language hits.
Q7 PASS: the qualification set has 30 distinct controls and the real set has 30 distinct contexts.
Q8 PASS: the premise checkpoint predates practice metrics, qualification dispatch, and real scoring.
REQUIRED DIFF: rerun every render in two fresh processes from raw judgments; add per-render-tree process_1/process_2/matches_landed digests to repeats.json, refresh SHA256SUMS, and amend memo:29.
CORRECTION DIFF: memo:9 should say pixel/truth disjoint within G396 and against G392, with context/tile disjointness only between the two G396 sets; each G396 set shares 30 context/tile pairs with G392.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G396 | qualification Astra 30/30, Sol 27/30, joint 27/30; real accounting 3/30 states and 3/22 visible after 3/6 audited pairs; fresh-process render-byte reproduction absent | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: the spec evidence list names input_manifest.csv, control_disjointness.csv, and raw_answers/, while the artifact supplies differently named equivalents.
NEW GAP: g396_prepare.controls_disjoint checks a combined tuple, so reuse of only a pixel hash or only a truth tuple could escape that helper; the submitted artifacts are independently clean.
NEW GAP: the main checkout does not track the G396 spec test, so contract A1 could not be rerun there.
