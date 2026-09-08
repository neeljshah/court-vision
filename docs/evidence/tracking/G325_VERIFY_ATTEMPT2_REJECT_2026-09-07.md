VERDICT: REJECT
Candidate: `967e181d2c4a0763b711b56b082416bf932c39e2`; verification date 2026-09-07.
ACCEPTANCE PASS: prereg manifest and census contain the same 122 unique games, 122 unique table hashes, zero missing/extra/mismatched entries, zero unusable rows, and all required diagnostics (`g325_offframe_boxes_attempt2_2026-09-07.md:9-21`; census:2-123).
PREMISE PASS: reproduced `wnba_06` 150/3606, `wnba_04` 160/6189, and `0022500575_s7200` 12/2620 with claimed widths/heights (`g325_offframe_boxes_attempt2_2026-09-07.md:6-7`).
REPRODUCTION PASS: claimed/reproduced 23408/480158 (~4.87506196e-02), 113/122 games at least 1/100, median ~4.21415392e-02, coasting 23408/23408, matched 0/269174 (`g325_offframe_boxes_attempt2_2026-09-07.md:1,18,30,39`).
DIAGNOSTICS PASS: reproduced naive-height 22666/480158, partial 134998/480158, PAD-removed 24952/480158, and all three resolution cells (`g325_offframe_boxes_attempt2_2026-09-07.md:11-21`).
ADDITIVITY PASS: no field/header/status was removed or renamed, the ledger change is one append, and the sole Python change is a test docstring (`g325_offframe_boxes_census_2026-09-07.csv:1`; `RESULTS_LEDGER.md:503`; `test_g325_offframe_boxes.py:1-8`).
LOC PASS: touched `test_g325_offframe_boxes.py` is 117 lines; imported unchanged harness is 243 lines (`test_g325_offframe_boxes.py:117`; `g325_offframe_boxes.py:243`).
NOT VERIFIED PASS: the memo explicitly lists unmeasured visual, downstream, width-source, daemon-config, repeatability, and population limits (`g325_offframe_boxes_attempt2_2026-09-07.md:46-49`).
B1 PASS: every row enters `rows_total`; unusable rows are counted before exclusion, and measured unusable count is zero (`g325_offframe_boxes.py:83-89,117`; census:2-123).
B2 PASS: schema and reader behavior are additive as documented above (`g325_offframe_boxes_census_2026-09-07.csv:1`; `test_g325_offframe_boxes.py:1-16`).
B3 PASS (N/A): no gate or quarantine path was applied (`g325_offframe_boxes_attempt2_2026-09-07.md:43-44`).
B4 PASS (N/A): no claim/retry workflow was added (`g325_offframe_boxes_attempt2_2026-09-07.md:60`).
B5 PASS: candidate diff contains no deployed-tree file and memo records no pod write (`g325_offframe_boxes_attempt2_2026-09-07.md:4,60`).
B6 PASS: no module was moved or retired; the sole importer remains present (`test_g325_offframe_boxes.py:12-16`).
B7 PASS: complete sorted enumeration, not a head slice; no render set exists (`g325_offframe_boxes.py:178-180`; memo:9,46).
B8 PASS (N/A): direct geometric counts use no fitted points (`g325_offframe_boxes.py:93-108`).
B9 PASS: denominators are per-table usable observations and vary from 37 to 6739 over 122 unique games (`g325_offframe_boxes.py:117,130-154`; census:2-123).
B10 PASS: candidate did not change the harness; 1/1000, 1/100, and 9/10 integer tests match the spec (`g325_offframe_boxes.py:158-167`).
Q1 PASS: prereg-only commit `eceac0b89` predates scoring and seal `57d7748a2cf7c84ebf7e3397357d3feb672a7fa0f2ca28cfdf25e6f8ae1518ca` reproduces (`g325_prereg_attempt2_2026-09-07.md:229-230`; memo:3).
Q2 PASS (N/A): this census has no charged trial or launch K (`g325_prereg_attempt2_2026-09-07.md:1-103`).
Q3 PASS: fixed rules match spec and unchanged harness (`g325_prereg_attempt2_2026-09-07.md:47-61`; `g325_offframe_boxes.py:158-167`).
Q4 PASS (N/A): no OOS comparison or meta-learner is present (`g325_offframe_boxes_attempt2_2026-09-07.md:9-42`).
Q5 PASS (N/A): no AHEAD result is asserted (`g325_offframe_boxes_attempt2_2026-09-07.md:1-49`).
Q6 FAIL: independent scan finds one restricted numeric-sequence hit at `g325_offframe_boxes_census_2026-09-07.csv:48` column 14; `g325_offframe_boxes_attempt2_2026-09-07.md:49` admits that CSV scan is not clean. Q6 is automatic reject.
Q7 PASS: the construct is exhaustive: prereg and census sets compare 122/122 with zero set or metadata mismatch (`g325_prereg_attempt2_2026-09-07.md:104-228`; census:2-123).
Q8 PASS: premise recount precedes the pooled census and reproduces (`g325_offframe_boxes_attempt2_2026-09-07.md:6-9`).
TEST [candidate cwd]: `set PYTHONDONTWRITEBYTECODE=1&&python -m pytest tests/platformkit/test_g325_offframe_boxes.py -q --confcutdir=tests/platformkit -p no:cacheprovider` -> 7 passed.
TEST [candidate cwd]: `set PYTHONDONTWRITEBYTECODE=1&&python -m pytest tests/platformkit/test_loc_rail_scope.py -q --confcutdir=tests/platformkit -p no:cacheprovider` -> 1 passed.
TEST [master cwd]: `set PYTHONDONTWRITEBYTECODE=1&&python -m pytest tests/platformkit/test_g325_offframe_boxes.py -q --confcutdir=tests/platformkit -p no:cacheprovider` -> 0 tests; file absent.
TEST [master cwd]: `set PYTHONDONTWRITEBYTECODE=1&&python -m pytest tests/platformkit/test_loc_rail_scope.py -q --confcutdir=tests/platformkit -p no:cacheprovider` -> 1 passed.
IMPORTER PASS: repository search finds only `tests/platformkit/test_g325_offframe_boxes.py`; it is covered above (`test_g325_offframe_boxes.py:12-16`).
CORRECTION DIFF: make `share_wholly` serialization collision-safe at `g325_offframe_boxes.py:124-126`, regenerate census/memo hashes, and append a correction ledger row; do not alter measured numerators, denominators, or bars.
2026-09-07 | tracking | G325 | reproduced 23408/480158 wholly outside; 23408/23408 coasting; 0/269174 matched; Q6 artifact scan has 1 restricted numeric-sequence hit | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: A7 input `track_daemon_ledger_snapshot.jsonl` named at memo:4 is absent from the candidate commit and current worktree, so snapshot eligibility cannot be independently rechecked.
NEW GAP: A7 reference `g323_nonplayer_boxes_attempt2_2026-09-07.md` at memo:46 is absent from the candidate commit and current tree.
NEW GAP: proposal is under `docs/evidence/tracking/` (memo:44), not the spec-named `docs/research/organization-sprint/` path.
NEW GAP: contract A1 cannot complete because master lacks the candidate test file; the exact master command above collected zero tests.
