"""slo.py — SLO definitions and evaluator for the CourtVision platform.

Each SLO exposes ``check(context) -> (ok: bool, detail: str)``. The public
``evaluate(context, alert_sink)`` runs all 5 checks and calls
``alert_sink(slo_name, detail)`` exactly once per breach (deduped within a
single call). Inject a mock sink in tests — never hits the network.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds (constants — one source of truth, referenced in SLOS.md)
# ---------------------------------------------------------------------------

LOOP_HEARTBEAT_THRESHOLD_SEC: int = 86_400   # 24 h
OPENER_CAPTURE_THRESHOLD_HOURS: int = 24      # within 24 h of game day
REGISTRY_WRITE_FAIL_THRESHOLD: int = 0        # zero failures tolerated

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

CheckResult = Tuple[bool, str]   # (ok, detail)
AlertSink = Callable[[str, str], None]


# ---------------------------------------------------------------------------
# Individual SLO check functions
# ---------------------------------------------------------------------------

def _check_loop_heartbeat(context: Dict[str, Any]) -> CheckResult:
    """SLO-1: loop iteration within 24 h; ok=True/n/a when signal absent."""
    field = context.get("loop_heartbeat_age_sec", {})
    if not isinstance(field, dict):
        return True, "no_signal: loop_heartbeat_age_sec missing"
    value = field.get("value")
    note = field.get("note", "")
    if value is None:
        return True, f"n/a: loop_heartbeat_age_sec absent (note={note!r})"
    age = float(value)
    if age > LOOP_HEARTBEAT_THRESHOLD_SEC:
        return (
            False,
            f"loop_heartbeat_age_sec={age:.0f}s > threshold={LOOP_HEARTBEAT_THRESHOLD_SEC}s",
        )
    return True, f"ok: loop_heartbeat_age_sec={age:.0f}s"


def _check_opener_captured(context: Dict[str, Any]) -> CheckResult:
    """SLO-2: opener captured for 100% of game days; n/a if no ledger."""
    field = context.get("capture_row_age_sec", {})
    if not isinstance(field, dict):
        return True, "n/a: capture_row_age_sec missing"
    value = field.get("value")
    note = field.get("note", "")
    if value is None or note in ("no_ledger", "no_rows", "absent"):
        return True, f"n/a: no ledger/game-day info (note={note!r})"
    age_sec = float(value)
    threshold_sec = OPENER_CAPTURE_THRESHOLD_HOURS * 3600
    if age_sec > threshold_sec:
        return (
            False,
            f"capture_row_age_sec={age_sec:.0f}s > threshold={threshold_sec}s "
            f"({OPENER_CAPTURE_THRESHOLD_HOURS}h)",
        )
    return True, f"ok: capture_row_age_sec={age_sec:.0f}s"


def _check_api_boot_green(context: Dict[str, Any]) -> CheckResult:
    """SLO-3: API boot green — api_health must equal 'up'."""
    field = context.get("api_health", {})
    if not isinstance(field, dict):
        return True, "no_signal: api_health missing"
    value = field.get("value")
    if value is None:
        return True, "n/a: api_health.value absent"
    if value != "up":
        return False, f"api_health={value!r} != 'up'"
    return True, "ok: api_health=up"


def _check_registry_write_failures(context: Dict[str, Any]) -> CheckResult:
    """SLO-4: zero registry-write failures; ok=True/"no signal" if counter absent."""
    failures = context.get("registry_write_failures")
    if failures is None:
        return True, "no signal: registry_write_failures counter absent"
    try:
        count = int(failures)
    except (TypeError, ValueError):
        return True, f"no signal: registry_write_failures unparseable ({failures!r})"
    if count > REGISTRY_WRITE_FAIL_THRESHOLD:
        return False, f"registry_write_failures={count} > threshold={REGISTRY_WRITE_FAIL_THRESHOLD}"
    return True, f"ok: registry_write_failures={count}"


def _check_g2_baseline_drift(context: Dict[str, Any]) -> CheckResult:
    """SLO-5: G2 baseline drift — page immediately; n/a/unknown if baseline absent."""
    g2_hash = context.get("g2_baseline_hash")
    if g2_hash is None:
        return True, "n/a/unknown: G2 fixture-hash baseline absent (P0-B-002 not built)"
    # When present: a non-empty hash means baseline exists; evaluate drift.
    drift = context.get("g2_baseline_drift_pct")
    if drift is None:
        return True, f"n/a: baseline hash present ({g2_hash!r}) but no drift metric"
    try:
        drift_pct = float(drift)
    except (TypeError, ValueError):
        return True, f"no signal: g2_baseline_drift_pct unparseable ({drift!r})"
    if drift_pct != 0.0:  # any drift = page immediately
        return False, f"G2 baseline drift detected: drift_pct={drift_pct}"
    return True, f"ok: G2 baseline drift=0"


# ---------------------------------------------------------------------------
# SLO registry
# ---------------------------------------------------------------------------

# Each entry: (name, check_fn, owner, runbook_line)
_SLOS: List[Tuple[str, Callable[[Dict[str, Any]], CheckResult], str, str]] = [
    (
        "loop_heartbeat_within_24h",
        _check_loop_heartbeat,
        "platform-oncall",
        "Check data/registry/state.json mtime; restart loop if stale > 24 h",
    ),
    (
        "opener_captured_for_game_days",
        _check_opener_captured,
        "platform-oncall",
        "Check data/lines/forward/ ledger freshness; re-run capture job if stale",
    ),
    (
        "api_boot_green",
        _check_api_boot_green,
        "platform-oncall",
        "Check GET http://127.0.0.1:8077/health; restart API if unreachable",
    ),
    (
        "zero_registry_write_failures",
        _check_registry_write_failures,
        "platform-oncall",
        "Check registry_write_failures counter; inspect data/registry/ write errors",
    ),
    (
        "g2_baseline_drift_page_immediately",
        _check_g2_baseline_drift,
        "platform-oncall",
        "Check G2 fixture-hash baseline; page immediately on any drift != 0",
    ),
]

SLO_NAMES: List[str] = [s[0] for s in _SLOS]  # public names (e.g. for SLOS.md)


# ---------------------------------------------------------------------------
# Default alert sink — wraps discord_webhook.alert
# ---------------------------------------------------------------------------

def _default_alert_sink(slo_name: str, detail: str) -> None:
    """Default alert sink: delegates to src.alerts.discord_webhook.alert (lazy import)."""
    try:
        from src.alerts.discord_webhook import alert as discord_alert  # noqa: PLC0415
        discord_alert(
            message=f"[SLO BREACH] {slo_name}: {detail}",
            level="critical",
            tag="slo_evaluator",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("SLO alert sink failed for %r: %s", slo_name, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_context_from_snapshot() -> Dict[str, Any]:
    """Build an SLO context dict from health_snapshot.snapshot() (lazy import)."""
    try:
        import sys  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415
        _here = Path(__file__).resolve().parent
        if str(_here) not in sys.path:
            sys.path.insert(0, str(_here))
        from health_snapshot import snapshot  # noqa: PLC0415 # type: ignore[import]
        return snapshot()
    except Exception as exc:  # noqa: BLE001
        log.warning("health_snapshot unavailable — returning empty context: %s", exc)
        return {}


def evaluate(
    context: Optional[Dict[str, Any]] = None,
    alert_sink: Optional[AlertSink] = None,
) -> List[Dict[str, Any]]:
    """Evaluate all SLOs; fire ``alert_sink(name, detail)`` once per breach.

    When ``context`` is None, calls ``build_context_from_snapshot()`` automatically.
    When ``alert_sink`` is None, uses ``_default_alert_sink`` (Discord webhook).
    Inject a mock sink in tests — never raises, never hits the network.
    Returns a list of ``{name, ok, detail, owner, runbook}`` dicts.
    """
    if context is None:
        context = build_context_from_snapshot()
    sink = alert_sink if alert_sink is not None else _default_alert_sink

    alerted: set = set()  # dedup: one alert per breach per evaluate() call
    results: List[Dict[str, Any]] = []

    for name, check_fn, owner, runbook in _SLOS:
        try:
            ok, detail = check_fn(context)
        except Exception as exc:  # noqa: BLE001
            log.warning("SLO check %r raised unexpectedly: %s", name, exc)
            ok, detail = True, f"check_error: {exc}"

        if not ok and name not in alerted:
            try:
                sink(name, detail)
            except Exception as exc:  # noqa: BLE001
                log.warning("alert_sink raised for SLO %r: %s", name, exc)
            alerted.add(name)

        results.append({
            "name": name,
            "ok": ok,
            "detail": detail,
            "owner": owner,
            "runbook": runbook,
        })

    return results


__all__ = [
    "evaluate",
    "build_context_from_snapshot",
    "SLO_NAMES",
    "LOOP_HEARTBEAT_THRESHOLD_SEC",
    "OPENER_CAPTURE_THRESHOLD_HOURS",
    "REGISTRY_WRITE_FAIL_THRESHOLD",
]
