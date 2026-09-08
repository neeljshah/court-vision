VERDICT: REJECT
Candidate: `a5056025e`; verification date 2026-09-07; scope is the G322 acceptance rule plus B1-B10 and Q1-Q8.
ACCEPTANCE PASS: exact 94-line ledger prefix has the sealed SHA-256, 71 tracked games, and no census omissions/extras; `g322_oversized_boxes_census_2026-09-07.csv:1-72`.
PREMISE PASS: claimed 0.1993/0.2293/0.0000; raw-table reproduction 1112/5580=0.1992831541, 1086/4736=0.2293074324, 0/1653=0, with frame_h 1080/720/720 and hashes matching census lines 63/71/64.
HEADLINE PASS: claimed 44/71 and 47206/250369=0.1885; reproduced 44/71 and 0.1885457065; secondary cuts reproduced 108161/250369=0.4320063586 and 187728/250369=0.7498052874; memo:2,13.
RESOLUTION PASS: reproduced 1920 4127/34428=1.198733589e-1, 1280 4659/36112=0.1290152858, 640 38420/179829=0.2136474095; `g322_oversized_boxes_by_resolution_2026-09-07.csv:2-4`.
PANELS PASS: 20 unique keys, five per sealed game, exact odd-decile ranks, counts 8/5/3/2/2 and sealed set 9/20; panels CSV:2-21, labels CSV:2-21, prereg:42-87.
TRACE PASS WITH CORRECTION: source confirms TOPCUT, detector call, no size gate, PAD, constant Kalman height and footpoint fallback; trace:5-38,44-56, but memo:21 overstates the mixed determination.
NOT VERIFIED PASS: explicit list exists at `g322_oversized_boxes_2026-09-07.md:40-42`.
B1 PASS: all 250369 rows are usable and no game is excluded; census:1-72; script:59-104.
B2 PASS: commit is additive: twelve new paths plus one ledger append, with no renamed/removed field, status or reader behavior; `RESULTS_LEDGER.md:485`.
B3 PASS: no quarantine or missing-evidence gate is introduced; scripts:183-254.
B4 PASS: no claim lifecycle is introduced; scripts:1-258.
B5 PASS: no deployed-tree change; memo:59 and candidate diff.
B6 PASS: no module is moved or retired; both modules are new; scripts:1-258 and renderer:1-144.
B7 PASS: per-resolution medians plus one maximum and odd deciles are sealed; prereg:42-60; panels CSV:2-21.
B8 PASS: descriptive row arithmetic has no fitted residual; script:59-108.
B9 PASS: denominators are each table's own varying row count; census:2-72.
B10 PASS: 0.50/0.33/0.25, 0.10 and 15/20 match spec and seal; script:20-25; prereg:32-40,88-91.
Q1 PASS: seal recomputed as `ca5227924c06e83b56de72782fe210a16ebad8169613215794aa3f26da9fb010`; prereg:1-5,174-176; separate commit precedes measurement commit by 18 minutes.
Q2 PASS: not a charged trial; this is an enumerated census; memo:10-18.
Q3 PASS: fixed bars match the spec byte-for-byte; prereg:32-40,88-91.
Q4 PASS: no OOS or meta-learner claim; memo:40-42.
Q5 PASS: no AHEAD claim; memo:2,40-42.
Q6 FAIL: five prohibited-token occurrences remain in the sealed prereg at lines 24 and 97, and a prohibited historical digit sequence remains at memo:13 and by-resolution CSV:3.
Q7 PASS: 71-game construct is exhaustive and the 20 panels are an eye check with counts only; memo:10-18,25-38.
Q8 PASS: premise independently remeasured first from the three pod tables; census:63,71,64.
TEST PASS: `python -m pytest tests/platformkit/test_g322_oversized_boxes.py -q` -> 4 passed in 1.74s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 0.66s.
IMPORT/LOC PASS: only `tests/platformkit/test_g322_oversized_boxes.py` imports a touched module; renderer has none; touched Python LOC = 258/144/73.
CORRECTION: new sealed prereg: line 24 final noun -> `border`; line 97 four-token enumeration -> `forbidden market-language tokens`; then rerun because Q1 forbids post-measurement resealing.
CORRECTION: memo:13 and by-resolution CSV:3 encode the 1920 result as `4127/34428 (~1.1987e-1)`; memo:21 -> `primarily (a); (b) contributes via PAD; (c) is confined to the off-frame tail`.
RESULTS_LEDGER_SYSTEM: 2026-09-07 | tracking | G322 | premise reproduced; 44/71 games meet the fixed bar, pooled 47206/250369, but Q6 artifact-language gate failed | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: candidate evidence memo places its verdict on line 2, not line 1 (`g322_oversized_boxes_2026-09-07.md:1-2`); outside the acceptance rule.
NEW GAP: contract A1 cannot be executed before landing because master `9b06d0f28` does not contain the candidate test, while this task permits committing only this verifier memo.
