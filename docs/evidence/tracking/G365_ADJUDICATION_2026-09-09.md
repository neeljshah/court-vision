VERDICT: CLOSED AT LIMIT (adjudicated 2026-09-09 by the orchestrator; fix 1d lands as PARTIAL)
Basis: two candidates (A: trf + Huber 2.0; B: + template-guided re-association + Huber 1.0) both REJECTED under the sealed all-four bars (G1 1.6516 -> 1.1000 / 1.1287; G3 2.0160 -> 2.1991 / 1.1165; G4 1.8003 -> 0.5992 / 0.7636; G2_WIDE 469.2083 -> 469.3300 / 469.3808, a mirror-symmetry basin); the noise sweep improved at every sigma (0.5: 0.5411 -> 0.4230 / 0.4338); the amendment's carve-out is sealed but not applied (B10/Q3); the three extra G362 geometries were never archived (Q8) so G2/G3/G4 are new quads; identical findings across fix 1c and 1d.
Licenses: the refinement modules (`g365_refine.py`, `g365_refine_b.py`, `g365_sweep.py`, `g365_sweep_b.py`) as additive tooling and the two diagnostics (the G2_WIDE mirror-symmetry basin; the G3_TIGHT foreign-support pull) as findings; licenses NO registration precision claim.
Carry-over (BINDING): G367 seals its own four quads and a modulo-symmetry metric; every future geometry fixture is archived with its quad.

--- verbatim REJECT (fix 1c) ---
VERDICT: REJECT
Candidate: b4cf9be71c877906745c902e01084de06cc351ac (full diff reviewed: memo plus additive ledger row).
ACCEPTANCE FAIL: spec:39 requires before 1.6516/1.33/1.78/1.89 px; memo:7,60 measures 1.6516/469.2083/2.0160/1.8003 on one required and three replacement quads.
PREMISE REMEASURE: direct archived-path run = 1.651641/469.208252/2.015967/1.800281 px vs memo 1.6516/469.2083/2.0160/1.8003; only the first is the spec premise.
HEADLINES PASS: direct B rerun = 1.1287/469.3808/1.1165/0.7636 px; recovery_b.csv:2-5 claims the same.
HEADLINES PASS: sweep_b.csv recompute at sigma 0.5 = baseline 0.517861, B 0.433783, n=160, worst geometry 0.4495155; exact baseline/B = 0/0 at n=160; memo:24-28 agrees.
BAR RECOMPUTE: all-four <=1.0 FALSE; sigma-0.5 TRUE; exact TRUE; no-worsening FALSE because G2 changes 469.2083 -> 469.3808; memo:33 agrees.
B1 FAIL: summary_b.json:184,187 still computes bars after excluding G2, the row that fails both all-four clauses.
B2 PASS: RESULTS_LEDGER.md:698 is additive; no schema field, status value, or reader behavior was renamed or removed.
B3 PASS: insufficient-support paths return unchanged status at g365_refine_b.py:116-118; no absent-evidence gate was added.
B4 PASS: candidate touches evidence text only; no claiming path exists in RESULTS_LEDGER.md:698.
B5 PASS: memo:4,59 records scratch-worktree measurement and no deployed-tree write.
B6 PASS: memo:59 records zero deletions; candidate has no move, retirement, import, or -m change.
B7 PASS: all 8 renders were inspected across the complete four-geometry set; prereg:192 defines that exhaustive set.
B8 PASS: held-out supports remain separate and are exercised at test_g365_fitter_refinement.py:74-90.
B9 PASS: recovery uses the fixed TEMPLATE_POINTS denominator at g365_sweep.py:75.
B10 FAIL: spec:40-41 requires all four/no worsening, but summary_b.json:184,187 and g365_sweep_b.py:211-217 retain the later exclusion.
Q1 PASS: both seals independently hold at base-prereg:248 and amendment-prereg:120; git chronology places each before its scored attempt.
Q2 PASS (N/A): this synthetic geometry row has no charged trial or launch K; memo:59 limits its scope.
Q3 FAIL: the committed summary artifact retains exclusion-based bar fields contrary to spec:40-41 and memo:33.
Q4 PASS (N/A): no OOS model score or meta-learner is claimed; memo:59 is synthetic geometry only.
Q5 PASS (N/A): no AHEAD verdict or second-corpus claim appears; memo:1,59.
Q6 PASS: candidate memo scan reports 0 controlled-vocabulary hits; the added ledger line at RESULTS_LEDGER.md:698 is clean.
Q7 PASS: g365_sweep_b.py:38,167 enumerates 40 draws per geometry/sigma; sweep_b.csv has 640 unique rows and exact is exhaustive.
Q8 FAIL: memo:60 admits three required G362 premise geometries were never archived and were not remeasured.
EVIDENCE PASS: every memo path exists; all 17 listed attempt-2 digests match, including corrected G2 render digests at memo:50.
LOC PASS: candidate touches 0 .py; row Python files are 164-300 lines, with g365_sweep.py exactly 300.
NOT VERIFIED PASS: memo:58-60 names synthetic-only scope, missing G362 quads, real-footage limits, and conditional hand-off.
TEST PASS: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g365_fitter_refinement.py -q -p no:cacheprovider` -> 11 passed in 1.58s.
TEST PASS: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g365_candidate_b.py -q -p no:cacheprovider` -> 16 passed in 1.44s.
IMPORT TEST SCAN PASS: the two G365 importer tests are the two commands above; candidate b4cf9be71 touches no module.
CORRECTION minimal diff: g365_sweep_b.py:211-217 must evaluate `names`, rename fields to `b_within_bar_all_four`/`no_geometry_worsens`, and regenerate summary_b.json with FALSE/FALSE.
CORRECTION minimal diff: update memo:48 summary digest after regeneration; the required three G362 quads/known_h artifact must be supplied and rerun, not replaced.
2026-09-09 | tracking | G365 | premise 1/4 spec geometries reproducible; B 1.1287/469.3808/1.1165/0.7636 px; all-four and no-worsening bars fail; committed summary still scores an exclusion | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: local numpy/scipy/cv2 2.2.6/1.15.1/4.11.0 reproduced distances but G4 n_fev=16 versus archived 17 from 2.1.2/1.18.1/4.14.0; iteration-count portability is untested.
NEW GAP: repository-wide controlled-vocabulary scan reports 42 pre-existing hits outside candidate-added G365 content; candidate-added content reports 0.

--- verbatim REJECT (attempt 2) ---
VERDICT: REJECT
Candidate: 31ac311bbc6355d02e5885cf89832c76b1b1c482; verifier: codex-sol; contract A/B/Q.
ACCEPTANCE FAIL: spec:39-41 requires the G362 four and no worsening; recovery_b.csv:2-5 has B=1.1287/469.3808/1.1165/0.7636 px and G2 worsens by 0.1725 px.
PREMISE FAIL: spec:18-20,39 claims 1.6516/1.33/1.78/1.89 px; independent rerun gives 1.651641/469.208252/2.015967/1.800281 because prereg:153-156 substituted three new quads.
HEADLINE PASS: memo:18-29 recovery values reproduce exactly; pooled sigma 0.50 claimed 0.5179 -> 0.4338 px, reproduced 0.517861 -> 0.433783 over 160 rows.
A1 FAIL: master does not contain tests/platformkit/test_g365_fitter_refinement.py; task-scoped candidate tests are recorded below.
A2 PASS: premise, recovery, pooled medians, p90s, and bars were recomputed independently from code/CSV; memo:7,18-35.
A3 PASS: all eight renders were inspected, one baseline/B pair for every geometry; memo:49-52.
A4 PASS: sweep_b.csv has 640 rows and 640 unique geometry/sigma/draw/seed keys; template has 398 rows and 382 unique coordinates.
A5 PASS: 31ac311bb touches no module; row-module reader grep finds only test_g365_candidate_b.py and test_g365_fitter_refinement.py.
A6 PASS: REJECT means no candidate landing; this task authorizes only the verifier memo commit.
A7 PASS: every evidence path in memo:43-55 exists; all are below 0.06 MB and renders are 1280x720.
B1 FAIL: att2 prereg:60-73 creates INIT_FAIL after attempt-1 diagnostics and :83-87 excludes that failing row from bars 1 and 4.
B2 PASS: recovery_b.csv:1 is additive, retains every geometry, and reader grep finds writer/memo/tests only; no field or prior status is removed.
B3 PASS: g365_refine_b.py:116-119 returns the prior matrix on absent support; candidate test passes at test_g365_candidate_b.py:185-191.
B4 PASS: this bounded synthetic runner has no claim/reclaim path; spec:45 supplies terminal statuses.
B5 PASS: memo:4,59 records pod scratch execution and no deployed-tree write.
B6 PASS: candidate 31ac311bb contains no moved/retired module and no orphaned import.
B7 PASS: memo:49-52 and renders_b contain the full four-geometry paired set, not a head slice.
B8 PASS: validation data is excluded and immutability is tested at test_g365_candidate_b.py:168-180.
B9 PASS: 382/398 template coordinates are unique; unique-coordinate recomputation preserves every decision (G3 B=1.108995 px).
B10 FAIL: base prereg:160,163 says ALL FOUR/NO geometry; amendment:83,87 changes both gates to NON-INIT_FAIL.
Q1 PASS: both seals verify; amendment was committed alone at 1acff8c89 before code a45003c75 and metrics 31ac311bb; memo:4.
Q2 PASS: not applicable to this uncharged deterministic synthetic row; spec:38-42 defines no K-ledger trial.
Q3 FAIL: summary_b.json:184,187 evaluates filtered bars, not the byte-identical all-four bars in spec:40-41.
Q4 PASS: not applicable; this is synthetic homography recovery, not OOS scoring; spec:38.
Q5 PASS: not applicable; memo:1,34 makes no AHEAD classification.
Q6 PASS: independent scanner reproduces memo:39-40; three hits are opaque measured/hash substrings under the contract note.
Q7 PASS: sweep_b.csv contains 40 draws per geometry/sigma, 160 per sigma and 640 unique sampled rows; memo:24-29.
Q8 FAIL: memo:59 admits three quads are not the G362 geometries required by spec:18-20,39; the binding premise was not re-measured.
LOC PASS: g365_refine.py 217, g365_refine_b.py 193, g365_sweep.py 300, g365_sweep_b.py 250; spec:51.
MEMO PASS: 59 <= 60 lines and has a NOT VERIFIED section at memo:58-59.
TEST: `python -m pytest tests/platformkit/test_g365_fitter_refinement.py -q -p no:cacheprovider` -> 11 passed.
TEST: `python -m pytest tests/platformkit/test_g365_candidate_b.py -q -p no:cacheprovider` -> 16 passed.
TEST: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed.
CORRECTION: memo:1,19,33-34 and RESULTS_LEDGER.md:696 minimally remove the carve-out decision and report bar 4 FAIL, candidate REJECT.
CORRECTION: memo:50 replace the two G2 render hashes with c17e46f0b52555a6e8ffdf0bd1e969fb555e3b9b0a419de2d685228465443af5 and b9e94fff24c4137ebb45af1f286945c884d1facbadd4f69083d12e2ffbe8ecdf.
2026-09-09 | tracking | G365 | B 1.1287/469.3808/1.1165/0.7636 px; G2 worsens 0.1725 px; all-four bars 1 and 4 fail | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: master lacks the G365 spec test, so contract A1 cannot run before landing under this verifier-only workflow.
NEW GAP: the exact three G362 comparison quads behind spec:39 were never archived; archive them before a compliant rerun.
