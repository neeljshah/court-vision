VERDICT: REJECT
Candidate: 72602bfc587bd0489bfbbf09da702049ad82c948.
ACCEPTANCE FAIL: numerical/table/decision requirements reproduce, but contract B7 is an automatic reject; spec:55-66.
PREMISE PASS: reproduced n=2130 ticks/355 unique clusters; market 0.151529526995305, null 0.151996612536569, simulator 0.257090852406103; claimed differences <=2.78e-16; memo:8-9.
TRACE FAIL: 30 unique rows and all 30 errors are field-listed, but selected ordered ranks are 0,2129,1..28; 29/30 are in the first 29 of 2,130; trace.csv:2-31.
ABLATION PASS: reproduced all 2,130 OOF rows/355 clusters; arm (ii) improvement -0.001854369218215, CI [-0.003423916345373,-0.000462429110253], matching ablation.csv:3 to <=5e-16; sealed STOP decision is correct at memo:23.
B PASS AS PARTIAL: top-level census=9, summary JSON count=1,610, game 401703370 has 454 plays; no cached one-step simulator probability found, so no rollout and BLOCKED is honest; memo:25-27.
EVIDENCE PASS: every committed path named by the memo exists; hashes for trace, ablation and route reproduce memo:42-45; NOT VERIFIED exists at memo:33-38; EYE CHECK: NONE.
B1 PASS: all 2,130 evaluator records are retained before scoring; s322_prior_ablation.py:119-144.
B2 PASS: the candidate only adds UTC-Z compatibility; no field/status removal; s322_prior_ablation.py:77 and ablation.csv:1. Sole test importer: test_s322_sim_diagnostics.py:12.
B3 PASS (N/A): this diagnostic has no item quarantine; missing transition predictions produce PARTIAL, memo:25-27.
B4 PASS (N/A): no claim/reclaim path exists; the fixed decision is recorded at memo:23.
B5 PASS: local interpreter is named and no rollout/deployed-tree write occurred; memo:6,25-27.
B6 PASS: no file was moved or retired; the touched route remains importable at s322_prior_ablation.py:1.
B7 FAIL: sequential filler `for row in ordered` creates head-slice evidence; s322_semantics_trace.py:88,96-101.
B8 PASS: fitted arms are train-fold-only and metrics use OOF evaluator records; s322_prior_ablation.py:91-103,119-144.
B9 PASS: 2,130 unique state keys and 355 genuine game clusters; s322_prior_ablation.py:88-90,143.
B10 PASS: 0.002 and CI-lower >0 are unchanged from the seal/spec; memo:23; spec:39-41.
Q1 PASS: seal eb2a883157e6c383f4781ce0df9719651b036ce2f055f5cf97f533fb7a8b5ee5 is valid at preregistration.md:67 and its commit precedes scoring.
Q2 PASS (N/A): S322 is not a charged trial and reads no trial ledger; spec:1-4.
Q3 PASS: the sealed comparison bar is unchanged; preregistration.md:43-47; memo:23.
Q4 PASS: shared CPCV uses strict redaction and symmetric three-day embargo; s322_prior_ablation.py:101-103; each arm summary is recomputed from its OOF records at :119-144.
Q5 PASS (N/A): no AHEAD result is claimed; memo:1,23.
Q6 PASS: prohibited-language scan over candidate artifacts returned zero hits; memo:1-50.
Q7 PASS: sampled metric has n=30 and 30 unique state keys; trace.csv:2-31. B7 independently fails representativeness.
Q8 PASS: premise was independently recomputed before acceptance scoring; s322_prior_ablation.py:157-174.
LOC PASS: touched Python file s322_prior_ablation.py is 205 lines <=300; repo-wide LOC rail passed.
TEST 3 PASS: C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_s322_sim_diagnostics.py -q -p no:cacheprovider --confcutdir=tests/platformkit
TEST 1 PASS: C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider --confcutdir=tests/platformkit
MASTER: S322 test file is absent; `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider --confcutdir=tests/platformkit` passed 1.
POD ROUTING: `/c/Users/neelj/bin/pod_run a7 -- python -m pytest tests/platformkit/test_s322_sim_diagnostics.py -q -p no:cacheprovider` produced no test result because Git Bash was denied CreateFileMapping; local shared-conftest attempt had 3 temp-root setup errors.
MINIMAL DIFF s322_semantics_trace.py:96:
- `for row in ordered:`
+ `slots=n-len(unique); remaining=[r for r in ordered if str(_value(r,"state_key","timestamp")) not in seen]`
+ `indices=[] if slots==0 else [len(remaining)//2] if slots==1 else [round(i*(len(remaining)-1)/(slots-1)) for i in range(slots)]`
+ `for row in (remaining[i] for i in indices):` then regenerate trace/memo and rerun the test.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | in-game calibration | S322 | premise reproduced n=2130/355; C(ii) improvement -0.001854, CI [-0.003424,-0.000462]; B7 trace ranks 0,2129,1..28 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: The method requests frozen-logit replay, but s322_semantics_trace.py:107-132 only writes trace rows; this is outside the acceptance rule.
NEW GAP: The top-level census missed data/cache/ingame/sim2_possessions.parquet (4,405,872 bytes; 780,166 rows); its 11-column schema has no simulator probability, so B remains blocked.
NEW GAP: Q9 differential rows exist only in the untracked ablation_evaluator_records.csv; Q9 was outside this verification scope.
