VERDICT: REJECT
Candidate: 6fc65159421317e7cf7eeacb5e648e4502dd2b8c.
ACCEPTANCE PASS: G363_spec.md:41-51; n=881 unique frames, 63 sections, 60 games, 3 competitions; held-out composition 285 VISIBLE / 243 ABSENT.
REPRODUCED vs claimed PASS: g363_ball_coverage_2026-09-09.md:1,28-34; C0 0/549=0.000000, A7 2/549=0.003642987, Wilson lower 0.003052375, FP/N_absent 178/243=0.732510288.
PREMISE CONTEXT PASS: survival_fix1b.csv:1 gives 505/1860=271.505 per mille and 358/1860=192.473 per mille, matching g363_ball_coverage_2026-09-09.md:13 rounding.
EVIDENCE PASS: frames.csv:1 and ratings.csv:1 have 881 unique complete references; identity.csv:1 has 2643/2643 REPRODUCED.
EYE CHECK PASS: g363_eyecheck.py:31 and eye_check_manifest.csv:1; 30 unique native 1920x1080 renders exactly match the even selector, hashes valid, three spread renders inspected.
MEMO PASS: g363_ball_coverage_2026-09-09.md:55 has a NOT VERIFIED list; memo is 60 lines.
TEST PASS: `python -m pytest tests/platformkit/test_g363_ball_coverage.py -q -p no:cacheprovider` -> 9 passed in 1.01s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed in 1.02s.
IMPORT TEST PASS: no existing test imports g363_centre_diag, g363_eyecheck, or g363_rebuild_cache; no additional file applies.
LOC PASS: g363_centre_diag.py:1=91, g363_eyecheck.py:1=123, g363_rebuild_cache.py:1=128; each <=300.
B1 PASS: g363_score.py:121 uses all labelled sealed frames; zero unadjudicated and no outcome-based exclusion.
B2 PASS: g363_rebuild_cache.py:29 adds fields/statuses only; candidate has no rename/removal and no existing reader change.
B3 PASS: g363_rebuild_cache.py:104 names missing identity; measured identity has no missing row.
B4 PASS: g363_ball_coverage_2026-09-09.md:42 adds no claim/retry path.
B5 PASS: g363_ball_coverage_2026-09-09.md:4,42 records scratch compute and no deployed-tree write.
B6 PASS: g363_centre_diag.py:1, g363_eyecheck.py:1, and g363_rebuild_cache.py:1 are additions; no move, removal, or orphaned reference found.
B7 PASS: g363_eyecheck.py:31-38 and eye_check_manifest.csv:2-31 span the held-out ordering, not a head slice.
B8 PASS: frames.csv:1 is game-disjoint; selection uses development and scoring uses held-out.
B9 PASS: g363_ball_coverage_2026-09-09.md:14 reports 3x zero undefined and LIMIT.
B10 PASS: G363_spec.md:45 and g363_score.py:24-29 agree on all bars; protected paths are untouched.
Q1 FAIL: g363_prereg_amendment_2026-09-09.md:13-21 changes the scored reference but line 32 has no embedded SHA-256 seal; g363_ball_coverage_2026-09-09.md:3 assigns amendment commit 83990386 to the base prereg, actually sealed at 6cc172fc.
Q2 FAIL: g363_ball_coverage_2026-09-09.md:16-26 scores A1-A7 but records neither a pre-metric charged-trial row nor launch K; the only G363 ledger row is post-result.
Q3 PASS: G363_spec.md:45 and summary.json:551-560 preserve 3.0, 0.90, 0.01, 150/150, and 0.50.
Q4 FAIL: g363_score.py:121-177 scores a single held-out split, with no walk_forward/cpcv_evaluate route, purge, or symmetric embargo.
Q5 PASS: summary.json:565 is LIMIT, not AHEAD; the two-corpus condition is not invoked.
Q6 FAIL: g363_ball_coverage_2026-09-09.md:51 omits predictions.csv from its scan; predictions.csv:18,21 exemplify 69 non-exempt exact-token matches in score and box-size fields.
Q7 PASS: frames.csv:1 has 881 scored unique frames, exceeding the sampled-score rail.
Q8 PASS: g363_ball_coverage_2026-09-09.md:11-14 remeasures C0 on the sealed labelled reference and closes the factor-three premise at LIMIT.
CORRECTION DIFF 1: g363_ball_coverage_2026-09-09.md:3 `- base prereg at 83990386` -> `+ base prereg at 6cc172fc; amendment 83990386 has no embedded seal`.
CORRECTION DIFF 2: g363_ball_coverage_2026-09-09.md:51 scan set `- excludes predictions.csv` -> `+ includes predictions.csv`; use equivalent clean numeric serialization and refresh artifact hashes.
CORRECTION: Q1/Q2/Q4 require a fresh, correctly sealed and charged evaluation; no retrospective memo-only patch cures them.
2026-09-10 | tracking | G363 | C0 0/549; A7 2/549, Wilson lower 0.003052, FP/N_absent 0.732510; contract Q1/Q2/Q4/Q6 failed | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: g363_ball_coverage_2026-09-09.md:44-46 gives LF-normalized blob hashes without saying so; raw CRLF checkout hashes differ.
NEW GAP: g363_ball_coverage_2026-09-09.md:8,41 names decode and GPU totals without an archived run receipt that establishes those totals or their ordering.
