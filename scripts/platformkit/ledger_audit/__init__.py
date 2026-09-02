"""scripts.platformkit.ledger_audit -- read-only CLV ledger duplicate-key audit.

Measurement-only sidecar: scans clv_ledger.jsonl for duplicate row keys using
the same derivation formula as governance/concurrency_guard._row_key, emits a
visible report to data/frontend/ops/clv_dup_report.json. NEVER mutates or
dedupes the ledger (that is human-gated governance).

Components:
  dup_key_detector  -- pure scan + report
  dup_runner        -- entry point + heartbeat (m18_dupaudit)
"""
