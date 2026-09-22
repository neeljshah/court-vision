# S351 runbook compliance

Verdict: PREPARE-ONLY; standalone scaffold prepared, operational readiness NOT VALIDATED.
Vocabulary follows contract Q6; automated scan required.

Machine: local C:/Users/neelj/nba-harness-h6, for code reads and synthetic tests.
Pod OFF. No capture, operational invocation, data/ writes, scoring or measured number.
Only new files; no feature flags, production callers, existing thresholds or schemas changed.

Binding before-condition, rerun before construction:
`ls docs/operations` (PowerShell Get-ChildItem) returned:
backfill-100-games.md, data-pipeline.md, deployment.md, fresh-pod-bootstrap.md,
full-game-production.md, new-pod-checklist.md, PUBLIC_PRIVATE_WORKFLOW.md,
runpod-runbook.md, runpod_video_sync_notes.md, tennis_reacquisition_2026-09-01.md.
No maker-channel runbook was present.
`ls scripts/platformkit/execution/venue_eligibility.py` (PowerShell Get-Item) failed:
"Cannot find path 'C:\Users\neelj\nba-harness-h6\scripts\platformkit\execution\venue_eligibility.py' because it does not exist."

Deliverables: runbook and retention scaffold under docs/operations; pure read-only
eligibility evaluator and all-unknown JSON table under scripts/platformkit/execution;
synthetic tests under tests/platformkit/execution. Unknown entries are placeholders,
not state-status assertions. Explicit arguments make evaluation deterministic;
None state opts into the specified environment fallback. No network access is used.

Reproduction from the worktree root, with PYTHONDONTWRITEBYTECODE=1:
`python -m pytest tests/platformkit/execution/test_venue_eligibility.py -q -p no:cacheprovider`
Initial gate-only run: 39 passed. Final documentation checks are recorded below.
Cases cover each refusal branch, available synthetic evidence, exact freshness
boundary, environment fallback and precedence, malformed/unreadable tables,
duplicate identities and the shipped unknown status. All fixtures are in memory.
Documentation checks cover citation resolution, ASCII, Q6 vocabulary and file limits.
No sampled or scored metric; construct cases exclude no failing observations.

Contract B self-check: B1/B7/B8/B9 inapplicable (no metric); B2/B6 additive new
files only; B3 explicit eligibility refusal required by spec, no ingest changes;
B4 no claim loop; B5 no deployment; B10 no existing threshold changed.
Contract Q self-check: Q1/Q2/Q4/Q5 inapplicable (no scoring, trial or comparative
claim); Q3 no acceptance bar changed; Q6 automated scan; Q7 synthetic cases only;
Q8 premise rerun above. No evidence ledger or register mutation in PREPARE-ONLY.

Final per-file output: `41 passed in 0.60s` (exit 0). This is a construct test
count, not a measured system result. ASCII, Q6 and citation checks passed in that
same file. Existing tracked files remain unchanged; all deliverables are new.

Citation grep check: extracted every file:line from both operations documents,
sorted unique, read the named source line and refused any empty/missing line.
PowerShell reproduction: use `[regex]::Matches(content, '(?:scripts|api|docs)/[A-Za-z0-9_./-]+:\d+')`,
split each match on colon, and select `Get-Content(path)[line - 1]`.
Pasted check output (path | matching source line):

```text
api/_risk_router.py:227 | {"error": str(exc), "ok": False, "kill_switch_engaged": True,
api/_risk_router.py:239 | @router.post("/api/risk/kill-switch", tags=["risk"])
api/_risk_router.py:254 | write_kill_switch(body.engage, body.reason)
api/_risk_router.py:51 | """Constant-time check of the cv_session cookie, then the ?token= fallback."""
api/_risk_router.py:71 | def mutating_auth_dep(request: Request, token: Optional[str] = Query(None)) -> None:
docs/evidence/tracking/specs/S342_spec.md:45 | flatten deadline the engine is reduce-only and unresolved inventory stays visible in the return value (maker-only cannot
docs/evidence/tracking/specs/S345_spec.md:13 | 1. scripts/platformkit/execution/position_ledger.py (<= 300 LOC, stdlib, ASCII): append-only JSONL event log
docs/GO_LIVE_GATES.md:15 | All six gates must pass. No gate may be weakened after its own result is seen.
docs/GO_LIVE_GATES.md:19 | | G1 Corpus integrity | The in-game join checker exits 0 on every captured sport and carries a test that detects a deliberately mis-anchored file | any downstream number is computed on a corpus that fails it |
docs/GO_LIVE_GATES.md:23 | | G5 Venue and legal boundary | Per-state legality encoded in code; venue terms, limits and settlement rules documented; record-retention and tax policy written; a go-live runbook with a flatten procedure | human-only gate; an agent may never assert it passed |
scripts/platformkit/clv_ledger.py:319 | def append_settlement(
scripts/platformkit/clv_ledger.py:49 | DEFAULT_LEDGER = _HERE.parents[1] / "data" / "frontend" / "clv_ledger.jsonl"
scripts/platformkit/execution/circuit_breaker.py:117 | capped = median is None or median < 0.0
scripts/platformkit/execution/executor/lifecycle.py:124 | if not _live_flag_set():
scripts/platformkit/execution/executor/lifecycle.py:209 | def cancel(self, order: ExecOrder) -> ExecOrder:
scripts/platformkit/execution/executor/lifecycle.py:75 | class ExecOrder:
scripts/platformkit/execution/executor/lifecycle.py:89 | history: List[Tuple[float, str]] = field(default_factory=list)
scripts/platformkit/execution/executor/reconcile.py:68 | def reconcile_row(row: Dict[str, Any], depth_by_ticker: Dict[str, List[Dict[str, Any]]],
scripts/platformkit/execution/paper_maker.py:220 | if _market_suspended(tick):
scripts/platformkit/execution/paper_maker.py:229 | if (age is not None and
scripts/platformkit/execution/quote_engine.py:125 | deadline = _number(caps['flatten_deadline_s'])
scripts/platformkit/execution/quote_engine.py:167 | 'unresolved_inventory': inventory}
scripts/platformkit/execution/quote_engine.py:98 | if _suspended(book, state):
scripts/platformkit/execution/venue_eligibility.py:13 | def check(
scripts/platformkit/ingame/inplay_breaker.py:120 | def allow(market: str, now: datetime,
scripts/platformkit/ingame/inplay_breaker.py:70 | def _load_channel_rows(ledger_path: Optional[Path],
scripts/platformkit/ingame/inplay_capture_loop.py:1180 | positions: Dict[str, Dict[str, Any]] = {}
scripts/platformkit/ingame/inplay_capture_loop.py:65 | DEFAULT_HEARTBEAT = _REPO_ROOT / "data" / "cache" / "ingame_grade" / "_capture_heartbeat.json"
scripts/platformkit/ingame/inplay_capture_runner.py:103 | def run(*, sports: Optional[List[str]] = None,
scripts/platformkit/ingame/inplay_capture_runner.py:151 | def _main() -> int:  # pragma: no cover -- thin CLI shim
scripts/platformkit/ingame/inplay_capture_runner.py:169 | except KeyboardInterrupt:
scripts/platformkit/ingame/inplay_status.py:120 | def load_heartbeat(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
scripts/platformkit/ingame/kalshi_book_capture.py:13 | data/cache/ingame_books/kalshi_multi/<sport>/, NOT ingame_books/mlb/ -- the landed
```

SHA: NOT CREATED (sandbox); files ready for lane_commit

## NOT VERIFIED

- Runtime capture heartbeat, maker session start/stop and breaker state.
- API kill-switch behavior in a running service; cancellation or guaranteed flatten.
- Position event-log recovery, sequence-gap recovery and complete reconciliation.
- Any state's venue status, owner retention decisions or tax treatment.
- Enforcement integration, production behavior and any go-live gate acceptance.
- Commit or landing in another worktree.
