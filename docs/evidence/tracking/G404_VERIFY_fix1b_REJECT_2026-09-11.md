VERDICT: REJECT
CANDIDATE: fa66caed578e002bf7a9eef0a89f87b1d8b5f168; scope is G404_spec.md:23-27 plus B1-B10 and Q1-Q8.
ACCEPTANCE Gate/source PASS (status): 14 is below 30 and alternate-upload relation is unresolved, so PARTIAL is required; G404_spec.md:25, premise.json:7,54.
ACCEPTANCE Reliability/usability PASS (status): 0 controls and 0 ratings are incomplete, with no joint-bar claim; G404_spec.md:26, summary.json:14,29.
ACCEPTANCE Yield/reference PASS (status): 0 planned keys means no yield conclusion; both prior sets remain untouched; G404_spec.md:27, summary.json:5,19,27.
B1 PASS: all 14 census rows remain in the denominator and exclusions are named before counting; g404_census.py:88, premise.json:7.
B2 FAIL: repeats.json removed each run's top-level returncode/stdout fields and nested replacements under routes; repeats.json:16,49; parent copy:29-30,48-49; g404_repeats.py:34-35.
B3 PASS: failed supply maps to PARTIAL rather than a negative item class; g404_play_gated_ball_growth_stage2_2026-09-11.md:1,9.
B4 PASS (not applicable): no claim/reclaim state is present in the touched routes; g404_census.py:161-166.
B5 PASS: candidate records scratch-only compute and no deployed-tree write; g404_play_gated_ball_growth_stage2_2026-09-11.md:37.
B6 PASS: no module moved; all touched-module imports resolve in the sole importing test; test_g404_play_gated_growth.py:90-94.
B7 PASS: delivered indices reproduce the sealed whole-stratum even draw for 187 and 199 rows; g404_audit.py:29, gate_audit_draw.csv:1.
B8 PASS: frozen nearest-reference inference is stated without fitting or cutoff changes; g404_play_gated_ball_growth_stage2_2026-09-11.md:11.
B9 PASS: remeasurement gives 386/386 unique frame keys and pixel hashes and 60/60 unique audit keys/cards; summary.json:6,21.
B10 PASS: 30-game, 30-card, 27/30 and 24/30 bars match the spec; G404_spec.md:25, g404_finish.py:126.
Q1 PASS: both LF seals validate and commits 5112012e9/039ac8811 are ancestors of the first scored commit; prereg.md:118, amendment_A1.md:58.
Q2 PASS (not applicable): no charged comparison or launch K is reported; g404_play_gated_ball_growth_stage2_2026-09-11.md:1.
Q3 PASS: no bar moved; G404_spec.md:25-27, summary.json:31,35-36.
Q4 PASS (not applicable): no OOS comparison or meta-model ran; g404_play_gated_ball_growth_stage2_2026-09-11.md:1.
Q5 PASS (not applicable): no AHEAD result is reported; g404_play_gated_ball_growth_stage2_2026-09-11.md:1.
Q6 PASS: independent scan of every candidate-added line found 0 non-exempt hits; saved claim_context_hits is 0; q6_scan.json:2.
Q7 PASS: the sampled audit is 30 admitted plus 30 excluded and both delivered index sets reproduce exactly; g404_audit.py:22,29.
Q8 PASS: independent whole-census remeasurement gives 14 exact-ID-disjoint candidates, 2 competition labels, 0 overlap with 101 old IDs; premise.json:1,7,53.
MEMO NOT VERIFIED PASS: explicit limitations are listed; g404_play_gated_ball_growth_stage2_2026-09-11.md:28-33.
ARTIFACT PASS: all memo-named paths exist; 33/33 SHA256SUMS, 11/11 route hashes, 6/6 retained sources and 60/60 receiver cards match; SHA256SUMS:1.
RENDER PASS: all 60 evenly drawn cards appear in the 6-by-10 contact sheet; summary.json:13,21.
TEST [candidate] PASS: python -m pytest tests/platformkit/test_g404_play_gated_growth.py -q -> 13 passed in 1.29s.
TEST [master] FAIL: python -m pytest tests/platformkit/test_g404_play_gated_growth.py -q -> file absent, exit 4, 0 collected.
READER SWEEP: the spec test is the only test importing g404_census, g404_finish or g404_q6_scan; test_g404_play_gated_growth.py:90,93-94.
LOC PASS: g404_census.py 171; g404_finish.py 159; g404_q6_scan.py 124; test_g404_play_gated_growth.py 173; all <=300.
REPRODUCED vs claimed: premise 14/2 vs 14/2; decoded 22,756; grid 386; gate 187/199; audit 26 admitted PLAY and 25 excluded NONPLAY; all numeric claims match memo:9-18.
CORRECTION DIFF: repeats.json:16,49 add top-level returncode=0 and stdout beside routes for both runs; retain routes and all per-table digests.
CORRECTION DIFF: memo:1 replace "14 eligible new games" with "14 resolved exact-ID-disjoint candidates; older alternate-upload relation unresolved."
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G404 | 14 exact-ID-disjoint candidates across 2 competition labels vs 30 required; 386 unique candidates (187 admitted, 199 excluded); repeat receipt removed two parent run fields | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: q6_scan.json:20 manifest omits three candidate-touched text files: the prior verifier memo, RESULTS_LEDGER.md and g404_census.py; independent added-line scan was clean.
NEW GAP: master f87336d19 lacks tests/platformkit/test_g404_play_gated_growth.py, so contract A1 cannot pass before landing.
NEW GAP: g404_finish.py:111 hardcodes the premise detail instead of formatting premise.json values, so a later rerun can emit stale detail.
NEW GAP: targeted git add and lane_commit.py both failed on the external linked-worktree index.lock ACL; no verifier commit object was created.
