VERDICT: REJECT
CANDIDATE: d6202fbd06769e923c237b84d5572812f446eaab; applied scope is G404_spec.md:21-27 plus B1-B10 and Q1-Q8.
ACCEPTANCE Gate/source PASS (status handling): 14 resolved rows across 2 competitions is below 30, so PARTIAL is required; G404_spec.md:25, memo:1,9.
ACCEPTANCE Rater reliability/usability PASS (status handling): 0 controls and 0 ratings leave the stage incomplete, with no joint-bar claim; G404_spec.md:26, summary.json:21-37.
ACCEPTANCE Yield/reference PASS (status handling): no 300-key draw or yield conclusion was made and both prior reference sets are reported untouched; G404_spec.md:27, summary.json:6-7.
B1 PASS: exclusions are named before counting and the whole 14-row census remains visible; g404_census.py:88, memo:9.
B2 PASS: the diff adds schemas/statuses and removes or renames none; the only reader found resolves; test_g404_play_gated_growth.py:90.
B3 PASS: missing supply maps to PARTIAL, not a negative item classification; memo:1,9.
B4 PASS: no claim queue or reclaim path is touched; memo:37.
B5 PASS: recorded pod work is scratch-only and the deployed tree is unchanged; memo:37.
B6 PASS: no module moved or retired; all new imports in the sole reader resolve; test_g404_play_gated_growth.py:90.
B7 PASS: both 30-card strata use the sealed full-stratum even indices; g404_audit.py:29, gate_audit_draw.csv:1.
B8 PASS: the gate is frozen nearest-reference inference with no fit; g404_gate.py:1, memo:11.
B9 PASS: remeasurement found 386/386 unique keys and pixel digests, and 60/60 unique audit keys/cards; candidate_grid.csv:1, gate_audit_draw.csv:1.
B10 PASS: 30-game, 30-card, 27/30 and 24/30 bars match the spec; g404_census.py:18, g404_audit.py:22, g404_finish.py:123.
Q1 PASS: LF seals independently match and commits 5112012e9/039ac8811 precede scored artifacts; prereg.md:118, amendment_A1.md:58.
Q2 PASS (not applicable): no charged comparison or K is reported; memo:1.
Q3 PASS: no acceptance threshold moved; G404_spec.md:25-27, g404_finish.py:123.
Q4 PASS (not applicable): no OOS comparison or meta-learner ran; memo:37.
Q5 PASS (not applicable): no AHEAD result is reported; memo:1.
Q6 FAIL: the saved scan reports claim_context_hits=6 from six literal numeric constants in its own source, contradicting memo:35; q6_scan.json:2, g404_q6_scan.py:29.
Q7 PASS: the sampled audit is 30 admitted plus 30 excluded and both index sets reproduce exactly; G404_spec.md:25, g404_audit.py:29.
Q8 PASS: the whole census was measured first and reproduces 14 rows/14 identities/2 competitions; memo:9, premise.json:3-8.
MEMO NOT VERIFIED PASS: explicit limitations begin at memo:28.
TEST PASS [cwd=C:/Users/neelj/nba-track-a18]: python -m pytest tests/platformkit/test_g404_play_gated_growth.py -q -> 12 passed in 1.36s.
TEST MASTER [cwd=C:/Users/neelj/nba-ai-system]: python -m pytest tests/platformkit/test_g404_play_gated_growth.py -q -> file absent, exit 4, 0 collected.
READER SWEEP: git grep -l g404_ -- tests -> only tests/platformkit/test_g404_play_gated_growth.py; run above.
LOC PASS: touched Python files are 25-195 lines; test is 155 lines; all <=300.
REPRODUCED vs claimed: premise 14/2 vs 14/2; decoded 22,756; grid 386 unique; gate 187/199; audit 26 admitted PLAY and 25 excluded NONPLAY; all match memo:9-18.
ARTIFACT PASS: 28/28 SHA256SUMS, 25/25 present input hashes, 6/6 retained-source hashes, and 60/60 receiver-card hashes match; render inspection covered all 60 cards.
CORRECTION DIFF: at g404_q6_scan.py:29 replace the tuple with NUMERIC_PATTERNS = (_word(43,49,56,46,51,56), _word(48,46,49,49,57), _word(43,53,52), _word(55,56,46,49,49), _word(56,46,57,52), _word(53,52,46,53,55)).
CORRECTION DIFF: regenerate q6_scan.json with claim_context_hits=0, then refresh route_digests.txt, SHA256SUMS, and memo:35.
CORRECTION DIFF: memo:9, summary.json:15 and ledger:769 should say 14 resolved exact-ID-disjoint candidates; relation to older alternate uploads remains unresolved.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G404 | premise remeasured as 14 resolved exact-ID-disjoint candidates across 2 competitions vs 30 required; 386 unique gate candidates (187 admitted/199 excluded); joint audit not evaluable; Q6 scan has 6 numeric claim-context hits | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: q6_scan.json records a file count but no complete path manifest, so exact changed-text scan coverage cannot be replayed.
NEW GAP: master 49ce49537 lacks the G404 test, so contract A1 cannot run there before landing.
NEW GAP: gate_audit_draw.csv card_path values point to absent pod scratch paths; the 60 receiver copies exist and hash-match but are not mapped in the table.
NEW GAP: RESULTS_LEDGER.md:769 is dated 2026-09-12 although the candidate and verification date are 2026-09-11.
NEW GAP: targeted git add and the sanctioned lane_commit.py helper both failed at the external linked-worktree index.lock ACL; no verifier commit object was created.
