VERDICT: REJECT
Candidate: a4a17902ef3105c410347645c5af2391d3d5a6ce; scope: G361_spec.md:38-56 and VERIFIER_CONTRACT.md:20-50 (B1-B10/Q1-Q8).
PREMISE PASS: snapshot recount is 892 rows/884 distinct ids; committed census reports 0/809 complete bindings, matching claimed 892/884 and 0/809 (census.csv:2,12,19).
HEADLINE PASS: raw artifacts reproduce 884/884 mappings, classes 19/22/843, 0 collisions over 690 parsed pairs, and 21/31 sections satisfying the sealed rule (ledger_links.csv:1-885; alignment.csv:1-694).
ACCEPTANCE FAIL: the nine-tick fiba section is ALIGNED instead of UNKNOWN, and summary collision_count=1 is the 194-id UNKNOWN sentinel bucket, not a parsed collision (ledger_links.csv:544; summary.json:30).
UNIQUENESS PASS: 884/884 mapping ids, 31/31 sampled ids, and 693/693 (game_id, landmark) keys are unique; the memo's 403 alignment rows should be 693 (alignment.csv:1-694; memo:21).
SAMPLE PASS: 632 eligible sorted ids with step floor(632/30)=21 reproduce the exact 31-row sample; 31 source ids are distinct (sample_census.csv:1-885; sections.csv:1-32).
EYE FAIL: 23 strips exist, all <=200 KB (max 162630 B); an even six-strip inspection showed readable paired frames, but the required count is 30 (G361_spec.md:44; memo:37-38).
EVIDENCE PASS WITH CORRECTION: all 38 manifest targets exist; 30 match current bytes and 8 match LF-normalized bytes; the claimed manifest digest is LF-normalized (SHA256SUMS.txt:1-38; memo:48-59).
ADDITIVITY PASS: no field, status value, or reader behavior was renamed/removed; g361_strips is new and its sole importing test passed (g361_strips.py:79-101; test_g361_strips.py:7).
LOC/MEMO PASS: touched Python files are 105 and 45 lines; memo is 59 lines with NOT VERIFIED at line 49 (g361_strips.py:1-105; test_g361_strips.py:1-45; memo:49).
B1 PASS: all 884 ids and all 31 sealed sample members remain in the denominators; eight blocked and two unproved sections are named (memo:12-36).
B2 PASS: schemas are additive and the only reader of the new strip module is checked (ledger_links.csv:1; test_g361_strips.py:7).
B3 PASS: unavailable source evidence remains UNKNOWN with a reason; no quarantine gate was added (g361_source_identity.py:198-205).
B4 PASS: no claim or reclaim lifecycle is present in the touched code (g361_strips.py:79-101).
B5 PASS: measurement ran in the named pod worktree and reports no deployed-tree mutation (memo:6,58-59).
B6 PASS: no module was moved or retired; both G361 importing test files pass (test_g361_source_identity.py:9; test_g361_strips.py:7).
B7 PASS: sections are the exact full stepped sample, and verifier render inspection was evenly spaced (g361_source_identity.py:220-234; sections.csv:1-32).
B8 PASS: this provenance map uses no fitted residual as independent evidence (g361_prereg_2026-09-09.md:95-101).
B9 PASS: construct denominator is 884 distinct snapshot ids; sampled units and landmark keys are nondegenerate and unique (summary.json:234-235; alignment.csv:1-694).
B10 FAIL: the effective alignment gate accepts nine ticks although the fixed minimum is 30 (g361_source_identity.py:129-133; G361_spec.md:31-34).
Q1 PASS: recorded and recomputed LF seal are 02c8e3534388bba404a0c83616aa8573af50e9e8d48de33e72ec14b3f0aed825; seal commit 18:25Z predates snapshot 18:35Z (g361_prereg_2026-09-09.md:127-129; memo:5-7).
Q2 PASS (not applicable): no charged trial or launch K exists (memo:1-59).
Q3 FAIL: the sealed >=30-landmark threshold is not applied by aligned_games, producing an invalid ALIGNED artifact row (g361_prereg_2026-09-09.md:58-66; ledger_links.csv:544).
Q4 PASS (not applicable): no OOS score or meta-learner is present (memo:58-59).
Q5 PASS (not applicable): no comparative advancement claim is made (memo:58-59).
Q6 PASS: independent scan of 17 G361 text artifacts and the added system-results row found 0 prohibited-word and 0 prohibited-number tokens (memo:48-59).
Q7 PASS: sampled n=31 and the 884-id construct is exhaustive (G361_spec.md:43; sections.csv:1-32).
Q8 PASS: same-day row; verifier first recounted 892 snapshot rows/884 ids and the premise artifact's 0/809 complete bindings (ledger_snapshot.jsonl:1-892; census.csv:19).
TEST PASS: `python -m pytest tests/platformkit/test_g361_source_identity.py -q -p no:cacheprovider` -> 8 passed in 0.82s.
TEST PASS: `python -m pytest tests/platformkit/test_g361_strips.py -q -p no:cacheprovider` -> 2 passed in 0.94s.
CORRECTION DIFF: aligned_games must count distinct landmarks and return a game only when all pass and count >= LANDMARKS; add a sub-30 regression test (g361_source_identity.py:129-133; test_g361_source_identity.py:69-86).
CORRECTION DIFF: cmd_summary must exclude UNKNOWN parse keys from collision groups and report their count separately; regenerate ledger_links.csv and summary.json (g361_source_identity.py:255-271; summary.json:30).
CORRECTION DIFF: regenerate hashes and update memo/results text to corrected classes 19/21/844, alignment rows 693, parsed collisions 0, and an explicit mixed-byte hash convention (memo:13-21; SHA256SUMS.txt:1-38).
2026-09-09 | tracking | G361 | 884/884 mappings present; corrected classes EXACT 19, ALIGNED 21, UNKNOWN 844; 0 collisions/690 parsed pairs; 21/31 sections pass <= 1 frame, below the 30-section bar | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: raw pod table headers are not archived and local data lacks them, so the 0/809 premise binding count cannot be replayed independently beyond census.csv.
NEW GAP: encode returns its last JPEG even if still oversized; actual strips pass, but the cap is not guaranteed for future inputs (g361_strips.py:66-75).
NEW GAP: direct targeted Git and the sanctioned lane_commit helper both failed before staging on the external linked-worktree index.lock; an external path-specific committer is required.
