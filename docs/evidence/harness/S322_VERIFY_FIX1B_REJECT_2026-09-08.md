VERDICT: REJECT
Candidate: `17e4301e092d31b7936a2891d9ca79df3c2f6959` (full stat and diff reviewed).
FAIL ACCEPTANCE: `S322_spec.md:62` requires 30 sealed states, but `s322_semantics_trace.py:76` omits the primary input's `ts` field from the sealed timestamp sort.
FAIL reproduction: selected boundaries are 401809239:120 (ts 1766692031) and 401850920:2520 (1769742619); true timestamp boundaries are 401810008:120 (1762128843) and 401811000:2520 (1775527545).
PASS premise: `s322_prior_ablation.py:159-171` independently returns 2,130 ticks/355 clusters and Brier market 0.151529526995305, null 0.151996612536570, simulator 0.257090852406103, matching `S322_sim_diagnostics_2026-09-08.md:7`.
PASS trace accounting: `trace.csv:2-31` has 30/30 unique states, 30 listed FAIL rows, 0 unexplained errors; recomputed rows match the CSV exactly.
PASS ablation/decision: `ablation.csv:2-4` reproduces all arms; arm (ii) Brier 0.153850981754784, improvement -0.001854369218215, CI [-0.003423916345373,-0.000462429110253], so the sealed decision is applied.
PASS replay: two independent `run_ablation` calls over 2,130 unique states give arm (ii) max absolute prediction difference 0, matching `replay.csv:2`.
PASS B result: inspected the named caches and relevant parquet schemas without loading full stores; no cached one-step simulator probability was found, so `S322_sim_diagnostics_2026-09-08.md:29` remains BLOCKED.
PASS B1: `s322_prior_ablation.py:119-147` scores the complete identity-matched 2,130-record set with no loss-based exclusion.
PASS B2: `s322_semantics_trace.py:10-13` retains trace fields/statuses; grep finds only the updated main reader at :212 and test import at `test_s322_sim_diagnostics.py:12`.
PASS B3: this diagnostic does not quarantine absent evidence; absence produces the explicit partial result at `S322_sim_diagnostics_2026-09-08.md:1,29`.
PASS B4: the sealed failed decision is terminal in `S322_sim_diagnostics_2026-09-08.md:25`; no claim loop exists.
PASS B5: the memo records the local interpreter at `S322_sim_diagnostics_2026-09-08.md:5`; candidate diff contains no deployed-tree change.
PASS B6: no module was moved or retired; the implementation and sole test import remain at `s322_semantics_trace.py:1` and `test_s322_sim_diagnostics.py:12`.
PASS B7: reproduced ranks 0,1,80,159,237,316,395,474,552,631,710,789,868,946,1025,1104,1183,1261,1340,1419,1498,1577,1655,1734,1813,1892,1970,2049,2128,2129; not a head slice (`S322_sim_diagnostics_2026-09-08.md:14`).
PASS B8: calibrators fit only evaluator train rows at `s322_prior_ablation.py:36-53,94-103`; reported losses are OOF records.
PASS B9: `s322_prior_ablation.py:84-91,143` enforces 2,130 unique states and reports 355 game clusters.
PASS B10: trace/replay/C bars in `S322_sim_diagnostics_2026-09-08_preregistration.md:37,50-53` match `S322_spec.md:59-64`.
PASS Q1: seal eb2a883157e6c383f4781ce0df9719651b036ce2f055f5cf97f533fb7a8b5ee5 verifies at `S322_sim_diagnostics_2026-09-08_preregistration.md:67`; commit ee6a34a92 predates scoring commit 72602bfc5.
PASS Q2: this fixed-arm diagnostic is not a charged trial and defines no K (`S322_spec.md:3-18`).
PASS Q3: no bar moved; see B10.
PASS Q4: `s322_prior_ablation.py:94-103` uses strict `cpcv_evaluate` with a symmetric 3-day embargo and unique-state guard; `cpcv_engine.py:139-143` asserts the purge.
PASS Q5: no AHEAD claim is made; the result is PARTIAL and the sealed decision fails (`S322_sim_diagnostics_2026-09-08.md:1,25`).
PASS Q6: restricted-claim scan is clean across the S322 memo, preregistration, and artifacts.
PASS Q7: reproduced n=30 unique trace states and n=2,130 unique scored states (`trace.csv:2-31`; `ablation.csv:2-4`).
PASS Q8: premise was recomputed before comparisons by `s322_prior_ablation.py:185`; verifier independently repeated it.
PASS evidence/LOC: all named evidence exists; LF hashes match `S322_sim_diagnostics_2026-09-08.md:45-51`; touched Python LOC is 225 and 81, both <=300; candidate memo has NOT VERIFIED at :36.
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_s322_sim_diagnostics.py -q -p no:cacheprovider` -> 4 setup errors from inaccessible pytest temp locks, not candidate assertions.
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_s322_sim_diagnostics.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 4 passed.
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 1 passed.
CORRECTION (minimal diff): `s322_semantics_trace.py:76` add `"ts"` to `_value(row, "timestamp_utc", "timestamp")`, regenerate trace/ranks/hash, and change memo :43 test LOC 79 to 81.
NOT VERIFIED: transition-law hypothesis, end-state calibration, season generality, or cross-environment equivalence.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | in-game calibration | S322 | premise 2130/355 reproduced; sealed trace invalid because ts alias omitted; arm (ii) improvement -0.001854369218215, CI [-0.003423916345373,-0.000462429110253] | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: `s322_semantics_trace.py:163-170` is sequential bucket exhaustion, not round-robin; a dense construct with 20 overtime rows and 2 venues selects 0 from both later buckets.
NEW GAP: recursive verification finds 35 current pbp/possession path matches versus memo :29's 9; inspected NBA parquet schemas still contain no cached one-step simulator probability, so the B status is unchanged.
