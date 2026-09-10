VERDICT: REJECT
Candidate: df95c430d50056f0b6523f46af3ea68f195fdc5a.
ACCEPTANCE RULE FAIL - coverage is 43/81 = 0.530864 against 1.000; selected-pin agreement must retain 81 attempts, not the 43-row join; replay has 27 completed pairs below 30 (G372_spec.md:13-17; memo:21-26,35).
PREMISE PASS - claimed/measured: 55 fresh, 35 available, 32 pinned, 20 unavailable, 3 ABSENT; 35/55 = 0.636364, 32/55 = 0.581818, 32/35 = 0.914286 (G369 ledger_snapshot.jsonl:856-910; attempts.csv:2-36; sources.csv:2-33).
HEADLINES - claimed/measured coverage 43/81 = 0.530864; claimed agreement 43/43 = 1.000000, measured 81 in-window OK pins but only 43 AGREE join rows, so corrected 43/81 = 0.530864 (claim_journal_live.csv:2-126; pins_live.csv:2-86; join_live.csv:2-44).
HEADLINES - claimed/measured replay: 27/39 complete, medians 368.64/375.79 s, ratio 1.0194; windows: 78/78 rows, medians 406.0/40.0 s (replay_pairs.csv:2-40; before_window.csv:2-79; after_window.csv:2-79).
HEADLINES - empty weight digest and deployed test regression reproduce; two queued reservations lack a terminal row (deploy_log.txt:30,34-43,92-97; claim_journal_live.csv:2-3).
CORRECTION MINIMAL DIFF - summary_phaseb_join.json: - pins_attempted 43, agreement_over_attempts 1.0; + pins_attempted 81, agreement_over_attempts 0.530864; append the 38 omitted no-sidecar attempts to join_live.csv (summary_phaseb_join.json:4-18).
B1 FAIL - 38 selected repeat pins are excluded from the agreement denominator, exactly the attempts whose sidecar writes failed; memo incorrectly says zero omitted (pins_live.csv:40-86; join_live.csv:2-44; memo:26).
B2 PASS - producer columns are identical; completion fields are additive; reader survey finds no exact-key dependency (schema_diff_phaseb.txt:1-15; schema_diff.txt:15-34).
B3 PASS - missing or terminal identity data passes through to dispatch (PROPOSED_g372_track_daemon_sidecar.diff:71-73,123-137).
B4 PASS - completed identity threads are popped and tracking proceeds; repeated claims are not attributed to this failure path (PROPOSED_g372_track_daemon_sidecar.diff:90-92,123-137; memo:45).
B5 PASS - memo records deploy after phase-A ACCEPT and only to the deploy tree (memo:3-4).
B6 PASS - candidate moves or retires no module; landing scripts remain unchanged (memo:4; PROPOSED_g372_track_daemon_sidecar.diff:1).
B7 PASS - every one of 39 replay inputs was selected; live pin collection covered the full fixed window (memo:21,34; replay_pairs.csv:2-40).
B8 PASS - no fit is used and the shared-hash limitation is disclosed (memo:25-26).
B9 PASS - coverage uses 81 distinct reservation events and replay uses unique preserved inputs (claim_journal_live.csv:2-126; replay_pairs.csv:2-40).
B10 PASS - numeric bars match the spec (G372_spec.md:14-16; g372_prereg_amendment_A3_2026-09-10.md:27).
Q1 PASS - A3 seal recomputes to 3ed7470864af67da4dd089bab017f5625be7b86462f22b24d5d8207620dc3cd6 and predates scoring (g372_prereg_amendment_A3_2026-09-10.md:1-32; memo:6).
Q2 PASS - no charged trial or K-based metric is present (summary_phaseb.json:1-81).
Q3 PASS - coverage, agreement, replay-n, and timing bars are unchanged (G372_spec.md:14-16; g372_prereg_amendment_A3_2026-09-10.md:27).
Q4 PASS - no OOS model comparison is scored (memo:14-35).
Q5 PASS - no AHEAD result is claimed (memo:36-42).
Q6 PASS - candidate supplies its restricted-language scan and only identifies opaque command text (memo:48-51).
Q7 PASS - live metrics are sampled, replay below n is not passed, and controls are separate CONSTRUCT cases (memo:27-28,35; controls.csv:2-4).
Q8 PASS - historical premise independently remeasured before adjudication (G369 ledger_snapshot.jsonl:856-910; attempts.csv:2-36).
ADDITIVITY PASS - no .py is touched; no field/status is removed or renamed and surveyed reader behavior is unchanged (schema_diff_phaseb.txt:9-15; schema_diff.txt:15-34).
LOC PASS - candidate touches no .py, so the <= 300 check is N/A (memo:4).
NOT VERIFIED LIST PASS - present and explicit (memo:53-59).
TEST: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g372_source_sidecar.py -q -p no:cacheprovider` -> 6 passed in 0.88s.
TEST: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g328_daemon_worker_accounting.py -q -p no:cacheprovider` -> 2 passed in 1.13s.
RESULTS_LEDGER_SYSTEM: 2026-09-10 | tracking | G372 | coverage 43/81; selected-pin agreement corrected from 43/43 to 43/81 after retaining 38 omitted attempts; replay 27 pairs below 30 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: Candidate history contains no committed phase-A verifier memo; the claimed predeploy ACCEPT is present only as an untracked worktree file.
NEW GAP: The deploy-only overlay is absent from the candidate tree, so the local daemon importer test passes while the archived deployed-tree run fails.
