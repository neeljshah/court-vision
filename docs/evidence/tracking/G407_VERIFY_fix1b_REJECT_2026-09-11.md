VERDICT: REJECT
Candidate: b2be13eacae48178a8af5f337aaae22d11f56e52; full 33-path diff reviewed.
PREMISE PASS: claimed/reproduced 121/121 unique terminal ORIGINAL sections, 111 tracked + 10 thin, requested formats 270=109 and 232=12; population.json:2.
REPRO PASS: claimed/reproduced retained/digest/probe 88/88/88, bytes 4,361,945,178, measured classes 720p30=26, 1080p60=24, 1080p30=22, 720p25=11, 720p60=5, UNKNOWN=33, actual UNRESOLVED=121; memo:9-15.
REPRO PASS: claimed/reproduced decoded/read/evaluated/suspended 511485/100491/97065/3426; held 296072/353842=0.836735 and 3317/3832=0.865605; cap loss 29/88; memo:19-25.
REPRO PASS: 12/12 assets predate daemon/window; regeneration 279/279; scan claimed/reproduced 2002 record fields + 177 file records with zero indices; memo:29.
ARTIFACT PASS: 22/22 required paths, 121 traces, 118 exact-even unique cards, 88/88 receiver paths and sizes, and 281/281 SHA256SUMS entries verified; SHA256SUMS:1.
TEST PASS: `python -m pytest tests/platformkit/test_g407_rendition_boundary.py -q -p no:cacheprovider --basetemp=.pytest_tmp_g407_verify_20260911` -> 22 passed in 0.84s; sole test importer; test_g407_rendition_boundary.py:14-21.
LOC PASS: g407_cards.py 119, g407_report.py 299, g407_tables.py 172, test 269; g407_report.py:1.
MEMO PASS: explicit NOT VERIFIED list present; g407_live_rendition_boundary_census_2026-09-11.md:46-53.
ACCEPTANCE-1 FAIL: UNRESOLVED is PARTIAL in provenance but quota_met=1 in the class summary, contradicting the unbound-PARTIAL bar and memo; class_summaries.csv:8, provenance_counts.csv:14.
ACCEPTANCE-2 FAIL: all 10 schedule-UNKNOWN windows still encode attempted/evaluated/suspended/no-output/held/shared as numeric zero, contrary to UNKNOWN-never-zero; window_counts.csv:41,69,77,81,91,97-98,101,104,110.
ACCEPTANCE-3 PASS: identity predates observation, saved-input regeneration is identical, and zero scratch launches remain NOT VALIDATED; route_hashes.json:2-5, memo:48.
B1 PASS: all 121 sections remain in the population and excluded evidence is named; memo:9,49-50.
B2 FAIL: schedule_status value ball_table_absent was replaced by UNKNOWN without a schedule_reason alias in current tables, changing reader-visible behavior; pre_fix1b/coverage.csv:41, coverage.csv:1,41.
B3 PASS: absent evidence remains UNKNOWN/PARTIAL; memo:1,49-50.
B4 PASS: zero-launch state is terminal and not claimable; launch_receipts.csv:2.
B5 PASS: no candidate producer launch or deployment is claimed; launch_receipts.csv:2.
B6 PASS: no moved/retired module or orphaned reference; g407_report.py:15-23, test_g407_rendition_boundary.py:14-21.
B7 PASS: 118 cards are exact-even over every measured-class decision set, including 30/33 UNKNOWN; eye_index.csv:1.
B8 PASS: no fitted comparison is used; memo:51.
B9 PASS: 121 section identities are unique and held denominators are shared consecutive evaluated-tick pairs; memo:9,21.
B10 PASS: quota 30 and total cap 180 match the sealed bars; g407_tables.py:17, g407_report.py:218.
Q1 PASS: LF prereg seal independently matches a411f5905fbce243d2198889752e40c5025a9b1abff74105976bbdd82606978c and commit 050d633bc predates measurement; prereg.md:23.
Q2 PASS: no charged trial or scratch launch exists; launch_receipts.csv:2.
Q3 PASS: sealed quota 30, total cap 180, and centered two-second interval are unchanged; prereg.md:12-14, g407_report.py:218.
Q4 PASS: no OOS comparison or meta-learner is claimed; memo:48-53.
Q5 PASS: no AHEAD claim is made; memo:1.
Q6 PASS: independent field-aware scan of 196 candidate records returns zero pattern indices; q6_scan.json:1.
Q7 PASS: under-30 classes remain descriptive PARTIAL and the card construct is exhaustive/exact-even; memo:15, eye_index.csv:1.
Q8 PASS: whole-set premise was independently re-measured before adjudication; population.json:2.
CORRECTION: g407_tables.py:147 must exclude UNRESOLVED/UNKNOWN when setting class_summaries quota_met, matching stratum_counts at lines 105-112.
CORRECTION: g407_report.py:80-167 must retain schedule_reason as an additive alias, emit UNKNOWN for schedule-dependent counts when schedule_status is UNKNOWN, exclude those values from aggregates, then regenerate derived artifacts, scan, repeats, memo, and SHA256SUMS.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G407 | 121 unique sections; 88 retained; all delivered formats UNRESOLVED; 111 known schedules reconcile, 10 schedule-absent rows retain numeric zero fields; residual quota flag inconsistent | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: g407_cards.py:83 excludes the archived pre-fix text artifacts from its own scan; the independent expanded scan was clean, so this does not reject G407.
NEW GAP: test_g407_rendition_boundary.py:177-187 checks draw residual status and only schedule_status, but not class_summaries residual quota, schedule-dependent UNKNOWN counts, or the reason alias.
NEW GAP: targeted git add was denied at the linked-worktree index.lock; lane_commit.py would also stage unrelated modified planning files, so no compliant commit was created.
