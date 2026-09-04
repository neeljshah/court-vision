GAP S295 | sport all | worktree a17 | log cx_s295_strict_redaction_wrapper
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: codex gap audit (the orchestrator-held codex gap audit (local-only; NOT a lane input) gap 6):
  walkforward.py:19-21,125
  leaves strict_redaction False by default and callbacks can close over raw arrays (s272_ingame_tail_recal.py:74,107),
  so an undeclared settled field is readable by a predictor. Additive wrapper only; engines byte-identical.
WHERE: local construct only; no data store.
PREMISE: show default-false redaction and a callback reading a planted raw settled field.
LIMIT: if the planted callback cannot alter a score, report FALSIFIED and stop.
CHANGE: additive isolated evaluator: serialize only declared features and a declarative predictor spec into a
  fresh subprocess; raw corpus arrays are never imported or inherited there.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Print RSS before/after; a scorer above 500 MB runs via ~/bin/pod_run <aN> --fetch <outputs> --
  <command> (B5 NOTE). Never write data/ or docs/research/; never rewrite an existing artifact (new dated names).
ACCEPTANCE RULE:
  metric = planted leak detections and valid-caller Brier replay error.
  before = undeclared settled field is readable under default mode in the construct.
  bar = 6/6 closure, module-global and default-argument plants rejected across walk-forward and CPCV; valid replay
        error <= 1e-12.
  sign = improvement = baseline loss minus candidate loss; positive = candidate better; compared with the frozen
         +0.004 bar.
  n = 6 (CONSTRUCT), exhaustive across walk-forward/CPCV and three attack forms.
  eye check = n/a; reproduction = rerun all six cases and valid fixture.
  must not move = cpcv_engine.py, walkforward.py, existing defaults, and thresholds.
NON-TAUTOLOGY: attacks are fixed before wrapper execution; valid fixture is independent.
EVIDENCE: docs/evidence/harness/S295_strict_redaction_wrapper_2026-09-04.md plus JSON.
REQUIRED EVIDENCE DURABILITY: archive inputs, exceptions, and valid replay records.
RE-EMITTED TABLES: existing record fields preserved; diagnostics are additive.
TEST: exactly one per-file construct test containing all six cases.
REPORT: premise counts, the metric table with CIs, RSS, test line, SHA. No push. NEVER PARK.
