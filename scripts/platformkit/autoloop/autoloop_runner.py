"""scripts.platformkit.autoloop.autoloop_runner -- the AUTOLOOP cycle driver.

AUTOLOOP_SPEC_2026-07-06.md sec 2 (+ R-C/R-D/R-E rulings). Composes EXISTING
harnesses under the sha-pinned standing_prereg registry; no new math, no new
gate. Zero-LLM by construction (no anthropic/openai import anywhere).

One tick = run_cycle(): per verified template, DUE via standing_prereg.
template_content_sha, run the pinned kind's harness restricted to the
universe, append K-ledger rows, refresh scoreboards, emit an honesty-linted
report + human-queue rows. Never raises/promotes/flips a flag/writes
data/registry/pushes.

CLI: python -m scripts.platformkit.autoloop.autoloop_runner [--once|--interval N]
"""
from __future__ import annotations

import json
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.autoloop import execution_cadence_job as ECJ
from scripts.platformkit.autoloop import maintenance_templates as MT
from scripts.platformkit.autoloop import standing_prereg as SP
from scripts.platformkit.io_atomic import append_jsonl_atomic, write_json_atomic

_REPO = Path(__file__).resolve().parents[3]
COMPONENT = "m38_autoloop"
DEFAULT_INTERVAL_SEC = 86400.0

REPORT_PATH = _REPO / "data" / "frontend" / "ops" / "autoloop_report.json"
CYCLE_HISTORY_PATH = _REPO / "data" / "frontend" / "ops" / "autoloop_cycle_history.jsonl"
HUMAN_QUEUE_PATH = _REPO / "data" / "frontend" / "ops" / "autoloop_human_queue.jsonl"
HEARTBEAT_PATH = _REPO / "data" / "cache" / "daemon_heartbeats" / "m38_autoloop.txt"
STOP_FLAG_PATH = _REPO / ".bot_state" / "live_status.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def should_stop_default() -> bool:
    """READ .bot_state/live_status.json stop_requested. Fail-SAFE: an unreadable
    flag halts (never runs wild) -- spec sec 5 STOP DISCIPLINE. NEVER runs
    stop_bot.py (that REQUESTS a stop, it does not read one)."""
    try:
        if not STOP_FLAG_PATH.exists():
            return False  # no flag ever written yet -- not a stop request
        doc = json.loads(STOP_FLAG_PATH.read_text(encoding="utf-8"))
        return bool(doc.get("stop_requested", False))
    except Exception:  # noqa: BLE001 -- unreadable flag -> fail-safe halt
        return True

# governance.honesty_linter is the single in-process object linter; reused
# verbatim (spec sec 2f/5), never reimplemented here.
def _honesty_clean(obj: Any) -> bool:
    try:
        from governance.honesty_linter import lint_obj
        return bool(lint_obj(obj).get("clean", False))
    except Exception:  # noqa: BLE001 -- linter must never crash the cycle; fail-closed (not written)
        return False

def _queue(row: Dict[str, Any], path: Optional[Path]) -> int:
    """Honesty-lint + append one human-queue row; 1 if appended else 0 (a
    tripped row is fail-closed dropped, never written)."""
    if not _honesty_clean(row):
        return 0
    append_jsonl_atomic(path or HUMAN_QUEUE_PATH, row)
    return 1


# Per-kind cycle actions: each a thin, injectable wrapper over an EXISTING
# harness. None reimplement a bar; all isolate their own exceptions.
def _run_reclaim_fit(template: SP.Template, eligible: List[str]) -> Dict[str, Any]:
    """Restrict asof_reclaim_sweep.registry() to the pinned+eligible universe,
    reuse the sweep's OWN normalize+ledger path (byte-identical to a full sweep)."""
    from scripts.platformkit.ceiling import asof_reclaim_sweep as ARS

    fits_run = rejected = ship_review_queued = 0
    human_rows: List[Dict[str, Any]] = []
    max_n = template.max_candidates_per_cycle
    for spec in ARS.registry():
        if spec.sport != template.sport or spec.signal not in eligible or fits_run >= max_n:
            continue
        try:
            row = ARS._normalize(spec, spec.fn())  # noqa: SLF001 -- reuse the sweep's own contract
        except Exception as exc:  # noqa: BLE001 -- isolate one candidate's failure
            row = {"sport": spec.sport, "signal": spec.signal, "verdict": "ERROR",
                   "error": str(exc)[:200]}
        fits_run += 1
        if row.get("verdict") != "ERROR":
            ARS._log_reject_ledger(row)  # noqa: SLF001 -- same ledger path a full sweep uses
        if row.get("verdict") == "REJECT":
            rejected += 1
        elif row.get("verdict") in ("SHIP", "SHIP_REVIEW"):
            ship_review_queued += 1
            human_rows.append({"kind": "SHIP_CANDIDATE", "template_id": template.template_id, "row": row})
    return {"fits_run": fits_run, "rejected": rejected,
           "ship_review_queued": ship_review_queued, "human_rows": human_rows,
           "new_deduped_k": fits_run}

def _run_interaction_batch(tpl: SP.Template) -> Dict[str, Any]:
    """Run ONE interaction-factory batch for the factory template this autoloop
    template points at. Reuses the factory runner's OWN dedupe + cluster-robust
    fit + cumulative-K ledger (byte-identical to a manual `runner.run_batch`);
    only REAL tests (SURVIVES|NULL) spend K, NOT_TESTABLE spends none. A SURVIVOR
    (provisional) becomes a human_queue row for the replication pass."""
    from scripts.platformkit.interaction_factory import runner as IFR

    factory_tpl = tpl.body.get("factory_template")
    k = min(20, tpl.max_candidates_per_cycle or 20)
    if not factory_tpl:
        return {"fits_run": 0, "rejected": 0, "ship_review_queued": 0,
                "human_rows": [], "new_deduped_k": 0}
    rows = IFR.run_batch(factory_tpl, k)
    real = [r for r in rows if r.get("verdict") in (IFR.SURVIVES, IFR.NULL)]
    survivors = [r for r in rows if r.get("verdict") == IFR.SURVIVES]
    human_rows = [{
        "kind": "INTERACTION_SURVIVOR", "template_id": tpl.template_id,
        "factory_template": factory_tpl, "candidate_id": s.get("candidate_id"),
        "effect": s.get("effect"), "p": s.get("p"), "n": s.get("n"),
        "cum_K": s.get("cum_K"), "note": s.get("note", ""), "edge_claimed": False,
    } for s in survivors]
    return {"fits_run": len(real), "rejected": sum(1 for r in real if r.get("verdict") == IFR.NULL),
            "ship_review_queued": len(survivors), "human_rows": human_rows,
            "new_deduped_k": len(real)}


def _refresh_scoreboards() -> None:
    """freshness_sla.write_status + edge_greenlight.main -- the same refreshers
    a human wake runs, unattended (spec sec 2e). Best-effort; never raises."""
    try:
        from scripts.platformkit.autonomy import freshness_sla as FS
        FS.write_status(FS.check_all(list(FS.TABLE.keys())))
    except Exception:  # noqa: BLE001
        pass
    try:
        from scripts.platformkit.econ import edge_greenlight as EG
        EG.main([])
    except Exception:  # noqa: BLE001
        pass


def _append_cycle_history(report: Dict[str, Any], execution: Dict[str, Any],
                          history_path: Optional[Path] = None) -> None:
    """Append one compact history line for THIS cycle -- report.json is
    overwritten every cycle (write_json_atomic), so per-cycle evidence
    otherwise vanishes. All fields pulled from objects already in scope
    (never recomputed); missing -> null. Append failure must never fail
    the cycle."""
    per_template = report.get("per_template", [])
    dryrun = ((execution.get("execution_stages") or {}).get("dryrun") or {})
    reconcile = ((execution.get("execution_stages") or {}).get("reconcile") or {})
    row = {
        "finished_at": report.get("ts"),
        "wall_clock_s": report.get("wall_clock_sec"),
        "fits_run": sum(t.get("fits_run", 0) for t in per_template),
        "rejected": sum(t.get("rejected", 0) for t in per_template),
        "ship_review_queued": sum(t.get("ship_review_queued", 0) for t in per_template),
        "skipped_no_new_data": sum(1 for t in per_template if t.get("status") == "skipped_no_new_data"),
        "dryrun": {
            "n_intents": dryrun.get("n_intents"),
            "n_fills": reconcile.get("n_fills"),
            "n_unparseable": dryrun.get("n_unparseable"),
        },
        "reconcile_verdict": (reconcile.get("vs_later_tape") or {}).get("verdict"),
        "cum_k_delta": None,  # ponytail: not cheaply available in this scope; add if a cheap source shows up
    }
    try:
        append_jsonl_atomic(history_path or CYCLE_HISTORY_PATH, row)
    except Exception as exc:  # noqa: BLE001 -- append is best-effort, never fails the cycle
        print("%s | cycle_history append FAILED %s" % (COMPONENT, str(exc)[:160]), flush=True)


# The cycle
def _base_row(tpl: SP.Template, k_ledger_dir: Optional[Path]) -> Dict[str, Any]:
    return {
        "template_id": tpl.template_id, "kind": tpl.kind, "sport": tpl.sport, "status": "ok",
        "fits_run": 0, "rejected": 0, "ship_review_queued": 0, "illegal_unpinned": 0,
        "blocked_closed_class": 0, "claims_regenerated": 0, "claims_verified": 0,
        "claims_mismatch": 0, "n_excluded_below_floor": 0, "prereg_tamper": False,
        "cum_k": SP.k_ledger_cum_k(tpl.sport, tpl.template_id, base_dir=k_ledger_dir),
    }


def _process_template(tpl: SP.Template, watermarks: Dict[str, Any], *, queue_path,
                      k_ledger_dir, reclaim_fit, claims_regen, corpus_sha_fn,
                      interaction_fn=None) -> Dict[str, Any]:
    """One template's tick: DUE check -> blocklist -> pinned-kind harness ->
    K-ledger append. Returns {row, human_queue_appended}. Isolated per-template
    (a raise here is caught by the caller, mirrors selfimprove_daemon)."""
    row = _base_row(tpl, k_ledger_dir)
    hq = 0
    if not tpl.ok:
        row["status"], row["prereg_tamper"] = tpl.reason, (tpl.reason == "PREREG_TAMPER")
        if tpl.reason == "PREREG_TAMPER":
            hq += _queue({"kind": "ANOMALY", "ts": _now_iso(), "template_id": tpl.template_id,
                         "reason": "PREREG_TAMPER"}, queue_path)
        return {"row": row, "human_queue_appended": hq}

    blocked = SP.derive_blocklist(tpl)
    row["blocked_closed_class"] = len(blocked)
    eligible = [m for m in tpl.universe if m not in blocked]

    corpus_sha = corpus_sha_fn(tpl)
    if corpus_sha is None:
        row["status"] = "ANOMALY"
        hq += _queue({"kind": "ANOMALY", "ts": _now_iso(), "template_id": tpl.template_id,
                     "reason": "corpus_unreadable_or_stale"}, queue_path)
        return {"row": row, "human_queue_appended": hq}

    if not SP.is_due(tpl.template_id, corpus_sha, watermarks):
        row["status"] = "skipped_no_new_data"
        return {"row": row, "human_queue_appended": hq}

    if not eligible:
        row["status"] = "TEMPLATE_EXHAUSTED"
        hq += _queue({"kind": "TEMPLATE_EXHAUSTED", "ts": _now_iso(),
                     "template_id": tpl.template_id, "sport": tpl.sport}, queue_path)
        watermarks[tpl.template_id] = {"corpus_sha": corpus_sha, "last_run_ts": _now_iso()}
        return {"row": row, "human_queue_appended": hq}

    new_k = 0
    if tpl.kind == "reclaim_fit":
        result = reclaim_fit(tpl, eligible)
        row["fits_run"] = result.get("fits_run", 0)
        row["rejected"] = result.get("rejected", 0)
        row["ship_review_queued"] = result.get("ship_review_queued", 0)
        for hr in result.get("human_rows", []):
            hq += _queue(hr, queue_path)
        new_k = int(result.get("new_deduped_k", 0))
    elif tpl.kind == "claims_regen":
        result = claims_regen(tpl)
        row["claims_regenerated"] = result.get("claims_regenerated", 0)
        row["claims_verified"] = result.get("claims_verified", 0)
        row["claims_mismatch"] = result.get("claims_mismatch", 0)
        row["n_excluded_below_floor"] = result.get("n_excluded_below_floor", 0)
        if (result.get("skipped_family") or []) and result.get("claims_regenerated", 0) == 0:
            row["status"] = "SKIPPED_FAMILY"
    elif tpl.kind == "interaction_batch":
        result = (interaction_fn or _run_interaction_batch)(tpl)
        row["fits_run"] = result.get("fits_run", 0)
        row["rejected"] = result.get("rejected", 0)
        row["ship_review_queued"] = result.get("ship_review_queued", 0)
        for hr in result.get("human_rows", []):
            hq += _queue(hr, queue_path)
        new_k = int(result.get("new_deduped_k", 0))
    else:
        row["status"], row["illegal_unpinned"] = "ILLEGAL_UNPINNED", 1

    from scripts.platformkit.combo.fwer_budget import cumulative_k
    prior_cum = SP.k_ledger_cum_k(tpl.sport, tpl.template_id, base_dir=k_ledger_dir)
    new_cum = cumulative_k(prior_cum, new_k)
    SP.k_ledger_append(tpl.sport, tpl.template_id, _now_iso(), new_k, new_cum, base_dir=k_ledger_dir)
    row["cum_k"] = new_cum
    watermarks[tpl.template_id] = {"corpus_sha": corpus_sha, "last_run_ts": _now_iso()}
    return {"row": row, "human_queue_appended": hq}


def run_cycle(*, templates_dir: Optional[Path] = None,
             reclaim_fit_fn: Optional[Callable[[SP.Template, List[str]], Dict[str, Any]]] = None,
             claims_regen_fn: Optional[Callable[[SP.Template], Dict[str, Any]]] = None,
             interaction_fn: Optional[Callable[[SP.Template], Dict[str, Any]]] = None,
             corpus_sha_fn: Optional[Callable[[SP.Template], Optional[str]]] = None,
             refresh_fn: Optional[Callable[[], None]] = None,
             maintenance_fn: Optional[Callable[..., Dict[str, Any]]] = None,
             execution_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
             report_path: Optional[Path] = None, queue_path: Optional[Path] = None,
             heartbeat_path: Optional[Path] = None, k_ledger_dir: Optional[Path] = None,
             watermark_path: Optional[Path] = None, clock: Optional[Callable[[], float]] = None,
             history_path: Optional[Path] = None) -> Dict[str, Any]:
    """One idempotent tick. Never raises. Returns the cycle report dict (also
    written atomically, honesty-linted first -- a tripped report is NOT written)."""
    t0 = (clock or _time.time)()
    watermarks = SP.load_watermarks(path=watermark_path)
    per_template: List[Dict[str, Any]] = []
    human_queue_appended = 0

    for tpl in SP.load_all_templates(templates_dir):
        try:
            out = _process_template(
                tpl, watermarks, queue_path=queue_path, k_ledger_dir=k_ledger_dir,
                reclaim_fit=reclaim_fit_fn or _run_reclaim_fit,
                claims_regen=claims_regen_fn or SP.run_claims_regen,
                interaction_fn=interaction_fn or _run_interaction_batch,
                corpus_sha_fn=corpus_sha_fn or SP.template_content_sha)
            per_template.append(out["row"])
            human_queue_appended += out["human_queue_appended"]
        except Exception as exc:  # noqa: BLE001 -- per-template isolation (spec sec 2)
            row = _base_row(tpl, k_ledger_dir)
            row["status"], row["error"] = "template_error", str(exc)[:200]
            per_template.append(row)

    maintenance = (maintenance_fn or MT.run_all)(watermarks, queue_fn=lambda row: _queue(row, queue_path))
    execution = (execution_fn or ECJ.run_all)(watermarks)  # M13/M14: composer->dryrun->reconcile + weekly timing refresh
    SP.save_watermarks(watermarks, path=watermark_path)
    (refresh_fn or _refresh_scoreboards)()

    report = {
        "ts": _now_iso(), "component": COMPONENT,
        "wall_clock_sec": round((clock or _time.time)() - t0, 3),
        "per_template": per_template, "human_queue_appended": human_queue_appended,
        "maintenance": maintenance, "execution": execution,
    }
    if _honesty_clean(report):
        write_json_atomic(report_path or REPORT_PATH, report)
    else:
        report["_write_suppressed"] = "honesty_lint_tripped"

    _append_cycle_history(report, execution, history_path=history_path)

    try:
        hb = heartbeat_path or HEARTBEAT_PATH
        hb.parent.mkdir(parents=True, exist_ok=True)
        hb.write_text(_now_iso(), encoding="ascii")
    except Exception:  # noqa: BLE001 -- heartbeat write is best-effort
        pass
    return report


def serve_forever(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
                  max_ticks: Optional[int] = None,
                  should_stop: Optional[Callable[[], bool]] = None,
                  sleep: Optional[Callable[[float], None]] = None, **cycle_kwargs: Any) -> int:
    """Run run_cycle() forever (or max_ticks). Reads the stop flag each tick
    BEFORE starting a new one; finishes an in-flight cycle's atomic write, then
    exits (spec sec 5 STOP DISCIPLINE). Never raises out; returns ticks run."""
    _stop = should_stop if should_stop is not None else should_stop_default
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    while True:
        try:
            if _stop():
                break
        except Exception:  # noqa: BLE001 -- unreadable stop check -> fail-safe halt
            break
        try:
            report = run_cycle(**cycle_kwargs)
            n_tpl = len(report.get("per_template", []))
            print("%s | tick=%d templates=%d human_queue+=%d" %
                 (COMPONENT, ticks, n_tpl, report.get("human_queue_appended", 0)), flush=True)
        except Exception as exc:  # noqa: BLE001 -- one bad cycle must not kill the loop
            print("%s | tick=%d ERROR %s" % (COMPONENT, ticks, str(exc)[:160]), flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def main() -> int:  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(description="AUTOLOOP -- CLAUDE-FREE daily cycle driver.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    p.add_argument("--once", action="store_true", help="Run a single cycle and exit.")
    a = p.parse_args()
    print("%s | started interval=%ss once=%s" % (COMPONENT, a.interval, a.once), flush=True)
    if a.once:
        report = run_cycle()
        print(json.dumps({k: report[k] for k in ("ts", "wall_clock_sec", "human_queue_appended")}))
        return 0
    serve_forever(interval_sec=a.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_cycle", "serve_forever", "should_stop_default", "main",
          "REPORT_PATH", "HUMAN_QUEUE_PATH", "HEARTBEAT_PATH", "STOP_FLAG_PATH",
          "CYCLE_HISTORY_PATH"]
