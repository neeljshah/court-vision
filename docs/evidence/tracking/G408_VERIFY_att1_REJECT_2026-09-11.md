VERDICT: REJECT
Candidate: e1b27ee36a0893a6aa8cccd167099e02d1cff132.
ACCEPTANCE temporal containment: FAIL; G401's 26 duplicate/26 dropped timestamp stream was replaced by 0/0 frame and 12/26 packet summaries (g401_fps_cap_duration_shadow_2026-09-11/pts.csv:4; g408_pts_duration_stop_proposal_2026-09-11/source_receipts.csv:4).
ACCEPTANCE endpoint honesty: FAIL; the claimed 30/30 last-admitted proximity is 26/30 against unrounded 1/fps, and the inherited first-boundary extent was changed (scripts/platformkit/tracking/g408_tables.py:59; scripts/platformkit/tracking/g401_measure.py:142).
ACCEPTANCE complete proposal: FAIL; the prefetcher applies stride at proposed diff:246 before the timestamp check at proposed diff:338, so skipped malformed timestamps cannot terminate UNKNOWN.
ACCEPTANCE controls/evidence: PASS; 30 unique sources, 90 unique source-arm units, 30/30 unique 5x6 controls, 18/18 named files and 30 cards (summary.json:14; paired_stops.csv:1).
MEMO NOT VERIFIED list: PASS (g408_pts_duration_stop_proposal_2026-09-11.md:44).
B1 PASS: no source row was omitted and UNKNOWN/EOF counts are named (summary.json:6).
B2 PASS: fields are additive and the sole direct 4-tuple reader is included in the proposal (reader_survey.csv:245; PROPOSED_g408_pts_duration.diff:45).
B3 PASS: absent timestamps terminate UNKNOWN, not quarantine (scripts/platformkit/tracking/g408_stop.py:62).
B4 PASS: no claim/retry state exists in this mechanics-only row (g408_pts_duration_stop_proposal_2026-09-11.md:3).
B5 PASS: proposal_applied_anywhere is false (summary.json:34).
B6 PASS: no module was moved or retired (proposal_checks.json:18).
B7 PASS: all 30 evenly ordered cards j00-j29 were inspected (eye_index.csv:2).
B8 PASS: no fitted or inferred quantity is used (prereg.md:14).
B9 PASS: denominator is 30 unique source schedules, not recycled units (summary.json:16).
B10 FAIL: G401 tests unrounded first-boundary extent; G408 tests rounded last-admitted span (scripts/platformkit/tracking/g401_measure.py:142; scripts/platformkit/tracking/g408_tables.py:59).
Q1 PASS: seal a419e4c00ec9936bc5eefd036f822c044936a7bf82004b55bc3b276f7e90ed88 was committed before measurement (prereg.md:26).
Q2 PASS: this is an uncharged mechanics comparison with no K-dependent trial (prereg.md:23).
Q3 FAIL: endpoint definition and rounding are not byte-identical to the inherited bar (scripts/platformkit/tracking/g408_tables.py:59,103).
Q4 PASS: no OOS model comparison is made (prereg.md:14).
Q5 PASS: no comparative promotion is claimed (prereg.md:14).
Q6 PASS: independent scan of all candidate-added lines found 0 hits (q6_scan.json:7).
Q7 PASS: the construct set is exhaustive and unique at 5 classes x 6 endpoints (construct_cases.csv:2; summary.json:13).
Q8 PASS: the row is same-day; verifier nevertheless remeasured the complete premise (G408_spec.md:1).
TEST PASS: `python -m pytest tests/platformkit/test_g408_pts_stop_proposal.py -q` -> 16 passed in 0.97s.
IMPORT CENSUS PASS: that is the only existing test file importing a touched G408 module (tests/platformkit/test_g408_pts_stop_proposal.py:7).
LOC PASS: touched Python files are 73,261,120,113,112,179,109,206 lines; maximum 261 <= 300 (scripts/platformkit/tracking/g408_build.py:1).
PREMISE REPRODUCED: streamed 1,719,699,126 bytes, 30/30 source digests and 30/30 G401 endpoints/caps; exception = 26 duplicate/26 dropped, last 100.071789, first boundary 100.088489.
HEADLINE REPRODUCED: candidate artifact gives containment 30/30, DEADLINE 30/30, gap 0.000100..0.016667; exact unrounded last-admitted interval test gives 26/30, not claimed 30/30.
CORRECTION: - best-effort-only/window-only schedule; + retain and score the exact G401 frame PTS stream and archive every anomaly row.
CORRECTION: - rounded last-admitted bar; + preserve unrounded G401 first-boundary extent and report last-admitted gap separately.
CORRECTION: - validate after prefetch stride; + validate missing/backward/deadline PTS before the stride continue and add skipped-anomaly tests.
2026-09-11 | tracking | G408 | 30/30 source identities/endpoints reproduced, but required 26/26 anomalies became 0/0 and proposal validates PTS after stride filtering | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: SHA256SUMS records proposal_checks.json as 5fcfe1d747ad4a13720bf162ef9ea515bfa4a863cddf6affa4b5e6d9a8504114; actual bytes are 6bf153ddd3a5b43a3cc51678d6e78bf3d7eca410117554b7d43b01ac7c93ca8c.
NEW GAP: repeats.json uses `<tmp>` and an external unsealed cache, so its saved-input commands are not self-contained (repeats.json:46; scripts/platformkit/tracking/g408_build.py:23).
