GAP S302 | sport all | worktree aXX | log cx_s302_cpcv_scalar_future_plant
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: codex test audit (docs/research/codex_test_audit_2026-09-04.md section D): the scalar CPCV route
  (cpcv_engine.py cpcv_evaluate)
  has purge and symmetric-embargo assertions but NO score-sensitive planted-label test: a future same-team row that
  leaks into the target's train set would not change any asserted number. cpcv_distribution.py (S268) has one.
PREMISE (step 0): print the existing cpcv_engine test assertions that mention future rows and show none asserts a
  score change (file:line).
CHANGE (step 1): additive test tests/platformkit/eval_gate/test_cpcv_scalar_future_plant.py on a fixture: a
  future same-team row at +47 h carrying a label-revealing feature; with the real purge/embargo the row is absent
  from the target train set and the target probability stays 0.5; a CONTROL with purge disabled (fixture-level
  monkeypatch, never a code default change) exposes the plant and moves the target score (print both scores).
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames);
  engines and every existing module byte-identical unless the CHANGE names the file (SHA-256 printed).
WHERE: local construct only. POD: n/a; above 500 MB use ~/bin/pod_run <aN> --fetch <outputs> -- <command>.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = planted row absent from target train (bool); target probability under real purge; target score
                  under the disabled-purge control; their difference
  before        = no scalar-route planted-label score assertion exists
  bar           = absent = True; real-purge probability = 0.5 exactly; control difference != 0 (printed)
  n             = 1 planted case + 1 control (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns the test file
  must not move = cpcv_engine.py byte-identical (SHA-256 printed); purge/embargo constants; nothing charged
NON-TAUTOLOGY: the control MUST expose the plant; a test that passes with purge disabled proves nothing.
EVIDENCE: docs/evidence/harness/S302_cpcv_scalar_future_plant_2026-09-04.md + JSON.
TEST: exactly tests/platformkit/eval_gate/test_cpcv_scalar_future_plant.py; run only that file.
REPORT: both scores, the absence check, engine SHA-256, test line, SHA. No push. NEVER PARK.
