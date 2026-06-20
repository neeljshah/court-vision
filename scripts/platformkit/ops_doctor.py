"""scripts.platformkit.ops_doctor -- lane-correct runbook doctor CLI.

One-command stack diagnosis consuming the SAME freshness aggregation as
autonomy/status_composer.  Fixes QA iter 3/9: fresh=null is treated as
UNKNOWN (not ok), never green -- so a stale critical producer is never
silently served as healthy.

CLI: python -m scripts.platformkit.ops_doctor [--json]
API: diagnose(*, autonomy_doc=None, now=None) -> dict
     render(diag) -> str (ASCII)   main() -> int (exit 1 if not ok)

Output shape: {overall, summary, problems[{service, severity, symptom,
               recovery_hint, critical}], ok_services, generated_at}
INVARIANTS: read-only; no $ / roi / pnl key; critical-first sorted;
            fresh=null => DEGRADED when live is not None; <=300 LOC.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Import the SAME aggregation path as autonomy/freshness so the doctor
# sees exactly what the autonomy monitor sees -- no parallel stub that can drift.
from scripts.platformkit.autonomy.status_composer import compose as _compose

OK = "ok"
DEGRADED = "degraded"
DOWN = "down"

_RANK = {OK: 0, DEGRADED: 1, DOWN: 2}
_BY_RANK = {v: k for k, v in _RANK.items()}

# Per-service recovery hints: Windows-first, posix note appended where path differs.
# Keyed by service name (from ops.service_registry); missing -> _DEFAULT_HINT.
_RECOVERY_HINTS: Dict[str, str] = {
    "m1_producer": (
        "Predict-service scheduler heartbeat stale / data source past SLA. "
        "Restart: .\\boot.ps1  (posix: bash boot.sh). "
        "Check data/frontend/predict_service/_heartbeat.json age."
    ),
    "m1_api_paper": (
        "Auto-API :8099 not answering /health. Restart: .\\boot.ps1. "
        "Verify: curl http://127.0.0.1:8099/health"
    ),
    "m1_api_boards": (
        "Boards API :8098 port closed. Restart: .\\boot.ps1 "
        "(depends on m1_api_paper up first)."
    ),
    "m1_ui": (
        "Next.js UI :3000 down. Restart: .\\boot.ps1 or "
        "`npm run dev` in court-visions. Non-critical."
    ),
    "m1_paper": (
        "Paper auto_loop not running -- no new paper bets / CLV rows. "
        "Restart: .\\boot.ps1. Non-critical (display only)."
    ),
    "m1_line_daemon": (
        "Line snapshot daemon stale -- odds going stale. Restart: .\\boot.ps1 "
        "or scripts/daemon_watchdog.py --platform auto."
    ),
    "m6_ingame_loop": (
        "In-game live_loop stale -- live re-pricing stopped. Restart: .\\boot.ps1. "
        "Check data/frontend/ingame/_heartbeat.json age."
    ),
    "m2_inplay": (
        "In-play capture daemon stale -- in-game ticks stopped. "
        "Restart: .\\boot.ps1; supervisor relaunches with backoff. "
        "Non-critical (capture only)."
    ),
    "m4_selfimprove": (
        "Self-improve daemon stale -- recalibration ratchet stopped. "
        "Restart: .\\boot.ps1; RESUMES from data/cache/improve/checkpoint.json. "
        "Non-critical (measurement only)."
    ),
    "m7_ingame_refresh": (
        "In-game refresh loop stale -- model not folding settled finals / re-gating. "
        "Beats HOURLY so stale means genuinely dead. "
        "Restart: .\\boot.ps1. Non-critical (measurement)."
    ),
    "m5_autonomy_monitor": (
        "Autonomy monitor daemon stale -- autonomy_status.json not refreshing. "
        "Restart: .\\boot.ps1. Non-critical (observability only)."
    ),
    "m8_ci_cadence": (
        "CI cadence runner stale -- progress ledger not ticking. "
        "Restart: .\\boot.ps1. Non-critical (measurement)."
    ),
    "m2_inplay_capture": (
        "In-play capture runner stale. Restart: .\\boot.ps1. Non-critical."
    ),
}

_DEFAULT_HINT = (
    "Service heartbeat stale or data source past SLA. "
    "Restart: .\\boot.ps1  (posix: bash boot.sh) and check logs/<name>.err."
)


def _utc_iso(ts: Optional[float] = None) -> str:
    dt = (datetime.fromtimestamp(ts, tz=timezone.utc)
          if ts is not None else datetime.now(timezone.utc))
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _severity_of_row(row: Dict[str, Any]) -> str:
    """Derive per-row severity with fresh=null treated as UNKNOWN (not ok).

    The gap in ops.health_aggregator._row_severity (and ops.runbook._is_problem):
    fresh=null is returned as ok for port-probed servers.  Here we treat null
    freshness as UNKNOWN for any row that has a liveness component (live not None),
    because a producer that SHOULD report freshness but doesn't is not healthy.

    DOWN     -- live is False, or breaker==OPEN, or fresh=="down"
    DEGRADED -- fresh=="stale", or fresh is None with live not None (unknown = not ok)
    OK       -- fresh=="fresh" and live is not False
    """
    if row.get("live") is False:
        return DOWN
    if row.get("breaker") == "OPEN":
        return DOWN
    fresh = row.get("fresh")
    if fresh == "down":
        return DOWN
    if fresh == "stale":
        return DEGRADED
    # KEY FIX: fresh=null with live not None (producer actively reporting liveness
    # but freshness unmeasured) is UNKNOWN -- not ok.  A critical producer whose
    # data-source freshness is not being measured should never read green.
    if fresh is None and row.get("live") is not None:
        return DEGRADED
    return OK


def _symptom_of(row: Dict[str, Any], sev: str) -> str:
    """One-line symptom string for a non-ok row."""
    parts: List[str] = []
    reason = row.get("reason")
    if reason:
        parts.append(str(reason))
    elif sev == DOWN and row.get("live") is False:
        parts.append("heartbeat absent or dead")
    elif row.get("breaker") == "OPEN":
        parts.append("circuit breaker OPEN (repeated failures)")
    elif row.get("fresh") in ("stale", "down"):
        parts.append("data source %s (past SLA)" % row.get("fresh"))
    elif row.get("fresh") is None and row.get("live") is not None:
        parts.append("freshness unknown (fresh=null; producer live but SLA unverified)")
    else:
        parts.append("not ok (%s)" % sev)

    age = row.get("age_sec")
    if age is not None:
        parts.append("last seen %.0fs ago" % float(age))
    port = row.get("port")
    if port is not None:
        parts.append("[port %s]" % port)
    return "; ".join(parts)


def _degrade(a: str, b: str) -> str:
    """Return the WORSE of two severity strings (monotone-DOWN)."""
    ra = _RANK.get(a, _RANK[DEGRADED])
    rb = _RANK.get(b, _RANK[DEGRADED])
    return _BY_RANK[max(ra, rb)]


def diagnose(
    *,
    autonomy_doc: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Diagnose the stack from the same aggregation as autonomy/freshness.

    Consumes status_composer.compose() so the doctor and the autonomy monitor
    read identical freshness verdicts.  fresh=null is treated as UNKNOWN (not ok).
    Critical problems are sorted before warnings; within each bucket: alphabetical.
    Never raises.  No $ / roi / pnl key.
    """
    try:
        doc = autonomy_doc if autonomy_doc is not None else _compose(now=now)
    except Exception:  # noqa: BLE001
        doc = {"overall": DOWN, "services": [], "notes": ["compose() raised"]}

    autonomy_overall = str(doc.get("overall", DEGRADED))
    if autonomy_overall not in _RANK:
        autonomy_overall = DEGRADED

    services = doc.get("services") or []
    problems: List[Dict[str, Any]] = []
    ok_services: List[str] = []

    # Parallel-derive our own severity (fresh=null fix applied).
    overall = OK
    for row in services:
        if not isinstance(row, dict):
            continue
        name = row.get("name", "?")
        sev = _severity_of_row(row)
        overall = _degrade(overall, sev)
        if sev != OK:
            is_critical = bool(row.get("critical"))
            problems.append({
                "service": name,
                "severity": "critical" if is_critical else "warning",
                "symptom": _symptom_of(row, sev),
                "recovery_hint": _RECOVERY_HINTS.get(name, _DEFAULT_HINT),
                "critical": is_critical,
            })
        else:
            ok_services.append(name)

    # doctor==degraded whenever autonomy==degraded (monotone-DOWN guarantee).
    overall = _degrade(overall, autonomy_overall)

    # Critical-first, then alphabetical within each bucket.
    problems.sort(key=lambda p: (0 if p["critical"] else 1, p["service"]))

    if not problems:
        summary = "All %d services healthy (overall=%s)." % (
            len(ok_services), overall)
    else:
        crits = [p["service"] for p in problems if p["critical"]]
        summary = "%d problem(s); overall=%s. Critical: %s." % (
            len(problems), overall,
            ", ".join(crits) if crits else "none",
        )

    return {
        "overall": overall,
        "summary": summary,
        "problems": problems,
        "ok_services": sorted(ok_services),
        "generated_at": _utc_iso(now),
    }


def render(diag: Dict[str, Any]) -> str:
    """Plain-ASCII text report of a diagnose() result."""
    lines: List[str] = []
    sep = "=" * 64
    lines.append(sep)
    lines.append("OPS DOCTOR -- %s" % diag.get("generated_at", "?"))
    lines.append(sep)
    lines.append(diag.get("summary", ""))
    problems = diag.get("problems", [])
    if problems:
        lines.append("")
        lines.append("PROBLEMS:")
        for p in problems:
            sev_tag = "[%s]" % p.get("severity", "?").upper()
            lines.append("  %s %s" % (sev_tag, p.get("service")))
            lines.append("      symptom:       %s" % p.get("symptom"))
            lines.append("      recovery_hint: %s" % p.get("recovery_hint"))
    ok = diag.get("ok_services", [])
    if ok:
        lines.append("")
        lines.append("HEALTHY: %s" % ", ".join(ok))
    lines.append(sep)
    lines.append("HONEST: calibration, not edge. No $ field. "
                 "fresh=null is UNKNOWN (not ok). Read-only; no procs started.")
    lines.append(sep)
    return "\n".join(lines)


def main() -> int:
    """`python -m scripts.platformkit.ops_doctor` -- diagnose and exit."""
    ap = argparse.ArgumentParser(
        description="OPS doctor: one-command stack diagnosis (read-only).")
    ap.add_argument("--json", action="store_true",
                    help="Print diagnosis as JSON instead of human text.")
    args = ap.parse_args()

    diag = diagnose()
    if args.json:
        print(json.dumps(diag, indent=2))
    else:
        print(render(diag))
    return 0 if diag.get("overall") == OK else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["diagnose", "render", "main"]
