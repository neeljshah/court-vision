VERDICT: REJECT
Candidate: 895b597486f632d9828b462f8adafd48ac941f90; scope is phase A and a PROPOSED overlay.
ACCEPTANCE RULE FAIL - scratch coverage is not over all unique attempts and is not an even sample (G372_spec.md:13-16; g372_phase_a.py:74-76,101-108,196-230).
A1 PASS - focused tests rerun one file per command at candidate HEAD (G372_spec.md:19).
A2 PASS - premise and headline tables independently recomputed (g369_prospective_identity_2026-09-09/ledger_snapshot.jsonl:856; attribution.csv:2; join.csv:2).
A3 PASS - no render claim; all 40 sampled sidecar rows are archived (sidecars.csv:2).
A4 PASS - 149/149 attribution game_ids and 40/40 join game_ids are unique; 15 videos (attribution.csv:2; join.csv:2).
A5 PASS - completion field is additive; Python and shell readers preserve behavior (schema_diff.txt:16; tracking/loop_status.sh:30).
A6 PASS - verifier-only commit required here; candidate landing was not performed (VERIFIER_CONTRACT.md:16).
A7 FAIL - named snapshot, collect_manifest.csv, and standalone PROPOSED diff are absent (memo:11,23,30).
B1 FAIL - exercise reads only scratch *.mp4 successes, not the attempt manifest (g372_phase_a.py:196,227-230; G372_spec.md:13).
B2 PASS - no producer field/status removal; source_identity_path is additive (PROPOSED_g372_track_daemon_sidecar.md:20-24; schema_diff.txt:34).
B3 PASS - terminal metadata failure passes tracking through (PROPOSED_g372_track_daemon_sidecar.md:23-24,103-105).
B4 PASS - pending claim is popped before launch and failures are terminal (PROPOSED_g372_track_daemon_sidecar.md:134-150).
B5 PASS - overlay remained proposed and pod deploy tree was read-only (memo:4,29-30).
B6 PASS - no module was moved or retired (895b59748 diff; g372_phase_a.py:1).
B7 FAIL - collector sorts each directory and stops at the first 40, not an even full-window sample (g372_phase_a.py:74-76,101-106; G372_spec.md:14,16).
B8 PASS - comparison uses the separately implemented G369 file record; limitation disclosed (memo:25-27).
B9 PASS - denominators are unique game_ids: attribution n=149; scratch n=40 across 15 videos (memo:11,23-25).
B10 PASS - numeric bars remain 1.000/100 pct, n>=30, videos>=10, throughput<=1.10 (G372_spec.md:14-15; prereg_amendment_A1:9).
Q1 PASS - seals recompute to 6e6469a0... and 21c128729...; amendment commit 9ce396284 predates metrics (memo:5).
Q2 PASS - no charged trial or K-based metric exists (memo:34; summary.json:1).
Q3 PASS - no numeric threshold was lowered (G372_spec.md:14-15; prereg_amendment_A1:9).
Q4 PASS - no OOS/model comparison was scored (prereg_amendment_A1:15).
Q5 PASS - no AHEAD result was claimed (memo:37-42).
Q6 PASS - automated candidate-diff scan found 0 vocabulary and 0 restricted-number findings (memo:35).
Q7 PASS - sampled n=40 and three CONSTRUCT controls are separate and exhaustive (controls.csv:2-4; memo:23-26).
Q8 PASS - premise remeasured from 55 unique fresh rows: available 35 and pinned 32 (G372_spec.md:4).
PREMISE REPRODUCED: 35/55=63.6364 pct available; 32/55=58.1818 pct pinned; 32/35=91.4286 pct; 20 unavailable; claimed matches.
HEADLINES REPRODUCED: gone 122/149 and attributed 122/122; medians 10.567/3.083 min; re-tracked 85/125 then 0/24; claimed matches.
SCRATCH TABLES REPRODUCED: committed 40/40, agreement 40/40, 15 videos, controls 3/3 PASS; acceptance validity fails B1/B7.
TEST: `python -m pytest tests/platformkit/test_g372_source_sidecar.py -q -p no:cacheprovider` -> 6 passed in 0.73s.
TEST: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed in 0.94s; no test imports touched module g372_phase_a.
LOC PASS: touched g372_phase_a.py = 300 lines; memo has NOT VERIFIED at lines 37-42.
CORRECTION DIFF: - derive sources from sorted scratch files; + read archived collect_manifest, retain every unique attempt, and left-join failures into coverage/agreement.
CORRECTION DIFF: - stop at sorted first 40; + seal the full window, choose even indices, archive snapshot/manifest, then rerun; commit or stop citing the standalone diff.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-10 | tracking | G372 | premise and attribution reproduce, but scratch scoring excludes non-copied attempts and uses a sorted first-40 sample | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: Proposed overlay opens the source inside its worker, not immediately at the hook (G372_spec.md:8; PROPOSED_g372_track_daemon_sidecar.md:92-96).
NEW GAP: No existing test imports touched g372_phase_a.py, leaving collection denominator and sampling behavior unexercised.
