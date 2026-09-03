GAP S187 | sport n/a | worktree aXX | log cx_s187_deploy_pathspec
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of section B and section Q (S-row) before you report.
PREMISE (step 0): re-measure today. Closure = transitive first-party imports of the paper profile's 14 py roots (`load_profile('paper').specs()`, kind=="py"); walk ast.Import, ImportFrom(level 0), and each `from X import Y` as a submodule candidate; first-party = resolves to a .py/__init__.py under the repo root or scripts/platformkit, REPO ROOT FIRST on sys.path (else scripts/platformkit/ops/ shadows the top-level ops/ and the walk dies).
Measured 2026-09-04: 524 modules over 11 module-bearing top-level trees -- scripts 330, domains 72, predict_service 53, frontend 23, supervisor 13, ops 9, src 9, improve 8, governance 4, data_registry 2, kernel 1.
The sanctioned full-tree command pod_bootstrap.sh:13 names 5 trees (scripts/platformkit supervisor predict_service domains config), of which 4 are module-bearing (config holds no closure module). 7 closure trees are named by NO deploy command -- frontend, src, improve, ops, governance, data_registry, kernel -- holding 56/524 = 10.69 pct; S21b:219 and the S21c delta list (S21c_delta_deploy_2026-09-03.md:46) are scoped to 4 trees and miss the same 7.
All 7 are TRACKED (ops 15, kernel 34, governance 14, data_registry 4, improve 10, frontend 27, src 436 files), so the honest claim is: an edit under any of the 7 cannot reach the pod via a sanctioned deploy, and no preflight says so.
Do NOT restate "50/436 can never reach the pod", the 60-of-74 route figure, or any pod-side claim -- ssh is forbidden here, on-pod presence is UNVERIFIED. Empty unnamed set -> FALSIFIED, write the memo, commit, report.
LIMIT (step 1): recompute the tree set with AND without the `from X import Y` submodule probe. If the two disagree on the 7-tree set, no derived pathspec is trustworthy -> CLOSED AT LIMIT; report both counts.
CHANGE (step 2): ONE new file scripts/platformkit/ops/deploy_pathspec.py (<=300 LOC; pod_bootstrap_check.py is already 311 LOC -- do not extend it) exposing `deploy_trees(profile)` derived from the closure, plus `--emit` (pathspec string) and `--check` (exit 1 naming the trees pod_bootstrap.sh:13 omits). Additive: no existing file edited.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = module-bearing top-level first-party trees named by the deploy pathspec, out of the 11 in the paper-profile closure
  before        = 4 of 11 (pod_bootstrap.sh:13); 4 of 11 (S21b:219 / S21c:46); 56 of 524 closure modules (10.69 pct) sit in the 7 unnamed trees
  bar           = deploy_trees('paper') returns a superset of all 11; `--check` exits 1 naming exactly the 7; the 11 are derived from load_profile -- a literal tree list in the module is an automatic reject
  n             = 11 (CONSTRUCT -- every module-bearing tree in the closure is enumerated)
  eye check     = n/a (S-row); reproduction = re-run the step-0 closure walk and set-diff its tree set against deploy_trees('paper'); the two must be equal
  must not move = pod_bootstrap.sh, pod_bootstrap_check.py, config/boot/paper.json, supervisor/stack_specs.py, .gitignore, data/cache/eval_gate/backtest_fwer.jsonl -- all byte-identical after
NON-TAUTOLOGY: denominator = every top-level tree any closure module resolves into in-repo. Excluded: stdlib/third-party (do not resolve in-repo) and `config` (data-only, already named). No tree is dropped after seeing it fail. Disjoint from S60 (untracked `_*` helpers) and from S21/S21b/S21c (parity of the already-named trees).
EVIDENCE: docs/evidence/harness/deploy_pathspec_closure_2026-09-04.md -- per-tree closure table, both resolver counts, the 7-tree set, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file.
POD: none -- no ssh, no scp, no deploy.
COMMIT: explicit pathspec in the worktree, no push; report the sha.
NEVER PARK: poll your own jobs in a blocking loop; never end waiting.
