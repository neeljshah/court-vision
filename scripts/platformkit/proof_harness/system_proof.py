"""scripts.platformkit.proof_harness.system_proof -- ONE-COMMAND system liveness
harness (LANE E3, 2026-07-11): the demo/sellability artifact. Composes EXISTING
sentinels/gates, no new math, no new gate:

  [fleet]       ops_sentinel.heartbeat_coverage (ProcSpec heartbeat freshness).
  [gates]       eval_gate/run_all.py subprocess (its 38-check scoreboard, verbatim).
  [data]        census_drift + newest-artifact age, one key store per sport (8).
  [predictions] one live predict_matchup.py smoke per core sport (subprocess,
                the resolver-registry path -- prediction_winprob is CLI-only).
  [ledgers]     row count + last-append age for the append-only ledgers.
  [autonomy]    m38 autoloop job registry (regex-scanned from maintenance_
                templates.run_all(), the canonical list) vs the last real
                autoloop_report.json. A job absent from the report while the
                m38 heartbeat is otherwise fresh means the daemon is alive on
                OLDER code -- PENDING-RESTART, distinct from a real FAIL.
  [integrity]   ops_sentinel.guard_integrity (invariant-surface tamper-evidence).

Every section is try/excepted in isolation -- a down section reports RED, never
crashes the harness. Output: one ASCII table on stdout + system_proof.json.

CLI: python -m scripts.platformkit.proof_harness.system_proof
Test: python -m pytest scripts/platformkit/proof_harness/test_system_proof.py -q
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.io_atomic import write_json_atomic

_REPO = Path(__file__).resolve().parents[3]
OUT_PATH = _REPO / "data" / "frontend" / "ops" / "system_proof.json"

GREEN, RED, NA, PENDING = "GREEN", "RED", "NA", "PENDING-RESTART"


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- missing/bad file -> {} (never treated as green)
        return {}


# [fleet] -- reuse ops_sentinel.heartbeat_coverage verbatim
def section_fleet() -> Dict[str, Any]:
    from scripts.platformkit.ops_sentinel import heartbeat_coverage as hc
    rows = hc.check_all()
    red = [r for r in rows if r.get("status") == RED]
    return {"rows": rows, "n_rows": len(rows), "n_red": len(red),
            "overall": RED if red else GREEN,
            "summary": (f"{len(red)}/{len(rows)} heartbeats RED: "
                        f"{', '.join(r['name'] for r in red)}") if red
                       else f"{len(rows)} ProcSpecs, all fresh/NA"}


# [gates] -- eval_gate/run_all.py's own 38-check scoreboard, subprocess (it
# expects cwd=its own dir -- flat imports, not a package).
def section_gates(python_exe: Optional[str] = None) -> Dict[str, Any]:
    exe = python_exe or sys.executable
    gate_dir = _REPO / "scripts" / "platformkit" / "eval_gate"
    try:
        proc = subprocess.run([exe, "run_all.py"], cwd=str(gate_dir),
                               capture_output=True, text=True, timeout=120)
        m = re.search(r"TOTAL\s+(\d+)/(\d+)", proc.stdout)
        passed, total = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        ok = proc.returncode == 0 and total > 0 and passed == total
        return {"passed": passed, "total": total, "returncode": proc.returncode,
                "overall": GREEN if ok else RED,
                "summary": f"{passed}/{total} checks green (exit {proc.returncode})"}
    except Exception as exc:  # noqa: BLE001
        return {"overall": RED, "error": str(exc)[:200], "summary": f"harness error: {exc}"}


# [data] -- census_drift.run_check() + newest-artifact age, one store/sport
_KEY_SPORTS = ("nba", "mlb", "soccer", "soccer_intl", "tennis", "wnba", "npb", "kbo")


def section_data() -> Dict[str, Any]:
    from scripts.platformkit.census_drift import CENSUS_PATH, _primary_token, _to_glob, run_check
    try:
        drift = run_check()
    except Exception as exc:  # noqa: BLE001
        drift = {"error": str(exc)[:200]}
    census = _load_json(_REPO / CENSUS_PATH)
    now = time.time()
    stores: List[Dict[str, Any]] = []
    for sport in _KEY_SPORTS:
        sources = census.get("sports", {}).get(sport, {}).get("sources", {})
        if not sources:
            stores.append({"sport": sport, "status": NA, "reason": "no census entry"})
            continue
        name, meta = next(iter(sources.items()))
        pattern = _to_glob(_primary_token(str(meta.get("path", ""))))
        matches = glob.glob(str(_REPO / pattern))
        if not matches:
            stores.append({"sport": sport, "store": name, "status": RED, "reason": "no artifact matched"})
            continue
        age_h = round((now - max(os.path.getmtime(m) for m in matches)) / 3600.0, 1)
        stores.append({"sport": sport, "store": name, "n_files": len(matches),
                        "age_hours": age_h, "status": GREEN})
    red = [s for s in stores if s.get("status") == RED]
    n_drift = drift.get("n_drift", 0) if isinstance(drift, dict) else 0
    return {"census_drift": drift, "key_stores": stores,
            "overall": RED if red else GREEN,
            "summary": (f"census: {drift.get('n_ok','?')} ok/{n_drift} drift/"
                        f"{drift.get('n_missing','?')} missing; "
                        f"{len(stores) - len(red)}/{len(stores)} key stores fresh")}


# [predictions] -- one live predict_matchup smoke per core sport (subprocess,
# the resolver-registry path -- prediction_winprob is CLI-only by design).
_SMOKE = (("nba", "BOS", "LAL"), ("mlb", "NYY", "BOS"),
          ("soccer", "Arsenal", "Chelsea"), ("tennis", "Djokovic", "Alcaraz"))


def section_predictions(python_exe: Optional[str] = None) -> Dict[str, Any]:
    exe = python_exe or sys.executable
    rows: List[Dict[str, Any]] = []
    for sport, home, away in _SMOKE:
        row: Dict[str, Any] = {"sport": sport, "home": home, "away": away}
        cmd = [exe, "-m", "scripts.platformkit.predict_matchup", "--sport", sport,
               "--home", home, "--away", away, "--no-banner", "--json"]
        try:
            proc = subprocess.run(cmd, cwd=str(_REPO), capture_output=True,
                                   text=True, timeout=60)
            doc: Dict[str, Any] = {}
            try:
                doc = json.loads(proc.stdout) if proc.stdout.strip() else {}
            except Exception:  # noqa: BLE001 -- unparsable stdout -> RED, never a crash
                doc = {}
            ok = proc.returncode == 0 and bool(doc)
            row.update(status=GREEN if ok else RED, returncode=proc.returncode,
                       has_pregame=isinstance(doc, dict) and "pregame" in doc)
        except Exception as exc:  # noqa: BLE001
            row.update(status=RED, error=str(exc)[:200])
        rows.append(row)
    red = [r for r in rows if r.get("status") == RED]
    return {"rows": rows, "overall": RED if red else GREEN,
            "summary": f"{len(rows) - len(red)}/{len(rows)} sport smokes returned a pregame prediction"}


# [ledgers] -- row count + last-append age. Missing file -> NA (a fresh clone
# has no data/, gitignored), never RED.
_LEDGERS: Dict[str, Path] = {
    "clv_ledger": _REPO / "data" / "frontend" / "clv_ledger.jsonl",
    "reject_ledger": _REPO / "data" / "frontend" / "reject_ledger.jsonl",
    "paper_predictions": _REPO / "data" / "frontend" / "paper_predictions.jsonl",
    "improve_ledger": _REPO / "data" / "frontend" / "improve_ledger.jsonl",
    "autoloop_human_queue": _REPO / "data" / "frontend" / "ops" / "autoloop_human_queue.jsonl",
    "validation_ledger_nba": _REPO / "domains" / "basketball_nba" / "knowledge" / "validation_ledger.jsonl",
    "validation_ledger_mlb": _REPO / "domains" / "mlb" / "knowledge" / "validation_ledger.jsonl",
    "validation_ledger_soccer": _REPO / "domains" / "soccer" / "knowledge" / "validation_ledger.jsonl",
    "validation_ledger_tennis": _REPO / "domains" / "tennis" / "knowledge" / "validation_ledger.jsonl",
}


def section_ledgers(ledgers: Optional[Dict[str, Path]] = None) -> Dict[str, Any]:
    now = time.time()
    rows: List[Dict[str, Any]] = []
    for name, path in (ledgers or _LEDGERS).items():
        row: Dict[str, Any] = {"name": name}
        if not path.exists():
            row.update(status=NA, n_rows=0, reason="not present in this clone")
        else:
            try:
                with open(path, encoding="utf-8") as fh:
                    n = sum(1 for line in fh if line.strip())
                row.update(status=GREEN, n_rows=n,
                           age_hours=round((now - path.stat().st_mtime) / 3600.0, 1))
            except Exception as exc:  # noqa: BLE001
                row.update(status=RED, error=str(exc)[:200])
        rows.append(row)
    red = [r for r in rows if r.get("status") == RED]
    n_present = sum(1 for r in rows if r.get("status") != NA)
    return {"rows": rows, "overall": RED if red else GREEN,
            "summary": f"{n_present}/{len(rows)} ledgers present, 0 read errors" if not red
                       else f"{len(red)} ledger read errors"}


# [autonomy] -- m38 autoloop job registry vs the last real cycle report.
_MAINT_SRC = _REPO / "scripts" / "platformkit" / "autoloop" / "maintenance_templates.py"
_JOB_KEY_RE = re.compile(r'out\["(\w+)"\]\s*=')
_AUTOLOOP_REPORT = _REPO / "data" / "frontend" / "ops" / "autoloop_report.json"
_AUTOLOOP_HB = _REPO / "data" / "cache" / "daemon_heartbeats" / "m38_autoloop.txt"


def _canonical_job_names(src: Optional[Path] = None) -> List[str]:
    """The job keys maintenance_templates.run_all() actually assigns -- scanned
    live from source so this list can never drift from the real registry."""
    try:
        text = (src or _MAINT_SRC).read_text(encoding="utf-8")
        return sorted(set(_JOB_KEY_RE.findall(text)))
    except Exception:  # noqa: BLE001
        return []


def section_autonomy() -> Dict[str, Any]:
    report = _load_json(_AUTOLOOP_REPORT)
    maint = report.get("maintenance", {}) if isinstance(report, dict) else {}
    hb_age_h = (round((time.time() - _AUTOLOOP_HB.stat().st_mtime) / 3600.0, 2)
                if _AUTOLOOP_HB.exists() else None)
    from scripts.platformkit.autoloop.autoloop_runner import DEFAULT_INTERVAL_SEC
    daemon_alive = hb_age_h is not None and hb_age_h * 3600.0 < 1.5 * DEFAULT_INTERVAL_SEC
    rows: List[Dict[str, Any]] = []
    for job in _canonical_job_names():
        if job in maint:
            v = maint[job]
            errored = isinstance(v, dict) and v.get("status") == "error"
            rows.append({"job": job, "status": RED if errored else GREEN,
                         "reason": v.get("error") if errored else None})
        elif daemon_alive:
            rows.append({"job": job, "status": PENDING,
                         "reason": "not in last cycle report; daemon heartbeat is fresh on OLDER "
                                   "code -- will appear after the next supervisor restart+cycle"})
        else:
            rows.append({"job": job, "status": RED,
                         "reason": "absent from last report AND daemon heartbeat stale"})
    red = [r for r in rows if r["status"] == RED]
    pending = [r for r in rows if r["status"] == PENDING]
    overall = RED if red else (PENDING if pending else GREEN)
    return {"rows": rows, "heartbeat_age_hours": hb_age_h,
            "report_ts": report.get("ts") if isinstance(report, dict) else None,
            "overall": overall,
            "summary": (f"{len(red)} job(s) truly failing" if red else
                        f"{len(pending)} job(s) pending restart" if pending else
                        f"{len(rows)} jobs all present in last cycle")}


# [integrity] -- reuse ops_sentinel.guard_integrity verbatim
def section_integrity() -> Dict[str, Any]:
    from scripts.platformkit.ops_sentinel import guard_integrity as gi
    try:
        rows = gi.check_all()
    except Exception as exc:  # noqa: BLE001
        return {"overall": RED, "error": str(exc)[:200], "summary": f"harness error: {exc}"}
    red = [r for r in rows if r.get("status") == RED]
    return {"rows": rows, "overall": RED if red else GREEN,
            "summary": "guard hashes match baseline" if not red
                       else f"{len(red)} guarded file(s) mismatched/missing"}


SECTIONS: "Dict[str, Callable[[], Dict[str, Any]]]" = {
    "fleet": section_fleet, "gates": section_gates, "data": section_data,
    "predictions": section_predictions, "ledgers": section_ledgers,
    "autonomy": section_autonomy, "integrity": section_integrity,
}


def run_all(section_fns: Optional[Dict[str, Callable[[], Dict[str, Any]]]] = None,
            *, now: Optional[float] = None) -> Dict[str, Any]:
    """Runs every section, each isolated -- a raise in one never sinks the rest.
    Never raises. Returns the full doc (also written atomically by main())."""
    fns = section_fns or SECTIONS
    ts = float(now) if now is not None else time.time()
    sections: Dict[str, Any] = {}
    for name, fn in fns.items():
        try:
            sections[name] = fn()
        except Exception as exc:  # noqa: BLE001 -- a down section is RED, never a crash
            sections[name] = {"overall": RED, "error": str(exc)[:200], "summary": f"section crashed: {exc}"}
    reds = [n for n, s in sections.items() if s.get("overall") == RED]
    pendings = [n for n, s in sections.items() if s.get("overall") == PENDING]
    overall = RED if reds else (PENDING if pendings else GREEN)
    return {"generated_at": ts, "component": "system_proof", "sections": sections,
            "overall": overall, "n_red_sections": len(reds), "n_pending_sections": len(pendings),
            "honest_note": ("one-command liveness harness -- composes existing sentinels/gates, "
                             "computes nothing new; PENDING-RESTART means the code is shipped but "
                             "the daemon hasn't been bounced to pick it up, distinct from a real FAIL")}


def render_table(doc: Dict[str, Any]) -> str:
    lines = ["SYSTEM PROOF -- one-command liveness harness", "=" * 78,
              f"{'SECTION':<13}{'STATUS':<18}SUMMARY", "-" * 78]
    for name, sec in doc.get("sections", {}).items():
        status = sec.get("overall", "?")
        lines.append(f"{name:<13}{status:<18}{sec.get('summary', '')}")
    lines.append("-" * 78)
    lines.append(f"OVERALL: {doc.get('overall')}  "
                 f"({doc.get('n_red_sections', 0)} RED section(s), "
                 f"{doc.get('n_pending_sections', 0)} PENDING-RESTART section(s))")
    return "\n".join(lines)


def main() -> int:
    doc = run_all()
    print(render_table(doc))
    write_json_atomic(OUT_PATH, doc, indent=2)
    return 1 if doc["overall"] == RED else 0


if __name__ == "__main__":
    sys.exit(main())
