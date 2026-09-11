VERDICT: ACCEPT WITH CORRECTIONS
Candidate: 557b0b305a32c466a176208c73624d19585d7bd7; full 31-path diff reviewed.
PREMISE PASS: claimed/reproduced 121/121 unique terminal ORIGINAL sections from 2,375 ledger rows: 111 tracked + 10 thin; requested 270=109 and 232=12; population.json:4-6.
REPRO PASS: claimed/reproduced retained/digest/probe 88/88/88, 4,361,945,178 bytes, 0 bound; classes 720p30=26, 1080p60=24, 1080p30=22, 720p25=11, 720p60=5, UNKNOWN=33; memo:9-15.
REPRO PASS: claimed/reproduced known/UNKNOWN schedules 111/10; decoded/read/evaluated/suspended 511485/100491/97065/3426; summary.json:62-65.
REPRO PASS: claimed/reproduced held 296072/353842=0.836735 and 3317/3832=0.865605; raw/known cap loss 29/88 and 22/78; memo:19-25.
ARTIFACT PASS: 22/22 required paths, 121 traces, 118/118 exact-even unique cards, 88/88 receiver paths and sizes, 296/296 manifest digests, pre_fix1c 16/16 exact parent bytes; SHA256SUMS:1.
ACCEPTANCE-1 PASS: every actual rendition is UNRESOLVED, every measured class is under 30, empty/missing strata are explicit, and the result remains PARTIAL; provenance_counts.csv:2.
ACCEPTANCE-2 PASS: 111 known schedules reconcile, 10 reason-aliased rows remain UNKNOWN, zero derived out-of-window rows, and aggregates exclude UNKNOWN; g407_report.py:73-91,237-277.
ACCEPTANCE-3 PASS: 12 assets predate observation, zero scratch launches remain NOT VALIDATED, and saved-input regeneration is 293/293 twice; route_hashes.json:2-5, repeats.json:2371.
B1 PASS: all 121 rows remain named and the 10 excluded schedule rows are explicit; memo:19-21.
B2 PASS: no field or row removed; schedule_reason and class status are additive aliases, and the sole test reader passes; g407_report.py:129-167.
B3 PASS: absent schedule and rendition evidence remains UNKNOWN/PARTIAL; memo:1,48-54.
B4 PASS: zero-launch state is terminal and not claimable; launch_receipts.csv:2.
B5 PASS: no deployment or scratch launch is claimed by this candidate; launch_receipts.csv:2.
B6 PASS: no module moved or retired; g407_repeats.py:31.
B7 PASS: 118 cards independently reproduce exact-even selection over every class decision set; g407_cards.py:29-33.
B8 PASS: no fitted comparison is used; memo:53.
B9 PASS: held denominators are shared consecutive evaluated-tick pairs and 121 section identities are unique; memo:9,21.
B10 PASS: quota 30 and total cap 180 match the sealed bars and are unchanged by the candidate; g407_tables.py:18, g407_report.py:218.
Q1 PASS: prereg seal a411f5905fbce243d2198889752e40c5025a9b1abff74105976bbdd82606978c matches and commit 050d633bc predates measurement; prereg.md:23.
Q2 PASS: no charged trial or scratch launch exists; launch_receipts.csv:2.
Q3 PASS: quota 30, total cap 180, and centered two-second interval remain unchanged; prereg.md:12-18.
Q4 PASS: no OOS comparison or meta-learner is claimed; memo:48-55.
Q5 PASS: no AHEAD claim is made; memo:1.
Q6 PASS: independent scan of all 4,702 candidate-added lines returns zero pattern indices; q6_scan.json:9-17.
Q7 PASS: under-30 strata remain descriptive PARTIAL and the 118-card construct is exhaustive/exact-even; eye_index.csv:1.
Q8 PASS: whole-set premise independently remeasured before adjudication; population.json:4-6.
TEST PASS: `python -m pytest tests/platformkit/test_g407_rendition_boundary.py -q -p no:cacheprovider --basetemp=%TEMP%\g407_verify_codex_sol_557b0b305` -> 22 passed in 0.93s; only existing test importer; test_g407_rendition_boundary.py:12-23.
LOC PASS: g407_cards.py 117, g407_report.py 297, g407_tables.py 176, test_g407_rendition_boundary.py 291; g407_report.py:1.
MEMO PASS: explicit NOT VERIFIED list is present; memo:48-55.
CORRECTION: memo:29 minimal diff: `2,002 record fields and 177 delivered file records` -> `2,251 record fields and 203 delivered file records`; q6_scan.json:10,16.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G407 | 121 unique sections; 88 retained; 0 bound; 111 known plus 10 UNKNOWN schedules; held 296072/353842 and 3317/3832; saved-input regeneration 293/293; scan counts corrected to 2251/203 | PARTIAL (verified: codex-sol, contract A/B/Q)
NEW GAP: linked-worktree Git metadata is outside the writable sandbox; targeted git add and the safely narrowed lane_commit helper both failed at index.lock, so no verifier commit object could be created here.
