VERDICT: ACCEPT
Candidate: c25ee30aa4461a28698425123c41be3868083753; one memo-line correction only (g372_inline_source_pinning_2026-09-10.md:5).
ACCEPTANCE RULE PASS - phase A is correctly PARTIAL: coverage 5/50 = 0.100000 fails 1.000, agreement is 5/50 with only 5 joinable, and DONE/throughput/live claims are not made (memo:26-27,42-45).
EVIDENCE PASS - every spec evidence path exists; snapshot, proposed diff, and before-condition LF hashes reproduce 1547d32d..., e0d8e924..., and a46bda1f... (memo:7,12,32).
PREMISE REPRODUCED - claimed and measured: 35/55 = 63.6364 pct available; 32/55 = 58.1818 pct pinned; 32/35 = 91.4286 pct; 20 unavailable; 3 ABSENT (G369 sources.csv:2, attempts.csv:2).
HEADLINES REPRODUCED - claimed/measured: 149 unique sections; 122 unavailable, 122/122 attributed; re-tracked 85/125 then 0/24; deletion medians 10.567/3.083 min (attribution.csv:2, deleters.csv:2).
SCRATCH REPRODUCED - claimed/measured: indices 0..147 by 3, n=50; 5 OK/45 BYTES_GONE; 5 AGREE/45 retained failures; 25 sampled videos, 4 committed; 3/3 controls PASS (sampled_indices.csv:2, join.csv:2, controls.csv:2).
B1 PASS - all 50 sampled attempts remain in coverage and agreement denominators (join.csv:2; memo:24-27).
B2 PASS - no field/status removal; proposed source_identity_path is additive and the reader survey finds no exact-key dependency (PROPOSED_g372_track_daemon_sidecar.diff:104; schema_diff.txt:15).
B3 PASS - an absent identity handle passes the item to launch (PROPOSED_g372_track_daemon_sidecar.diff:60,117).
B4 PASS - pending identity is popped and terminal failures are journaled, not retried by the identity route (PROPOSED_g372_track_daemon_sidecar.diff:58-60,121-127).
B5 PASS - overlay remained proposed; deploy tree and data were read-only (memo:5,31-33).
B6 PASS - candidate moves/retires no module or reference (g372_inline_source_pinning_2026-09-10.md:5).
B7 PASS - preregistered sample spans the full ordered window, every third index through 147 (memo:24; sampled_indices.csv:2).
B8 PASS - no self-fit claim; same-byte hash agreement scope and limitation are explicit (memo:27-29).
B9 PASS - denominators are unique game_id attempts, not recycled rows; n=50 over 25 videos (memo:24-27).
B10 PASS - bars remain 1.000, 100 pct, n>=30, videos>=10, and throughput ratio<=1.10 (G372_spec.md:14-16; amendment_A2:15).
Q1 PASS - all three seals reproduce; A2 commit 07ece33f2 predates metric commit 8a8303a6e (memo:6; amendment_A2:20).
Q2 PASS - no charged trial, K, or K-based metric exists (summary.json:2).
Q3 PASS - no acceptance bar or threshold moved (amendment_A2:15; G372_spec.md:14-16).
Q4 PASS - no OOS or model comparison is scored (memo:42-48).
Q5 PASS - no AHEAD result is claimed (memo:42-48).
Q6 PASS - candidate and memo automated scans have zero restricted-language findings (memo:38-40).
Q7 PASS - scored n=50 exceeds 30; three deterministic controls are separately exhaustive CONSTRUCT cases (memo:24,28).
Q8 PASS - the 55-section historical premise was independently remeasured before adjudication (G369 ledger_snapshot.jsonl:856; attempts.csv:2).
ADDITIVITY PASS - candidate touches no .py; the proposed overlay adds one ledger key and reader behavior is unchanged (schema_diff.txt:15-34).
LOC PASS - row Python files are 140, 128, and 294 lines; tests are 73 and 81 (memo:35).
NOT VERIFIED LIST PASS - live coverage, live schema, throughput, runtime overlay behavior, third implementation, survival effect, and future prune policy are listed (memo:42-48).
TEST: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g372_source_sidecar.py -q -p no:cacheprovider` -> 6 passed in 0.84s.
TEST: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g372_phase_a.py -q -p no:cacheprovider` -> 4 passed in 2.11s.
TEST: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed in 0.69s.
CORRECTIONS: none.
RESULTS_LEDGER_SYSTEM: 2026-09-10 | tracking | G372 | phase-A premise and headlines reproduce; corrected even sample retains 50/50 attempts, with coverage and agreement 5/50 and live clauses still not verified | ACCEPT (verified: codex-sol, contract A/B/Q)
NEW GAP: Contract A1 requests a MASTER rerun, but the G372 tests are absent from master and this verification scope forbids landing; commands above ran at candidate HEAD.
NEW GAP: The memo cites G372_VERIFY_att1_REJECT_2026-09-10.md, which exists locally but is untracked and absent from the candidate tree (memo:4).
