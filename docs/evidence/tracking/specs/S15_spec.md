GAP S15 | sport all (signals) | worktree a13 AFTER S11 LANDS (same new package) | log cx_s15_results_db
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of section B AND section Q (Q1-Q8) before you report. Template: docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md.
GAP (verbatim from the register): no results DB: a re-proposed hypothesis is a fresh trial rather than a lookup, and nothing indexes the trial artifacts.
READ (read every signature on disk; line numbers drift): scripts/platformkit/foundry/grammar.py as landed by S11 (`Hypothesis`, `semantic_hash`) -- if absent, S11 has not landed: STOP and report BLOCKED; scripts/platformkit/foundry/tiers.py `TierResult` if S12 has landed (if not, define the DB against the field list below and say so); scripts/platformkit/eval_gate/backtest_runner.py `_charge_ledger` (THE only ledger writer). Library: STDLIB `sqlite3` only -- no new dependency; MLflow / DVC / Arize Phoenix are REJECTED (one more service to keep alive on the pod for a job one stdlib file does).
PREMISE (step 0): `data/cache/eval_gate/hypotheses.sqlite` is ABSENT (verified 2026-09-03: the directory holds backtest_fwer.jsonl, its .lock, two trial JSONs and gate_manifest.json) and `scripts/platformkit/foundry/results_db.py` is ABSENT -- before = 0 hypotheses indexed, every re-proposal is a fresh trial. If either exists, STOP, write the memo, commit, report FALSIFIED.
LIMIT (step 1): n/a -- CONSTRUCT row; the two proposals of the same hash ARE the enumerated case set.
CHANGE (step 2): NEW `scripts/platformkit/foundry/results_db.py` (<=300 LOC), stdlib `sqlite3`, one file at `data/cache/eval_gate/hypotheses.sqlite` (gitignored, pod-authoritative, backed up nightly by S29; `data/registry/` is NEVER agent-written and a tracked path would leak research state to the public origin). SCHEMA, verbatim:
  hypothesis(hash TEXT PK, family, sport, feature, transform, params, conditioning, horizon, market, runtime_available INTEGER, created_at, grammar_version)
  result(id INTEGER PK, hash REFERENCES hypothesis, tier, corpus, corpus_unit, n INTEGER, n_eff REAL, brier_model REAL, brier_close REAL, dm_stat REAL, raw_p REAL, k_family INTEGER, k_global INTEGER, deflated_p REAL, pbo REAL, verdict, artifact_path, prereg_sha256, run_at)
         UNIQUE(hash, tier, corpus, corpus_unit)
  queue(hash TEXT PK, tier, enqueued_at, claimed_at)
  API: `upsert_hypothesis(h) -> hash`; `lookup(hash, tier, corpus, corpus_unit) -> Row | None`; `record(TierResult)`; `enqueue(hashes, tier)`; `claim(n) -> list[Hypothesis]` in ONE transaction. `artifact_path` points at `data/cache/eval_gate/trials/<hash>_<tier>_<corpus_unit>.json` -- the DB INDEXES the evidence and never replaces it. The DB accepts a db path argument so tests use `tmp_path`.
TEST: NEW tests/platformkit/foundry/test_results_db.py: on a tmp DB and a TMP ledger path, the SAME hash proposed twice at T2 yields 1 trial + 1 lookup and the tmp ledger's K is UNCHANGED on the second proposal; one hypothesis and one result round-trip every column; the UNIQUE constraint rejects a duplicate (hash, tier, corpus, corpus_unit); `claim(n)` is atomic (a claimed row is not claimable again). Run ONLY that file: `python -m pytest tests/platformkit/foundry/test_results_db.py -q`.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = re-proposal charges nothing; denominator = 2 proposals of the same hash
  before        = 0 (no DB; every re-proposal is a fresh trial)
  bar           = 1 trial + 1 lookup, with the tmp ledger K UNCHANGED on the second proposal, and one hypothesis + one result round-tripping every column
  n             = 2 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns the test in master and re-reads the tmp ledger row count before and after the second proposal
  must not move = data/cache/eval_gate/backtest_fwer.jsonl (13 rows -- the test uses a TMP ledger only), `_charge_ledger`'s signature and lock semantics, every threshold under scripts/platformkit/eval_gate/, data/registry/** (never written)
NON-TAUTOLOGY: both proposals are in the denominator; the second is not excluded or renamed to make the lookup path fire. No `_charge_ledger` call against the real ledger path anywhere -- the tmp ledger only; indexing is not a trial.
EVIDENCE: docs/evidence/harness/S15_results_db_2026-09-03.md -- the premise absence check, the schema as created (dump it), the two-proposal trace with the tmp ledger K before and after, the round-trip column list, test output, and a NOT VERIFIED list. Calibration language only (Q6): no dollar, ROI, profit or edge word.
POD: none. Local sqlite only. No deploy before ACCEPT (B5).
COMMIT: explicit pathspec (results_db.py, the test, the memo), in this worktree, no push -- never commit the .sqlite file itself. Last line of your report: `SHA: <sha>`.
NEVER PARK: run everything to completion this turn; never end waiting.
