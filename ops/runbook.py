"""ops.runbook -- the 'ops doctor': what is wrong + what to do.

Turns the aggregated status.json into a structured, actionable diagnosis. For
every down/degraded service it emits the likely cause and the concrete remedy
(the boot.ps1 / watchdog command that brings it back). Designed to be run by a
human at 2am: ``python -m ops.runbook``.

Public API
----------
doctor(*, status=None, now=None) -> dict
    {
      "overall": "ok"|"degraded"|"down",
      "summary": "<one-line headline>",
      "problems": [
        {"service": str, "severity": "critical"|"warning",
         "symptom": str, "remedy": str}
      ],
      "ok_services": [<name>...],
      "generated_at": "<ISO-8601 UTC>"
    }
    If *status* is None it aggregates a fresh one. Never raises.

render(diagnosis) -> str
    A plain-ASCII text report of the diagnosis (what `__main__` prints).

DOCTOR CONTRACT (what callers may rely on):
  * doctor()["problems"] names EVERY non-ok service (down or stale) by name.
  * each problem carries a non-empty human remedy string.
  * doctor()["summary"] states overall and the count of problems.
  * doctor() NEVER raises and is offline (no network, no port binding).

INVARIANTS: <=300 LOC; ASCII only; stdlib only; never raises. Build only under ops/.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ops import health_aggregator as _agg

# Per-service remedy hints. Windows-first (the user runs Win11 PowerShell);
# a posix note is appended where the path differs (RunPod RTX 3090).
_REMEDIES: Dict[str, str] = {
    "m1_producer": (
        "Producer/scheduler heartbeat is stale -- the predict-service is not "
        "writing data/frontend/predict_service/_heartbeat.json. Restart the stack: "
        ".\\boot.ps1   (posix: bash boot.sh). Check logs/m1_producer.err."
    ),
    "m1_api_paper": (
        "Auto-API :8099 is not answering /health. Restart: .\\boot.ps1 "
        "(it relaunches m1_api_paper after the producer is READY). "
        "Verify with: curl http://127.0.0.1:8099/health."
    ),
    "m1_api_boards": (
        "Boards API :8098 port is closed. Restart the stack with .\\boot.ps1; "
        "it depends on m1_api_paper being up first."
    ),
    "m1_ui": (
        "Next.js UI :3000 is down. Restart the stack (.\\boot.ps1) or, for UI only, "
        "run `npm run dev` in court-visions. Non-critical: backend keeps serving."
    ),
    "m1_paper": (
        "Paper auto_loop is not running -- no new paper bets / CLV rows. Restart: "
        ".\\boot.ps1. It depends on the Auto-API. Non-critical (display only)."
    ),
    "m1_line_daemon": (
        "Line snapshot daemon is stale -- odds will go stale. Restart via "
        ".\\boot.ps1, or relaunch line_snapshot_daemon directly. The watchdog "
        "(scripts/daemon_watchdog.py --platform auto) also auto-restarts it."
    ),
    "m6_ingame_loop": (
        "In-game live_loop heartbeat is stale -- live re-pricing has stopped. "
        "Restart via .\\boot.ps1. Check data/frontend/ingame/_heartbeat.json age."
    ),
    "m2_inplay": (
        "In-play capture daemon (P2) heartbeat is stale -- in-game ticks have "
        "stopped. Restart via .\\boot.ps1; the supervisor relaunches it with "
        "backoff. Non-critical (capture only). Check logs/m2_inplay.err."
    ),
    "m4_selfimprove": (
        "Self-improve daemon (P4) heartbeat is stale -- recalibration ratchet "
        "has stopped. Restart via .\\boot.ps1; it RESUMES from "
        "data/cache/improve/checkpoint.json (no reprocessing). Non-critical."
    ),
    "m7_ingame_refresh": (
        "In-game refresh loop (P7) heartbeat is stale -- the living in-game model "
        "has stopped folding newly-settled finals / re-gating / re-fitting. It "
        "beats HOURLY, so 'stale' here means it is genuinely dead, not merely "
        "between beats. Restart via .\\boot.ps1; it RESUMES from its checkpoint "
        "(no reprocessing). Check data/cache/daemon_heartbeats/m7_ingame_refresh.txt "
        "age + logs/m7_ingame_refresh.err. Non-critical (measurement only)."
    ),
}

_DEFAULT_REMEDY = (
    "Service heartbeat is stale or its port is closed. Restart the stack with "
    ".\\boot.ps1 (posix: bash boot.sh) and inspect logs/<name>.err."
)


def _utc_iso(ts: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts is not None else datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _symptom(row: Dict[str, Any]) -> str:
    reason = row.get("reason")
    if reason:
        base = reason
    elif row.get("breaker") == "OPEN":
        base = "circuit breaker OPEN (repeated failures)"
    elif row.get("fresh") in ("stale", "down"):
        base = "data source %s" % row.get("fresh")
    else:
        base = "not live"
    age = row.get("age_sec")
    if age is not None:
        base += " (last seen %.0fs ago)" % float(age)
    port = row.get("port")
    if port is not None:
        base += " [port %s]" % port
    return base


def _is_problem(row: Dict[str, Any]) -> bool:
    if row.get("live") is False:
        return True
    if row.get("breaker") == "OPEN":
        return True
    if row.get("fresh") in ("stale", "down"):
        return True
    return False


def doctor(
    *,
    status: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Diagnose the aggregated status. Names every non-ok service. Never raises."""
    try:
        if status is None:
            status = _agg.aggregate(now=now)
    except Exception:  # noqa: BLE001
        status = {"overall": "down", "services": [], "notes": ["aggregate failed"]}

    services = status.get("services", []) if isinstance(status, dict) else []
    problems: List[Dict[str, Any]] = []
    ok_services: List[str] = []
    for row in services:
        if not isinstance(row, dict):
            continue
        name = row.get("name", "?")
        if _is_problem(row):
            problems.append({
                "service": name,
                "severity": "critical" if row.get("critical") else "warning",
                "symptom": _symptom(row),
                "remedy": _REMEDIES.get(name, _DEFAULT_REMEDY),
            })
        else:
            ok_services.append(name)

    overall = status.get("overall", "ok")
    if not problems:
        summary = "All %d services healthy (overall=%s)." % (len(ok_services), overall)
    else:
        summary = "%d problem(s); overall=%s. Critical: %s." % (
            len(problems), overall,
            ", ".join(p["service"] for p in problems if p["severity"] == "critical") or "none",
        )

    return {
        "overall": overall,
        "summary": summary,
        "problems": problems,
        "ok_services": ok_services,
        "generated_at": _utc_iso(now),
    }


def render(diagnosis: Dict[str, Any]) -> str:
    """Render a doctor() diagnosis as a plain-ASCII text report."""
    lines: List[str] = []
    lines.append("=" * 62)
    lines.append("OPS DOCTOR -- %s" % diagnosis.get("generated_at", "?"))
    lines.append("=" * 62)
    lines.append(diagnosis.get("summary", ""))
    problems = diagnosis.get("problems", [])
    if problems:
        lines.append("")
        lines.append("PROBLEMS:")
        for p in problems:
            lines.append("  [%s] %s" % (p.get("severity", "?").upper(), p.get("service")))
            lines.append("      symptom: %s" % p.get("symptom"))
            lines.append("      remedy:  %s" % p.get("remedy"))
    ok = diagnosis.get("ok_services", [])
    if ok:
        lines.append("")
        lines.append("HEALTHY: %s" % ", ".join(ok))
    lines.append("=" * 62)
    return "\n".join(lines)


def main() -> int:
    """`python -m ops.runbook` -- print the diagnosis; exit 1 if not ok."""
    diag = doctor()
    print(render(diag))
    return 0 if diag.get("overall") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["doctor", "render", "main"]
