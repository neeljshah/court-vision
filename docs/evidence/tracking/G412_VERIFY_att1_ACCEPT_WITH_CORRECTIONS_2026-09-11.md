VERDICT: ACCEPT WITH CORRECTIONS
Candidate: 2fecca4e1a22f2935379775d44a97a52f4f77031; acceptance source: docs/evidence/tracking/specs/G412_spec.md:21.
PASS PREMEASURE: 60 unique ticks/53 sections, 206 rows, 5 silent, 592 comparator boxes; 25/25 input hashes and 60/60 source receipts rehashed (summary.json:70-89).
PASS Coordinate accounting: 60/60 cards, 55 measured and 5 silent; 206 boxes; 8 evenly spaced cards inspected (summary.json:121-126,134-149).
PASS Writer/geometry compatibility: 32/32 exhaustive controls, 206/206 legacy parity, 178 reader lines/53 files independently recensused (summary.json:118-136).
PASS Comparator re-derivation: claimed -58.203 to +1.797; reproduced -58.203 to +1.797, exact +60 on 51 pairs/28 frames, 18 clipped (summary.json:138-146).
PASS B1: all planned units and silent outcomes retained; no post-exclusion metric (specs/G412_spec.md:21-23).
PASS B2: proposal is additive, with 21 additions/0 removals; no legacy field, status, or reader behavior changed (PROPOSED_g412_box_frame_contract.diff:1).
PASS B3: absent boxes emit EMPTY and unbound routes emit UNKNOWN, not an adverse gate (diff_fixture.json:3-30).
PASS B4: no claim/retry mechanism exists in this proposed-only receipt (summary.json:23-31).
PASS B5: local CPU-only evidence; no pod stage or deployment (g412_box_frame_contract_2026-09-12.md:9).
PASS B6: no module move or retirement; import census found one test file and no orphan (test_g412_box_frame_contract.py:8-15).
PASS B7: all 60 exact-even cards retained; visual sample spans ordinals 00/09/19/29 in both kinds (eye_index.csv:1).
PASS B8: constants come from archived source and fitted_constants is empty (transforms.json:1-17; summary.json:143).
PASS B9: denominators remain 60 unique ticks, 206 rows, and 28 unique comparator frames (summary.json:70,89,144-146).
PASS B10: bars remain 60/55, 32/32, at least 30 native frames, and exact +60 (specs/G412_spec.md:21-23).
PASS Q1: prereg seal independently recomputed as f48ae105abc5d869864bc19d5e580870bcf8b98eafd33baf99a4e400882be916; commit e44f8d096 predates candidate (prereg.md:31).
PASS Q2: no charged trial or launch-K claim exists (summary.json:32-33).
PASS Q3: the sealed 60/15 constants and acceptance bars are unchanged (prereg.md:13-20; transforms.json:1-17).
PASS Q4: no OOS or meta-learning claim exists; this is construct and descriptive arithmetic (summary.json:145).
PASS Q5: no AHEAD claim exists (g412_box_frame_contract_2026-09-12.md:1).
PASS Q6: independent scan of 38 delivered/touched text paths found no non-exempt hit; one typed numeric CSV value is exempt (q6_scan.json:1-367).
PASS Q7: the declared 2x4x2x2 CONSTRUCT matrix has 32 unique exhaustive cases (construct_cases.csv:1-33).
PASS Q8: premise independently remeasured TRUE before verdict (summary.json:68-102).
PASS Evidence: all named paths exist; 97/97 SHA256SUMS entries rehash, maximum entry 485644 bytes (SHA256SUMS:1-98).
PASS LOC: touched Python files are 175,131,152,119,165,210,264,181 lines; maximum 264.
PASS NOT VERIFIED: memo explicitly lists live integration, physical registration, freshness, geometry quality, and training suitability (g412_box_frame_contract_2026-09-12.md:33-39).
TEST PASS: `python -m pytest tests/platformkit/test_g412_box_frame_contract.py -q` -- 11 passed in 0.82s.
TEST IMPORT CENSUS: only tests/platformkit/test_g412_box_frame_contract.py imports a touched module; no additional command required.
CORRECTION (minimal diff): g412_box_frame_contract_2026-09-12.md:19 replace `adds 20 lines` with `adds 21 lines`; measured proposal is 21 additions and 0 removals.
2026-09-11 | tracking | G412 | 60/60 cards; 32/32 controls; 206/206 legacy parity; dy -58.203 to +1.797 on 51 pairs/28 frames; proposed only | DONE PROPOSED ONLY; ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: q6_scan.json:1-367 omits SHA256SUMS from its path manifest; the independent verification scan covered it.
NEW GAP: diff_fixture.json:1-32 checks three synthetic route states but does not replay the proposed persistent box_route state across all 206 archived rows; add that linkage before live integration.
NEW GAP: linked-worktree Git metadata is outside the writable root; targeted git add and the sanctioned lane_commit.py both failed at index.lock, so an external path-specific committer must commit this sole memo.
