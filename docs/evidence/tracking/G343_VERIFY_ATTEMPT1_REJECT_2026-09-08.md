VERDICT: REJECT
CANDIDATE: b10077d60df801abde780a2674030e76d4398aab; full stat and diff reviewed.
SCOPE: G343 ACCEPTANCE RULE plus B1-B10 and Q1-Q8 only.
PREMISE PASS: baseline 6277207ba has no injected-corruption power harness; current mirror independently has 356 paired tables and 0 calibration sidecars (spec:58; memo:10-12,25).
ACCEPTANCE FAIL: A2 could not run on 7/24 windows, while the required verdict is PARTIAL whenever an arm or gate cannot run; candidate says MEASURED (spec:66-67; memo:1,20,34).
ARM ROUTE FAIL: A3 shifts the returned ball table in all 24 windows, but run discards that return and sends only unchanged tracking rows to evaluate (g343_attack_test.py:173-175; memo:21,43).
REPRODUCTION: 2,592/2,592 unique cells = 24 windows x 6 arms x 18 gates; coordinate_contract is 24/24 for A0/A1/A3/A4/A5 and 17/17 applicable A2 with 7 NOT_APPLICABLE; A0 acceptance is 0.000000; all 13 downstream gates have applicable_n=0 (memo:14-23; power.csv:38).
MANIFEST PASS: sealed rule, 48 source sizes/digests, window counts, and max-plus-one dimensions reproduce; largest source is 22,448,525 bytes and sequential total read is 288,782,098 bytes (windows.csv:2-25).
ARTIFACT PASS: power/windows hashes reproduce as e30b995b1169296baefc1577b467c7cd65dca8875f06a29a116afb499b984dc6 and 419ae3d5092831420d7591c3c663800b392e08097442d430ca357fa293e43910 (memo:49).
A0 PASS: construct test proves frame identity; runtime A0 is 0/24 accepted solely because coordinate_contract rejects it (test_g343_attack_test.py:16-19; memo:18,38).
EVIDENCE PASS: all named deliverables exist; memo is 49 lines, has eye check NONE and NOT VERIFIED at lines 40-45 (memo:7,40-49).
TEST PASS: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_g343_attack_test.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 1 passed in 2.70s.
TEST PASS: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 1 passed in 1.07s.
IMPORTER PASS: repository search finds only test_g343_attack_test.py importing the touched module (test_g343_attack_test.py:6).
LOC PASS: g343_attack_test.py 215 LOC and test_g343_attack_test.py 51 LOC, both <= 300.
ADDITIVITY FAIL: b10077d60 replaces the prior PREPARED ledger row instead of appending the new result, removing status history (b10077d60^:RESULTS_LEDGER.md:591; RESULTS_LEDGER.md:591).
B1 PASS: all exclusions are named; A2 uses 17 applicable windows and identifies all 7 construction exclusions (memo:20,34; power.csv:38).
B2 FAIL: the PREPARED status row was removed without an additive successor row (b10077d60^:RESULTS_LEDGER.md:591; RESULTS_LEDGER.md:591).
B3 PASS: this measurement changes no production gate or item flow (memo:7; candidate diff).
B4 PASS: no claim or retry lifecycle is added or changed (g343_attack_test.py:145-203).
B5 PASS: local-only measurement; no deployed tree was written (memo:3,6-7).
B6 PASS: no module, import, or command target was moved or retired (candidate stat; g343_attack_test.py:1).
B7 PASS: every 15th sorted eligible clip spans indices 0 through 345; this is not a head slice (g343_prereg_2026-09-08.md:15-23; windows.csv:2-25).
B8 PASS: no fit or fitted residual is used (g343_prereg_2026-09-08.md:61-65).
B9 PASS: per-arm denominators are 24 unique windows, or the named 17-window A2 applicable set (memo:18-23; power.csv:38).
B10 PASS: candidate changes no harness threshold or gate value (memo:7,31; candidate stat).
Q1 PASS: seal 8893df131bd1399954484d436081c695b429b319175e601588299e362d525527 reproduces and commit 2e2d66853 predates b10077d60 (g343_prereg_2026-09-08.md:72).
Q2 PASS (N/A): this descriptive measurement charges no trial and has no launch K (g343_prereg_2026-09-08.md:61-65).
Q3 PASS: the sealed 24-window rule and all gate bars remain byte-identical (spec:56-65; memo:31).
Q4 PASS (N/A): no OOS model or meta-learner is scored (g343_prereg_2026-09-08.md:61-65).
Q5 PASS (N/A): no comparative AHEAD result is claimed (memo:1,14-23).
Q6 PASS: restricted-language scan of candidate additions and this memo is clean (memo:1-49).
Q7 FAIL: each sampled per-arm rejection share has n=24, below the n>=30 rail; this is expressly a screening sample, not an exhaustive construct (VERIFIER_CONTRACT.md:45; spec:62; g343_prereg_2026-09-08.md:68).
Q8 PASS: the baseline premise was independently remeasured true before scoring review (spec:58; memo:10-12).
CORRECTION DIFF: memo:1 `MEASURED ... all 6 arms ... all 24` -> `PARTIAL; five arms are 24/24, A2 is 17/17 applicable with 7 construction exclusions`; memo:25 `every arm x window` -> `every constructed arm x window`.
CORRECTION DIFF: restore b10077d60^ RESULTS_LEDGER.md:591, then append the measured row with status PARTIAL; do not replace the preparation history.
RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G343 | premise holds; reproduced 2,592 unique cells over 24 windows, A0 acceptance 0.000000, coordinate-contract rejection 24/24 for A0/A1/A3/A4/A5 and 17/17 applicable A2 with 7 construction exclusions; sampled denominator is below Q7 and ledger history was replaced | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: the sealed ASCII every-15th rule selects 0/2 WNBA tables despite naming cross-league span; stratify the next preregistration (g343_prereg_2026-09-08.md:15-23; windows.csv:2-25).
NEW GAP: run catches ValueError from both arm construction and evaluate, so a future harness ValueError would be mislabeled as arm construction failure (g343_attack_test.py:172-178).
NEW GAP: linked-worktree Git metadata is outside the writable root; the exact commit command and sanctioned lane_commit.py both failed on index.lock, so an external path-specific commit is required.
