"""scripts.platformkit.autonomy.post_restart_checks -- checks (a), (b), (c),
(f), (g) of LANE 4's post-`boot.ps1` verifier. Checks (d)/(e) (per-sport
capture-dir + shadow-field) live in post_restart_capture_checks.py -- split out
so both modules stay under the <=300 LOC rail (behavior-preserving split,
mirrors the http_wedge_reaper/_probe/_io split already used in this package).

See post_restart_verify.py's module docstring for the full check narrative.
Every external effect (HTTP probe, kalshi fetch, wall clock) is INJECTABLE so
tests never hit a real socket, kill a PID, or restart anything. Read-only: no
flag flip, no data/registry/ write, no PID touched, no restart authority.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_post_restart_verify.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[3]
_OPS = _REPO / "data" / "frontend" / "ops"
_HB = _REPO / "data" / "cache" / "daemon_heartbeats"

PASS = "PASS"
FAIL = "FAIL"
PENDING = "PENDING"

# The 4 NEW ProcSpecs this restart is expected to activate + their heartbeat +
# declared tick cadence (source: supervisor/stack_specs.py argv --interval).
NEW_PROCS: Dict[str, Dict[str, Any]] = {
    "m33_http_wedge_reaper": {
        "heartbeat": _HB / "m33_http_wedge_reaper.txt", "cadence_sec": 30.0},
    "m34_freshness_sla": {
        "heartbeat": _HB / "m34_freshness_sla.txt", "cadence_sec": 300.0},
    "m35_ingame_tail_multi": {
        "heartbeat": _HB / "m35_ingame_tail_multi.txt", "cadence_sec": 21600.0},
    "m36_ingame_grading_multi": {
        "heartbeat": _HB / "m36_ingame_grading_multi.txt", "cadence_sec": 900.0},
    # LANE 5 waves 11-13 addition: m37_ingame_enrichment (fotmob/gumbo/book-depth
    # pollers), 30s cadence (ingame_enrichment_runner.DEFAULT_INTERVAL_SEC).
    "m37_ingame_enrichment": {
        "heartbeat": _HB / "m37_ingame_enrichment.txt", "cadence_sec": 30.0},
}

# The 3 serving ports (m1_api_paper :8099, m1_api_boards :8098, m1_ui :3000) +
# the path each one actually answers 200 on. m1_api_paper's ReadinessSpec in
# stack_specs.py declares http_path="/health" (a FastAPI app with no root
# route 404s on "/"); the boards API + Next.js UI both serve 200 on "/".
SERVING_PORTS: Dict[str, Dict[str, Any]] = {
    "m1_api_paper": {"port": 8099, "path": "/health"},
    "m1_api_boards": {"port": 8098, "path": "/"},
    "m1_ui": {"port": 3000, "path": "/"},
}

# Kalshi pregame sports this lane checks n_events for (per the task brief).
KALSHI_PREGAME_SPORTS: List[str] = ["mlb", "wnba", "npb", "kbo"]


def row(name: str, status: str, evidence: str, **extra: Any) -> Dict[str, Any]:
    d: Dict[str, Any] = {"name": name, "status": status, "evidence": evidence}
    d.update(extra)
    return d


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="ascii", errors="replace"))
    except Exception:  # noqa: BLE001 -- unreadable/corrupt -> treated as absent
        return None


def restart_ts(now: float) -> float:
    """Best-effort restart timestamp: supervisor_status.json's own
    "started_at", falling back to the file's own mtime, falling back to *now*
    (a fresh/never-booted stack -- every freshness check below then reads
    PENDING, never a false FAIL). Never raises."""
    path = _OPS / "supervisor_status.json"
    doc = read_json(path)
    if isinstance(doc, dict):
        started = doc.get("started_at")
        if isinstance(started, (int, float)):
            return float(started)
    try:
        if path.exists():
            return float(path.stat().st_mtime)
    except Exception:  # noqa: BLE001
        pass
    return float(now)


def check_supervisor_status(now: float) -> Dict[str, Any]:
    """(a) all_ready + m33..m36 present in the proc-name set."""
    doc = read_json(_OPS / "supervisor_status.json")
    if doc is None:
        return row("supervisor_status", FAIL,
                    "data/frontend/ops/supervisor_status.json missing/unreadable")
    procs = doc.get("procs") if isinstance(doc, dict) else None
    names = {p.get("name") for p in procs} if isinstance(procs, list) else set()
    missing = sorted(n for n in NEW_PROCS if n not in names)
    all_ready = bool(doc.get("all_ready", False))
    if missing:
        return row("supervisor_status", FAIL,
                    "all_ready=%s but missing new procs: %s" % (all_ready, missing),
                    missing=missing, all_ready=all_ready, n_procs=len(names))
    if not all_ready:
        return row("supervisor_status", FAIL,
                    "all_ready=False (n_procs=%d, new procs all present)" % len(names),
                    all_ready=all_ready, n_procs=len(names))
    return row("supervisor_status", PASS,
                "all_ready=True, n_procs=%d, m33..m36 all present" % len(names),
                all_ready=True, n_procs=len(names))


def check_ports(*, http_probe_fn: Callable[..., Dict[str, Any]],
                timeout: float = 10.0) -> List[Dict[str, Any]]:
    """(b) HTTP 200 on each serving port. Read-only probe, no kill."""
    rows: List[Dict[str, Any]] = []
    for name, spec in SERVING_PORTS.items():
        port = int(spec["port"])
        path = str(spec.get("path", "/"))
        url = "http://127.0.0.1:%d%s" % (port, path)
        try:
            result = http_probe_fn(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 -- a probe crash reads FAIL, not a raise
            rows.append(row(name, FAIL, "probe raised %s" % type(exc).__name__, port=port))
            continue
        status = int(result.get("status", 0) or 0)
        timed_out = bool(result.get("timed_out", False))
        if status == 200:
            rows.append(row(name, PASS, "port %d -> HTTP 200" % port, port=port))
        elif timed_out:
            rows.append(row(name, FAIL, "port %d timed out (>%.0fs)" % (port, timeout),
                            port=port))
        else:
            rows.append(row(name, FAIL, "port %d -> HTTP %d (not 200)" % (port, status),
                            port=port))
    return rows


def check_new_procs(now: float, restart_at: float) -> List[Dict[str, Any]]:
    """(c) each new ProcSpec's heartbeat is fresher than restart_at."""
    rows: List[Dict[str, Any]] = []
    for name, spec in NEW_PROCS.items():
        hb_path: Path = spec["heartbeat"]
        cadence = float(spec["cadence_sec"])
        elapsed = now - restart_at
        if not hb_path.exists():
            if elapsed < cadence:
                rows.append(row(
                    name, PENDING,
                    "no heartbeat yet, only %.0fs since restart (< 1 tick=%.0fs)"
                    % (elapsed, cadence), cadence_sec=cadence))
            else:
                rows.append(row(
                    name, FAIL,
                    "heartbeat missing %.0fs after restart (>= 1 tick=%.0fs)"
                    % (elapsed, cadence), cadence_sec=cadence))
            continue
        try:
            mtime = hb_path.stat().st_mtime
        except Exception as exc:  # noqa: BLE001
            rows.append(row(name, FAIL, "heartbeat stat() raised %s" % type(exc).__name__))
            continue
        if mtime < restart_at:
            # Heartbeat predates the restart -- it's a stale artifact from a
            # prior manual run, not proof the supervisor's own tick fired yet.
            if elapsed < cadence:
                rows.append(row(
                    name, PENDING,
                    "heartbeat predates restart (mtime<restart_ts), only %.0fs "
                    "since restart (< 1 tick=%.0fs)" % (elapsed, cadence),
                    cadence_sec=cadence))
            else:
                rows.append(row(
                    name, FAIL,
                    "heartbeat still predates restart %.0fs later (>= 1 tick=%.0fs)"
                    % (elapsed, cadence), cadence_sec=cadence))
            continue
        age = now - mtime
        rows.append(row(name, PASS,
                        "heartbeat fresh: %.0fs old, %.0fs after restart"
                        % (age, mtime - restart_at), cadence_sec=cadence))
    return rows


def check_freshness_sla() -> Dict[str, Any]:
    """(f) freshness_sla.json's own overall field reads GREEN."""
    doc = read_json(_OPS / "freshness_sla.json")
    if doc is None:
        return row("freshness_sla_overall", PENDING,
                    "data/frontend/ops/freshness_sla.json missing (m34 has not "
                    "ticked yet post-restart)")
    overall = doc.get("overall")
    if overall == "GREEN":
        return row("freshness_sla_overall", PASS,
                    "overall=GREEN (n_daemons=%s n_red=%s n_na=%s)"
                    % (doc.get("n_daemons"), doc.get("n_red"), doc.get("n_na")))
    return row("freshness_sla_overall", FAIL,
                "overall=%s (n_red=%s)" % (overall, doc.get("n_red")))


def check_kalshi_pregame(*, fetch_fn: Callable[[str], Any]) -> List[Dict[str, Any]]:
    """(g) kalshi pregame n_events per sport, live call, honest degrade."""
    rows: List[Dict[str, Any]] = []
    for sport in KALSHI_PREGAME_SPORTS:
        try:
            result = fetch_fn(sport)
        except Exception as exc:  # noqa: BLE001 -- a network hiccup is PENDING, not FAIL
            rows.append(row(sport, PENDING, "fetch raised %s" % type(exc).__name__))
            continue
        if isinstance(result, dict):
            # kalshi.unavailable(...) shape: a dict, never a list of events.
            reason = result.get("reason") or result.get("error") or str(result)[:120]
            rows.append(row(sport, PENDING, "kalshi unavailable: %s" % reason))
            continue
        try:
            n_events = len(result)
        except Exception:  # noqa: BLE001
            rows.append(row(sport, PENDING, "fetch returned unrecognized shape"))
            continue
        if n_events > 0:
            rows.append(row(sport, PASS, "n_events=%d" % n_events, n_events=n_events))
        else:
            rows.append(row(sport, FAIL, "n_events=0 (pregame feed empty)",
                            n_events=0))
    return rows


__all__ = [
    "PASS", "FAIL", "PENDING",
    "NEW_PROCS", "SERVING_PORTS", "KALSHI_PREGAME_SPORTS",
    "row", "read_json", "restart_ts",
    "check_supervisor_status", "check_ports", "check_new_procs",
    "check_freshness_sla", "check_kalshi_pregame",
]
