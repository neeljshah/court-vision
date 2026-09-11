VERDICT: REJECT
CANDIDATE: 7a20c111c3200e4c739f7038951567798986fffe; scope is G404_spec.md:23-27 plus B1-B10 and Q1-Q8.
ACCEPTANCE Gate/source PASS (status): raw census gives 14 resolved exact-ID-disjoint candidates in 2 competitions vs 30, so PARTIAL is required; G404_spec.md:25, memo:9.
ACCEPTANCE Reliability/usability PASS (status): 0 controls and 0 ratings are incomplete, with no joint-bar claim; G404_spec.md:26, summary.json:14,22,29.
ACCEPTANCE Yield/reference PASS (status): 0 planned keys means no yield conclusion; 530 accepted and 116 unused remain separate; G404_spec.md:27, summary.json:5,19,27.
B1 PASS: all 79 raw census rows form 14 whole-pool groups and exclusions are applied before counting; g404_census.py:88-108,127-153.
B2 FAIL: parent run-level returncode values 0 changed to 1; pre_fix1b/repeats.json:29,48, repeats.json:32,68. No keys were removed, but status semantics changed.
B3 PASS: missing supply returns PARTIAL, not a negative item class; g404_score.py:62-67, memo:1.
B4 PASS (not applicable): no claim/reclaim state exists in the added G404 routes; g404_census.py:124-158.
B5 PASS: evidence records scratch-only compute and no deployed-tree write; memo:37.
B6 PASS: cumulative G404 diff has no renamed/deleted module; its sole importing test resolves all imports; test_g404_play_gated_growth.py:7-22,90-95.
B7 PASS: delivered audit keys exactly reproduce 30 even indices in each full 187/199 stratum; g404_audit.py:29-35,46-50,77-90.
B8 PASS: inference uses the frozen 240-reference route with no fit or cutoff change; memo:11.
B9 PASS: 386/386 grid keys and pixel hashes plus 60/60 audit keys/card hashes are unique; summary.json:6,20-24.
B10 PASS: 27/30, 24/30, 30-game, 300-key and 0.60 bars match the spec; G404_spec.md:25-27, g404_score.py:35-52.
Q1 PASS: LF seals reproduce at prereg.md:118 and amendment_A1.md:58; commits 5112012e9 and 039ac8811 precede scored d6202fbd0.
Q2 PASS (not applicable): no charged comparison or launch K is reported; memo:1.
Q3 PASS: sealed bars match G404_spec.md:25-27 and summary.json:31,35-36.
Q4 PASS (not applicable): no OOS comparison or meta-model ran; memo:1.
Q5 PASS (not applicable): no AHEAD result is reported; memo:1.
Q6 PASS: independent scan of all 126 candidate-added lines found 0 prose and 0 numeric hits; q6_scan.json:1-62.
Q7 PASS: both sampled strata contain 30 evenly selected rows and exhaustive key comparison matches; gate_audit_seal.json:2-7, g404_audit.py:29-35.
Q8 PASS: raw census remeasurement gives 79 sections, 14 eligible games, 2 competitions, 0 exact-ID overlap with the independently unioned 101 old IDs; memo:9.
MEMO NOT VERIFIED PASS: explicit limitations are listed; memo:28-33.
INTEGRITY PASS: 33/33 SHA256SUMS, 6/6 retained-source hashes, and 60/60 receiver card hashes/bytes/native dimensions match; SHA256SUMS:1-34.
LOC PASS: candidate touches 0 .py; cumulative G404 has 11 helpers (max 195) and one 173-line test, all <=300.
TEST PASS: python -m pytest tests/platformkit/test_g404_play_gated_growth.py -q -> 13 passed in 0.88s; it is the only existing test importing a G404 module.
REPRODUCED vs claimed: premise 79 sections, 14/30 candidates, 2 competitions, 101 old IDs, 0 exact-ID overlap; all match memo:7-9.
REPRODUCED vs claimed: 530 boxes/27 games, 116 unused, 22,756 decoded, 386 unique grid, 187/199 gate, 30/30 audit, reviewer 26 PLAY/25 NONPLAY, retention 6/8; all match memo:7-23.
CORRECTION DIFF: repeats.json:32,68 change run-level returncode 1 -> 0; keep nested census returncode 1 at lines 35,71.
CORRECTION DIFF: repeats.json:48,84 describe run-level returncode as the repeat-wrapper exit code; then refresh only its SHA256SUMS entry.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G404 | 14 exact-ID-disjoint candidates across 2 competitions vs 30 required; 386 unique candidates (187 admitted, 199 excluded); parent repeat run status changed from 0 to 1 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: G404_spec.md:28 names disjointness.csv, but the delivered path is game_disjointness.csv with no path alias.
NEW GAP: test_g404_play_gated_growth.py:1-173 never validates repeats.json run-level fields or status semantics.
NEW GAP: targeted git add could not create the linked-worktree index.lock because the shared Git directory is outside this workspace's write boundary.
