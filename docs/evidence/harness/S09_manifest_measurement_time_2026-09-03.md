# S09 manifest measurement time

GAP S09 | sport all (harness) | worktree a13 | log cx_s09_manifest_measurement_time
CONTRACT: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q; construct row under `CODEX_SPEC_TEMPLATE.md`.

PREMISE (2026-09-02T04:56:48Z): `Select-String -CaseSensitive` found 0 hits for `measured_at|measured_at_source` and 0 hits for `\bSTALE\b|max_age|max-age` in `gate_manifest.py`.
`build_manifest(Path('.').resolve())` measured mtime fallback `45/45`; no row had neither source. This is the honest current ceiling for measurement-time judgements.
The scoped premise holds: before = `0/3` cases block because no provenance fields, `STALE` status, or max-age claim gate existed.

LIMIT: n/a; all three claim outcomes are constructed and enumerated.
CHANGE: additive `measured_at` and `measured_at_source`, `StaleEvidence` / `assert_fresh`, plus opt-in `--max-age-days`; no-flag statuses, existing fields, staleness values, and exit semantics remain unchanged.

ACCEPTANCE RULE:
metric = the block fires; denominator = 3 cases (fresh / stale / absent).
before = 0/3; bar = 3/3 with absent treated as stale; n = 3 (CONSTRUCT).
eye check = n/a (S-row); reproduction = rerun the three test files and recompute the live mtime-fallback fraction above.
must not move = existing fields and statuses OK / EMPTY / UNREADABLE, six fail-closed fixes, reader behavior, existing gate values and thresholds, registry, and the named backtest ledger.

NON-TAUTOLOGY: all three cases are scored. Mtime-only and corrupt evidence are included and block; excluding them would make the result circular. The claim gate raises rather than quarantining an item.

| Case | Construct | Result |
|---|---|---|
| Fresh | `generated_at` one day before as-of | `field:generated_at`; `assert_fresh(30)` passes |
| Stale | `generated_at` 400 days before as-of, current mtime | Field remains authoritative; assertion raises; CLI writes `STALE` and exits 1 |
| Absent | mtime-only artifact plus corrupt artifact | Both appear in the raised exception; neither is skipped |

TEST:
`python -m pytest scripts/platformkit/eval_gate/test_gate_manifest_measured_at.py -q` -> `4 passed in 1.01s`.
`python -m pytest scripts/platformkit/eval_gate/test_gate_manifest.py -q` -> `14 passed in 2.54s`.
`python -m pytest scripts/platformkit/mcp/test_gate_manifest_tool.py -q` -> `7 passed in 0.83s`.
The MCP reader remains unchanged and returns row dictionaries verbatim; its compatibility suite is green.

NOT VERIFIED:
- No caller sets `--max-age-days` yet; S27 is the row that arms it.
- No pod work or deployment was performed; no production registry, cache ledger, or feature flag was written.
