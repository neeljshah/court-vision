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
