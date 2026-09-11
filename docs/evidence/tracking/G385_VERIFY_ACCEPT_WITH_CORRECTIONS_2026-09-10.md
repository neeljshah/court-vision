VERDICT: ACCEPT WITH CORRECTIONS
Candidate 7396aab67; verification 2026-09-10; contract A/B/Q and G385 acceptance rule only.
ACCEPTANCE-premise PASS - independently reproduced 281 rated, 127 non-play, 6 OTHER_SPORT from one video, and 837 excluded rows (g385_nonplay_shadow_mask_2026-09-10.md:5).
ACCEPTANCE-sample PASS - 174 eligible disjoint sections/34 videos reproduce the exact even draw: 30 sections, 29 videos, 360 unique interior ticks (memo:7; frames.csv:1).
ACCEPTANCE-score PASS - reproduced false masks 5/234=0.0213675214, independent Wilson95 upper 0.0490355163; claim 0.021368/0.049036 (memo:16; summary.json:11).
ACCEPTANCE-capture PASS - reproduced 94/125=0.7520000000, independent Wilson95 lower 0.6695405133; claim 0.752000/0.669541 (memo:17; summary.json:5).
ACCEPTANCE-denominators PASS - 360/360 unique attempts, 234 PLAY, 125 definite non-play, 1 UNKNOWN, 0 absent masks; regenerated paired/confusion/purity receipts match (memo:12; summary.json:23,40).
ACCEPTANCE-eye PASS - exact 30 evenly spaced keys plus all 5 harmful PLAY masks; 35 renders visually checked and byte-match their sheets (memo:22).
ACCEPTANCE-runtime PASS - 30 sections, total 25678.0 ms, 71.3278 ms/frame; median wording needs correction below (memo:24; runtime.csv:1).
ACCEPTANCE-scope PASS - unused research mask, zero callers, no general sport-purity or section-level claim (memo:1,21,23).
MEMO PASS - substantive NOT VERIFIED list exists (g385_nonplay_shadow_mask_2026-09-10.md:28-34).
TEST PASS - `python -m pytest tests/platformkit/test_g385_nonplay_shadow_mask.py -q` -> 4 passed in 0.71s.
TEST PASS - `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 0.73s.
IMPORTER CENSUS PASS - the spec test is the only existing test importing any G385 module; candidate 7396aab67 touches no .py.
LOC PASS - candidate touches no .py; G385 row modules are 32-209 LOC, all <=300.
B1 PASS - no filtering/top-up: reference, prediction and paired joins each retain all 360 planned keys (memo:7,12).
B2 PASS - additive paired schema keeps original gate decision beside shadow fields; no field/status/reader behavior removed (paired_masks.csv:1; memo:25).
B3 PASS - absent/invalid evidence passes through as UNKNOWN; zero absent masks; dedicated test passed (summary.json:40).
B4 PASS - unused mask has zero claim or retry path and zero callers (memo:1,34).
B5 PASS - candidate is evidence-only; no deployed-tree path changed (memo:25).
B6 PASS - no module moved or retired and no orphan reference introduced (memo:25).
B7 PASS - exact midpoint-stratified section draw and evenly spaced render keys reproduce (memo:7,22).
B8 PASS - frozen G375 fit and validation have zero video-ID overlap (memo:9; dev_exclusions.csv:1).
B9 PASS - 360 unique tick keys across 30 sections/29 videos; denominators are non-degenerate (memo:7; summary.json:23).
B10 PASS - numeric bars and threshold 0.95 match the sealed spec; no shared threshold file changed (G385_spec.md:19; model_identity.json:13).
Q1 PASS - seal 1dd44f12075456bd18b5797815d23ba8b4bf3e13eb24417d08d813c0f085d589 independently reproduces; commit 951f3b4c3 contains only the prereg and predates scoring (g385_prereg_2026-09-10.md:68).
Q2 PASS (not applicable) - no charged trial or K (memo:33).
Q3 PASS - fixed class, Wilson, 360-attempt and absent-evidence bars are unchanged (G385_spec.md:19; memo:14-19).
Q4 PASS (not applicable) - static frame-mask audit, not an OOS forecast or meta-learner comparison (memo:33).
Q5 PASS (not applicable) - no AHEAD claim; second-corpus uncertainty is explicit (memo:30).
Q6 PASS - independent scan of evidence, memo, modules and the G385 ledger row found 0 findings (memo:26).
Q7 PASS - scored n=360; class denominators are 234 and 125, both >=30 (memo:15-17).
Q8 PASS - premise independently remeasured before adjudication and remains true (memo:5).
CORRECTION (minimal, memo:5): replace `837 rows: 131 G375 labelled-video ids plus 10 G364 development ids` with `837 rows; 131 unique excluded video ids; all 10 G364 ids overlap the 131 G375 ids`.
CORRECTION (minimal, memo:24): replace `median 853.8 ms, p90 884.2 ms` with `median 853.25 ms, nearest-rank p90 884.2 ms`.
2026-09-10 | tracking | G385 | shadow-mask false masks 5/234 = 0.021368 (Wilson95 upper 0.049036); definite non-play capture 94/125 = 0.752000 (Wilson95 lower 0.669541); 360 unique ticks, 30 sections, 29 videos, 0 absent masks; unused, zero callers | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: The memo names deleted pod-only source paths (memo:8,48-49), so source containers and frozen backbone bytes cannot be reopened from this worktree; local sheets and all recorded sheet hashes do reproduce.
