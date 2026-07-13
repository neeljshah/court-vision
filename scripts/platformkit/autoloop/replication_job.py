"""scripts.platformkit.autoloop.replication_job -- M21: cadence-gated
auto-replication of interaction-factory gate survivors. Every ledger row
whose LATEST verdict (by candidate_id) is SURVIVES_PREREG_PROVISIONAL and
that carries NO replication row anywhere in the ledger yet gets its
second-corpus replication run automatically -- closing the gap replicate_*
CLIs left as a human-run-by-hand-only path (mirrors M15/eval_gate/M18's own
"nothing daemons this" finding).

WORKER REUSE (thin cadence wrapper, not a reimplementation): this job never
fits a model or appends a ledger row itself. It only decides WHEN to call
each family's EXISTING replicate() -- replicate_survivors.py (batch-1 NBA)
or replicate_batch2b.py (batch-2b MLB archetype + tennis, which itself
records REPLICATION_BLOCKED for tennis when no disjoint corpus exists --
that IS a replication row, so a later tick correctly treats it as done).
replicate_tennis_2026's later refire of an already-BLOCKED row is a
deliberate re-arm and out of THIS job's join-key scope (it targets rows
that already have a replication row, just a blocked one).

JOIN KEY: (candidate_id) via the ledger's own `replication_of` field -- the
SAME field replicate_tennis_2026._tennis_blocked_rows/`by_id` already reads
back out of this ledger, not a new convention. A row tagged
SURVIVES_PREREG_PROVISIONAL is ALWAYS an original discovery-time row (no
replicate_* worker ever writes that verdict), so scanning for that verdict
with no matching replication_of elsewhere is exactly "un-replicated
survivor".

FAMILY_WORKERS maps template_id -> the worker's replicate(). nba_shot_attr_x_
state is now registered too (replicate_nba_2026.py, 2026-07-13 -- season-based
second corpus, same shape as replicate_survivors.py's sibling template). A
survivor family with no registered worker is reported NO_WORKER_REGISTERED --
an honest gap, never a guessed generic fit.

Each worker's replicate() reprocesses its WHOLE family every call (no
partial-candidate-list API) -- it re-selects every original SURVIVES row
for its template(s) from the ledger, so calling it appends one fresh row
per family member, including ones already replicated (same behavior the
worker already exhibits across e.g. replicate_batch2b.MLB_REPL_YEARS
2024/2026 reruns -- not a defect introduced here). This job therefore
bounds ticks by FAMILY, not raw candidate count: it calls a family's worker
only if that family's PENDING count fits within the remaining MAX_PER_TICK
budget for this tick; a family that doesn't fit is deferred (retried next
tick, no separate waiting-period logic -- the ledger is rescanned fresh
every tick, no age-based skip).
# ponytail: a single family accumulating >MAX_PER_TICK new survivors between
# ticks would starve indefinitely (whole-family defer, no partial split) --
# propose_gate's own per-cycle K=8 cap makes this rare; raise MAX_PER_TICK or
# teach a worker a candidate subset if it ever bites.

WATERMARK (M20 lesson, commit d1e8eccb): stamped in `watermarks[STATE_KEY]`
ONLY when every family attempted this tick ran without raising (PARTIAL --
one family's worker raised -- or a total failure never stamps), so the same
pending candidates are retried next tick, never silently dropped. There is
no cadence/staleness gate on top of this (task rail: "no waiting period
needed") -- the job always rescans the ledger fresh; the stamp is a
last-run record for observability only, matching call-shape uniformity with
every other maintenance job (STATE_KEY dict, same convention as M02/M07/M08/
M10).

ledger_lock (commit 2d071426): already held internally by each worker's own
append_jsonl_atomic call -- this job never writes the ledger directly, so it
needs no lock of its own.

CLI (dry-run/list-only, no writes):
    python -m scripts.platformkit.autoloop.replication_job --dry-run

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_replication_job.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.interaction_factory import runner as IFR
from scripts.platformkit.interaction_factory import replicate_survivors as RS
from scripts.platformkit.interaction_factory import replicate_batch2b as B2B
from scripts.platformkit.interaction_factory import replicate_nba_2026 as RN26

STATE_KEY = "M21_replication_cadence"
MAX_PER_TICK = 5

# template_id -> the existing worker's replicate(ledger_path=...) for that
# family. Both workers accept `ledger_path` as an optional kwarg with their
# own default for everything else (season / mlb_year) -- this job never
# overrides those, same corpora a human CLI run would pick.
FAMILY_WORKERS: Dict[str, Callable[..., List[Dict[str, Any]]]] = {
    RS.TEMPLATE_ID: RS.replicate,
    "mlb_pa_attr_x_archetype": B2B.replicate,
    "tennis_match_asof_self_cross": B2B.replicate,
    RN26.TEMPLATE_ID: RN26.replicate,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _latest_by_candidate(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        cid = row.get("candidate_id")
        if not cid:
            continue
        if cid not in latest or str(row.get("computed_at", "")) > str(latest[cid].get("computed_at", "")):
            latest[cid] = row
    return latest


def pending_survivors(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """template_id -> latest-verdict SURVIVES_PREREG_PROVISIONAL rows with no
    replication row yet (no ledger row anywhere carries
    replication_of == this candidate_id)."""
    latest = _latest_by_candidate(rows)
    already_replicated = {r.get("replication_of") for r in rows if r.get("replication_of")}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for cid, row in latest.items():
        if row.get("verdict") != IFR.SURVIVES or cid in already_replicated:
            continue
        out.setdefault(str(row.get("template_id")), []).append(row)
    return out


def run_replication_cadence(watermarks: Dict[str, Any], *,
                            ledger_path: Optional[Path] = None,
                            family_workers: Optional[Dict[str, Callable[..., Any]]] = None,
                            max_per_tick: int = MAX_PER_TICK,
                            load_ledger_fn: Optional[Callable[[Path], List[Dict[str, Any]]]] = None
                            ) -> Dict[str, Any]:
    """One M21 tick. Never raises out (one family's worker error is isolated
    and simply withholds the watermark stamp -- maintenance_templates.run_all
    also isolates this job's own top-level raise, same table convention as
    every other job). Safe to call with zero pending survivors (clean no-op)."""
    lp = ledger_path or IFR.LEDGER_PATH
    workers = family_workers if family_workers is not None else FAMILY_WORKERS
    rows = (load_ledger_fn or IFR._load_ledger)(lp)  # noqa: SLF001 -- same loader every replicate_* worker uses
    pending = pending_survivors(rows)

    families: Dict[str, Any] = {}
    no_worker: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    ran = 0
    budget = int(max_per_tick)
    called: Dict[int, str] = {}  # id(worker) -> first family it ran under this tick
    for tid in sorted(pending):
        cand_rows = pending[tid]
        worker = workers.get(tid)
        if worker is None:
            no_worker[tid] = len(cand_rows)
            families[tid] = {"status": "NO_WORKER_REGISTERED", "n_pending": len(cand_rows),
                             "candidate_ids": [r["candidate_id"] for r in cand_rows]}
            continue
        if id(worker) in called:
            # a worker serving several family keys (e.g. batch2b) processes its
            # whole template set in one call -- calling it again would re-append
            # the sibling family's rows (judge NIT on 0b7e5f9e: 07-13 double-fire)
            families[tid] = {"status": "ran_shared", "n_pending": len(cand_rows),
                             "via_family": called[id(worker)]}
            continue
        if len(cand_rows) > budget:
            families[tid] = {"status": "deferred_bound", "n_pending": len(cand_rows),
                             "budget_left": budget}
            continue
        try:
            appended = worker(ledger_path=lp)
            called[id(worker)] = tid
            families[tid] = {"status": "ran", "n_pending": len(cand_rows),
                             "n_appended": len(appended)}
            budget -= len(cand_rows)
            ran += 1
        except Exception as exc:  # noqa: BLE001 -- one family's worker failing must not block siblings
            errors[tid] = str(exc)[:200]
            families[tid] = {"status": "error", "n_pending": len(cand_rows), "error": str(exc)[:200]}

    total_pending = sum(len(v) for v in pending.values())
    success = not errors  # PARTIAL/FAILED (any family raised) never stamps -- retry next tick
    if success:
        watermarks[STATE_KEY] = {"last_run_ts": _now_iso(), "total_pending_at_run": total_pending,
                                 "families_ran": ran}
    return {"status": "ran", "total_pending": total_pending, "families": families,
           "no_worker_registered": no_worker, "families_ran": ran,
           "watermark_stamped": success}


def dry_run(*, ledger_path: Optional[Path] = None,
           family_workers: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """List-only: which survivors WOULD be replicated this tick. No writes,
    no worker calls."""
    lp = ledger_path or IFR.LEDGER_PATH
    workers = family_workers if family_workers is not None else FAMILY_WORKERS
    rows = IFR._load_ledger(lp)  # noqa: SLF001 -- same loader every replicate_* worker uses
    pending = pending_survivors(rows)
    return {tid: {"n_pending": len(cand_rows), "has_worker": tid in workers,
                 "candidate_ids": [r["candidate_id"] for r in cand_rows]}
           for tid, cand_rows in sorted(pending.items())}


def main() -> int:  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(description="M21 auto-replication cadence job.")
    p.add_argument("--dry-run", action="store_true", help="List pending survivors only, no writes.")
    a = p.parse_args()
    if a.dry_run:
        pending = dry_run()
        if not pending:
            print("M21 replication_cadence: no pending survivors")
            return 0
        for tid, info in pending.items():
            print("%-32s pending=%d worker=%s" % (tid, info["n_pending"], info["has_worker"]))
            for cid in info["candidate_ids"]:
                print("  - %s" % cid)
        return 0
    out = run_replication_cadence({})
    print(json.dumps({k: out[k] for k in ("status", "total_pending", "families_ran", "watermark_stamped")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_replication_cadence", "pending_survivors", "dry_run", "main",
          "FAMILY_WORKERS", "STATE_KEY", "MAX_PER_TICK"]
