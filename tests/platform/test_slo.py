"""test_slo.py — Acceptance tests for scripts/platformkit/obs/slo.py.

Verification criteria
---------------------
* Each SLO, when synthetically breached, fires EXACTLY ONE alert on the
  mock sink (assert call_count == 1 per breach).
* A healthy context fires zero alerts.
* ``evaluate()`` never raises and never performs real network I/O.
* The mock sink is always injected — the default Discord sink is never
  called from these tests.

Python 3.9 compatible.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

import pytest

# Make slo.py importable directly (scripts/platformkit/obs on sys.path)
ROOT = Path(__file__).resolve().parents[2]
_OBS_DIR = ROOT / "scripts" / "platformkit" / "obs"
if str(_OBS_DIR) not in sys.path:
    sys.path.insert(0, str(_OBS_DIR))

from slo import (  # noqa: E402
    LOOP_HEARTBEAT_THRESHOLD_SEC,
    OPENER_CAPTURE_THRESHOLD_HOURS,
    REGISTRY_WRITE_FAIL_THRESHOLD,
    SLO_NAMES,
    evaluate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sink() -> MagicMock:
    """Return a fresh MagicMock that records (slo_name, detail) calls."""
    return MagicMock()


def _healthy_context() -> Dict[str, Any]:
    """Return a context dict that makes all SLOs pass."""
    return {
        # SLO-1: heartbeat fresh (1 h ago)
        "loop_heartbeat_age_sec": {
            "value": 3_600.0,
            "unit": "sec",
            "threshold": LOOP_HEARTBEAT_THRESHOLD_SEC,
        },
        # SLO-2: capture fresh (30 min ago)
        "capture_row_age_sec": {
            "value": 1_800.0,
            "unit": "sec",
            "threshold": OPENER_CAPTURE_THRESHOLD_HOURS * 3600,
        },
        # SLO-3: API up
        "api_health": {
            "value": "up",
            "unit": "status",
            "threshold": "up",
        },
        # SLO-4: no registry write failures
        "registry_write_failures": 0,
        # SLO-5: G2 baseline absent (n/a — P0-B-002 not built)
        # deliberately omitted → n/a treatment
    }


# ---------------------------------------------------------------------------
# 1. Healthy context → zero alerts
# ---------------------------------------------------------------------------

def test_healthy_context_fires_zero_alerts():
    sink = _make_sink()
    results = evaluate(context=_healthy_context(), alert_sink=sink)
    assert sink.call_count == 0, (
        f"Healthy context must fire 0 alerts, got {sink.call_count}"
    )
    assert all(r["ok"] for r in results), (
        "All SLOs must be ok in a healthy context"
    )


# ---------------------------------------------------------------------------
# 2. Breach SLO-1: loop_heartbeat_within_24h
# ---------------------------------------------------------------------------

def test_loop_heartbeat_breach_fires_exactly_one_alert():
    ctx = _healthy_context()
    ctx["loop_heartbeat_age_sec"] = {
        "value": LOOP_HEARTBEAT_THRESHOLD_SEC + 1,  # 1 second over threshold
        "unit": "sec",
        "threshold": LOOP_HEARTBEAT_THRESHOLD_SEC,
    }
    sink = _make_sink()
    results = evaluate(context=ctx, alert_sink=sink)

    breached = [r for r in results if r["name"] == "loop_heartbeat_within_24h"]
    assert len(breached) == 1
    assert breached[0]["ok"] is False
    assert sink.call_count == 1, (
        f"loop_heartbeat breach must fire exactly 1 alert, got {sink.call_count}"
    )
    fired_name = sink.call_args[0][0]
    assert fired_name == "loop_heartbeat_within_24h"


# ---------------------------------------------------------------------------
# 3. Breach SLO-2: opener_captured_for_game_days
# ---------------------------------------------------------------------------

def test_opener_captured_breach_fires_exactly_one_alert():
    ctx = _healthy_context()
    stale_sec = (OPENER_CAPTURE_THRESHOLD_HOURS + 1) * 3600  # 1 hour over
    ctx["capture_row_age_sec"] = {
        "value": float(stale_sec),
        "unit": "sec",
        "threshold": OPENER_CAPTURE_THRESHOLD_HOURS * 3600,
    }
    sink = _make_sink()
    results = evaluate(context=ctx, alert_sink=sink)

    breached = [r for r in results if r["name"] == "opener_captured_for_game_days"]
    assert len(breached) == 1
    assert breached[0]["ok"] is False
    assert sink.call_count == 1, (
        f"opener_captured breach must fire exactly 1 alert, got {sink.call_count}"
    )
    fired_name = sink.call_args[0][0]
    assert fired_name == "opener_captured_for_game_days"


# ---------------------------------------------------------------------------
# 4. Breach SLO-3: api_boot_green
# ---------------------------------------------------------------------------

def test_api_boot_green_breach_fires_exactly_one_alert():
    ctx = _healthy_context()
    ctx["api_health"] = {
        "value": "unreachable",
        "unit": "status",
        "threshold": "up",
    }
    sink = _make_sink()
    results = evaluate(context=ctx, alert_sink=sink)

    breached = [r for r in results if r["name"] == "api_boot_green"]
    assert len(breached) == 1
    assert breached[0]["ok"] is False
    assert sink.call_count == 1, (
        f"api_boot_green breach must fire exactly 1 alert, got {sink.call_count}"
    )
    fired_name = sink.call_args[0][0]
    assert fired_name == "api_boot_green"


def test_api_http_503_is_breach():
    ctx = _healthy_context()
    ctx["api_health"] = {"value": "http_503", "unit": "status", "threshold": "up"}
    sink = _make_sink()
    results = evaluate(context=ctx, alert_sink=sink)
    breached = [r for r in results if r["name"] == "api_boot_green"]
    assert breached[0]["ok"] is False
    assert sink.call_count == 1


# ---------------------------------------------------------------------------
# 5. Breach SLO-4: zero_registry_write_failures
# ---------------------------------------------------------------------------

def test_registry_write_failure_breach_fires_exactly_one_alert():
    ctx = _healthy_context()
    ctx["registry_write_failures"] = 3  # non-zero → breach
    sink = _make_sink()
    results = evaluate(context=ctx, alert_sink=sink)

    breached = [r for r in results if r["name"] == "zero_registry_write_failures"]
    assert len(breached) == 1
    assert breached[0]["ok"] is False
    assert sink.call_count == 1, (
        f"registry_write_failures breach must fire exactly 1 alert, got {sink.call_count}"
    )
    fired_name = sink.call_args[0][0]
    assert fired_name == "zero_registry_write_failures"


def test_registry_failures_absent_is_ok():
    """When counter absent, SLO-4 must be ok (no signal = assume ok)."""
    ctx = _healthy_context()
    ctx.pop("registry_write_failures", None)
    sink = _make_sink()
    results = evaluate(context=ctx, alert_sink=sink)
    slo4 = next(r for r in results if r["name"] == "zero_registry_write_failures")
    assert slo4["ok"] is True
    # Overall alerts may be 0 (no other breach)
    assert sink.call_count == 0


# ---------------------------------------------------------------------------
# 6. SLO-5: g2_baseline_drift_page_immediately — absent baseline is n/a
# ---------------------------------------------------------------------------

def test_g2_baseline_absent_is_not_a_breach():
    """P0-B-002 not built → g2_baseline_hash absent → n/a, no alert."""
    ctx = _healthy_context()
    # Ensure the key is absent (healthy_context doesn't include it)
    ctx.pop("g2_baseline_hash", None)
    ctx.pop("g2_baseline_drift_pct", None)
    sink = _make_sink()
    results = evaluate(context=ctx, alert_sink=sink)

    slo5 = next(r for r in results if r["name"] == "g2_baseline_drift_page_immediately")
    assert slo5["ok"] is True
    assert "n/a" in slo5["detail"].lower() or "unknown" in slo5["detail"].lower()
    assert sink.call_count == 0


def test_g2_baseline_drift_fires_exactly_one_alert():
    """When baseline IS present and drift != 0, fire exactly one alert."""
    ctx = _healthy_context()
    ctx["g2_baseline_hash"] = "abc123"
    ctx["g2_baseline_drift_pct"] = 2.5  # non-zero drift → breach
    sink = _make_sink()
    results = evaluate(context=ctx, alert_sink=sink)

    slo5 = next(r for r in results if r["name"] == "g2_baseline_drift_page_immediately")
    assert slo5["ok"] is False
    assert sink.call_count == 1
    fired_name = sink.call_args[0][0]
    assert fired_name == "g2_baseline_drift_page_immediately"


# ---------------------------------------------------------------------------
# 7. Multiple simultaneous breaches — each fires exactly one alert
# ---------------------------------------------------------------------------

def test_multiple_breaches_each_fire_once():
    """Breach SLO-1 and SLO-3 simultaneously; expect exactly 2 alerts."""
    ctx = _healthy_context()
    ctx["loop_heartbeat_age_sec"] = {
        "value": LOOP_HEARTBEAT_THRESHOLD_SEC + 9999,
        "unit": "sec",
        "threshold": LOOP_HEARTBEAT_THRESHOLD_SEC,
    }
    ctx["api_health"] = {"value": "unreachable", "unit": "status", "threshold": "up"}

    sink = _make_sink()
    results = evaluate(context=ctx, alert_sink=sink)

    assert sink.call_count == 2, (
        f"Two simultaneous breaches must fire exactly 2 alerts, got {sink.call_count}"
    )
    fired_names = {call[0][0] for call in sink.call_args_list}
    assert "loop_heartbeat_within_24h" in fired_names
    assert "api_boot_green" in fired_names


# ---------------------------------------------------------------------------
# 8. evaluate() never raises, even with adversarial / empty context
# ---------------------------------------------------------------------------

def test_evaluate_never_raises_on_empty_context():
    sink = _make_sink()
    try:
        results = evaluate(context={}, alert_sink=sink)
    except Exception as exc:
        pytest.fail(f"evaluate() raised on empty context: {exc!r}")
    assert isinstance(results, list)


def test_evaluate_never_raises_on_none_context():
    """evaluate(context=None) must auto-call build_context_from_snapshot() without raising."""
    sink = _make_sink()
    try:
        results = evaluate(context=None, alert_sink=sink)
    except Exception as exc:
        pytest.fail(f"evaluate(context=None) raised: {exc!r}")
    assert isinstance(results, list)


def test_evaluate_never_raises_on_garbage_context():
    ctx: Dict[str, Any] = {
        "loop_heartbeat_age_sec": "GARBAGE",
        "capture_row_age_sec": 12345,
        "api_health": None,
        "registry_write_failures": "not-a-number",
        "g2_baseline_hash": object(),
    }
    sink = _make_sink()
    try:
        results = evaluate(context=ctx, alert_sink=sink)
    except Exception as exc:
        pytest.fail(f"evaluate() raised on garbage context: {exc!r}")
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# 9. evaluate() returns the correct structure for every SLO
# ---------------------------------------------------------------------------

def test_evaluate_returns_all_slo_names():
    sink = _make_sink()
    results = evaluate(context=_healthy_context(), alert_sink=sink)
    returned_names = {r["name"] for r in results}
    assert returned_names == set(SLO_NAMES), (
        f"Missing SLOs: {set(SLO_NAMES) - returned_names}"
    )


def test_evaluate_result_entries_have_required_keys():
    sink = _make_sink()
    results = evaluate(context=_healthy_context(), alert_sink=sink)
    required = {"name", "ok", "detail", "owner", "runbook"}
    for r in results:
        missing = required - set(r.keys())
        assert not missing, f"SLO entry {r.get('name')!r} missing keys: {missing}"


# ---------------------------------------------------------------------------
# 10. Dedup: calling evaluate() twice with the same breach fires once per call
# ---------------------------------------------------------------------------

def test_dedup_within_single_evaluate_call():
    """A single breach must fire the sink exactly once per evaluate() call."""
    ctx = _healthy_context()
    ctx["loop_heartbeat_age_sec"] = {
        "value": LOOP_HEARTBEAT_THRESHOLD_SEC + 1,
        "unit": "sec",
        "threshold": LOOP_HEARTBEAT_THRESHOLD_SEC,
    }
    sink = _make_sink()
    # Run evaluate twice; each call should independently fire once.
    evaluate(context=ctx, alert_sink=sink)
    evaluate(context=ctx, alert_sink=sink)
    assert sink.call_count == 2, (
        f"Each evaluate() call must fire exactly 1 alert for the same breach; "
        f"got total {sink.call_count} across 2 calls"
    )


# ---------------------------------------------------------------------------
# 11. No real network I/O — sink is always the mock
# ---------------------------------------------------------------------------

def test_no_real_discord_call_when_sink_injected(monkeypatch):
    """Confirm that injecting a mock sink prevents any real Discord call."""
    # Monkeypatch the discord_webhook.alert to raise if called.
    called_real = []

    def _spy_discord(*args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        called_real.append((args, kwargs))
        raise AssertionError("Real discord_webhook.alert must NOT be called in tests")

    # Patch at the module level where slo.py would import it.
    try:
        import src.alerts.discord_webhook as dw  # noqa: PLC0415
        monkeypatch.setattr(dw, "alert", _spy_discord)
    except ImportError:
        pass  # module unavailable in this environment — skip patching

    ctx = _healthy_context()
    ctx["loop_heartbeat_age_sec"] = {
        "value": LOOP_HEARTBEAT_THRESHOLD_SEC + 1,
        "unit": "sec",
        "threshold": LOOP_HEARTBEAT_THRESHOLD_SEC,
    }
    sink = _make_sink()
    evaluate(context=ctx, alert_sink=sink)

    assert not called_real, "Real discord alert must not be called when a mock sink is injected"
    assert sink.call_count == 1
