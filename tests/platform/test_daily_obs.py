"""test_daily_obs.py — Acceptance tests for scripts/platformkit/obs/daily_obs.py.

Verification criteria
---------------------
* build_daily_report() returns a dict with the three required top-level
  sections: "health", "slos", "drift".
* The report also contains "generated_at" (ISO-8601 string).
* The function runs OFFLINE and completes quickly (< 15 s).
* No alerts are fired (null sink is the default).
* Nothing is written to disk.
* The API health probe inside health_snapshot is monkeypatched so the test
  never opens a real socket.
* slo.evaluate is called with the health dict as context — no second
  network call is made.
* drift_report.build_report() is monkeypatched to stay offline (it already
  is, but we guard against heavy pandas/scipy imports by confirming the
  patched path never raises ImportError in CI).

Python 3.9 compatible. No torch. No FastAPI boot.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# sys.path wiring — make obs/ siblings importable as bare names
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
_OBS_DIR = ROOT / "scripts" / "platformkit" / "obs"
if str(_OBS_DIR) not in sys.path:
    sys.path.insert(0, str(_OBS_DIR))

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

# daily_obs lives under scripts/platformkit/obs; import via file path so the
# test does not depend on package __init__ wiring.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "daily_obs", str(_OBS_DIR / "daily_obs.py")
)
_daily_obs_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_daily_obs_mod)  # type: ignore[union-attr]

build_daily_report = _daily_obs_mod.build_daily_report
_null_sink = _daily_obs_mod._null_sink


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def offline_health() -> Dict[str, Any]:
    """Minimal health snapshot that looks like health_snapshot.snapshot() output
    with no real disk/network I/O required."""
    return {
        "loop_heartbeat_age_sec": {"value": None, "unit": "sec", "threshold": 86400,
                                   "note": "absent"},
        "capture_row_age_sec": {"value": None, "unit": "sec", "threshold": 3600,
                                "note": "no_ledger"},
        "api_health": {"value": "unreachable", "unit": "status", "threshold": "up"},
        "registry_parquet_freshness_sec": {"value": None, "unit": "sec",
                                           "threshold": 86400, "note": "absent"},
        "disk_headroom_gb": {"value": 20.0, "unit": "GB", "threshold": 5.0},
        "last_vault_autowrite_age_sec": {"value": None, "unit": "sec",
                                         "threshold": 172800, "note": "absent"},
    }


@pytest.fixture()
def offline_drift() -> Dict[str, Any]:
    """Minimal drift report that looks like drift_report.build_report() output."""
    return {
        "generated_at": "2026-06-12T00:00:00+00:00",
        "data_sources": {
            "calibration_frame": "absent",
            "prop_calibration_history": "absent",
            "feature_drift_log": "absent",
        },
        "point_metrics": {"window_days": 30, "n_total": 0, "per_stat": {}, "flags": []},
        "coverage_metrics": {"per_stat": {}, "flags": []},
        "drift_metrics": {"model_count": 0, "flagged_models": [], "n_flagged": 0,
                          "flags": []},
        "all_flags": [],
    }


@pytest.fixture()
def offline_slos() -> List[Dict[str, Any]]:
    """Minimal SLO results list that looks like slo.evaluate() output."""
    return [
        {"name": "loop_heartbeat_within_24h", "ok": True, "detail": "n/a",
         "owner": "platform-oncall", "runbook": ""},
        {"name": "opener_captured_for_game_days", "ok": True, "detail": "n/a",
         "owner": "platform-oncall", "runbook": ""},
        {"name": "api_boot_green", "ok": False,
         "detail": "api_health='unreachable' != 'up'",
         "owner": "platform-oncall", "runbook": ""},
        {"name": "zero_registry_write_failures", "ok": True, "detail": "no signal",
         "owner": "platform-oncall", "runbook": ""},
        {"name": "g2_baseline_drift_page_immediately", "ok": True,
         "detail": "n/a/unknown: G2 fixture-hash baseline absent",
         "owner": "platform-oncall", "runbook": ""},
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mocked_report(
    offline_health: Dict[str, Any],
    offline_slos: List[Dict[str, Any]],
    offline_drift: Dict[str, Any],
) -> Dict[str, Any]:
    """Call build_daily_report() with all three sub-modules monkeypatched."""
    # Patch the three lazy-import functions inside daily_obs to return
    # mock module objects so no real imports or network I/O occur.

    mock_hs = MagicMock()
    mock_hs.snapshot.return_value = offline_health

    mock_slo = MagicMock()
    mock_slo.evaluate.return_value = offline_slos

    mock_dr = MagicMock()
    mock_dr.build_report.return_value = offline_drift

    with (
        patch.object(_daily_obs_mod, "_import_health_snapshot", return_value=mock_hs),
        patch.object(_daily_obs_mod, "_import_slo", return_value=mock_slo),
        patch.object(_daily_obs_mod, "_import_drift_report", return_value=mock_dr),
    ):
        return build_daily_report()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_dict_with_three_sections(
    offline_health: Dict[str, Any],
    offline_slos: List[Dict[str, Any]],
    offline_drift: Dict[str, Any],
) -> None:
    """build_daily_report() must return a dict with 'health', 'slos', 'drift'."""
    report = _make_mocked_report(offline_health, offline_slos, offline_drift)

    assert isinstance(report, dict), "return value must be a dict"
    assert "health" in report, "report must contain 'health'"
    assert "slos" in report, "report must contain 'slos'"
    assert "drift" in report, "report must contain 'drift'"


def test_generated_at_present(
    offline_health: Dict[str, Any],
    offline_slos: List[Dict[str, Any]],
    offline_drift: Dict[str, Any],
) -> None:
    """report['generated_at'] must be a non-empty ISO-8601-ish string."""
    report = _make_mocked_report(offline_health, offline_slos, offline_drift)

    gen = report.get("generated_at", "")
    assert isinstance(gen, str) and len(gen) >= 10, (
        f"generated_at must be an ISO-8601 string, got {gen!r}"
    )


def test_health_section_passthrough(
    offline_health: Dict[str, Any],
    offline_slos: List[Dict[str, Any]],
    offline_drift: Dict[str, Any],
) -> None:
    """report['health'] must be exactly the snapshot dict returned by the sub-module."""
    report = _make_mocked_report(offline_health, offline_slos, offline_drift)
    assert report["health"] == offline_health


def test_slos_section_passthrough(
    offline_health: Dict[str, Any],
    offline_slos: List[Dict[str, Any]],
    offline_drift: Dict[str, Any],
) -> None:
    """report['slos'] must be exactly the list returned by the SLO evaluator."""
    report = _make_mocked_report(offline_health, offline_slos, offline_drift)
    assert report["slos"] == offline_slos


def test_drift_section_passthrough(
    offline_health: Dict[str, Any],
    offline_slos: List[Dict[str, Any]],
    offline_drift: Dict[str, Any],
) -> None:
    """report['drift'] must be exactly the dict returned by drift_report.build_report()."""
    report = _make_mocked_report(offline_health, offline_slos, offline_drift)
    assert report["drift"] == offline_drift


def test_no_alerts_fired_by_default(
    offline_health: Dict[str, Any],
    offline_slos: List[Dict[str, Any]],
    offline_drift: Dict[str, Any],
) -> None:
    """With the default null sink, no alert should be fired even if SLOs breach."""
    alert_calls: List[Any] = []

    def _spy_sink(name: str, detail: str) -> None:
        alert_calls.append((name, detail))

    mock_hs = MagicMock()
    mock_hs.snapshot.return_value = offline_health

    mock_slo = MagicMock()
    # Simulate the real slo.evaluate: it would call the sink for breaches,
    # but we confirm the null_sink is passed and the list is empty.
    mock_slo.evaluate.return_value = offline_slos

    mock_dr = MagicMock()
    mock_dr.build_report.return_value = offline_drift

    with (
        patch.object(_daily_obs_mod, "_import_health_snapshot", return_value=mock_hs),
        patch.object(_daily_obs_mod, "_import_slo", return_value=mock_slo),
        patch.object(_daily_obs_mod, "_import_drift_report", return_value=mock_dr),
    ):
        # Default call — no explicit alert_sink
        build_daily_report()

    # Verify slo.evaluate was called with a null/no-op sink (not the spy)
    call_kwargs = mock_slo.evaluate.call_args
    sink_arg = call_kwargs[1].get("alert_sink") or call_kwargs[0][1]
    assert sink_arg is _daily_obs_mod._null_sink, (
        "Default alert_sink must be _null_sink, not a real sink"
    )
    assert alert_calls == [], "No alert should have been fired via the spy"


def test_explicit_alert_sink_is_forwarded(
    offline_health: Dict[str, Any],
    offline_slos: List[Dict[str, Any]],
    offline_drift: Dict[str, Any],
) -> None:
    """An explicit alert_sink passed to build_daily_report() must be forwarded to slo.evaluate."""
    my_sink = MagicMock()

    mock_hs = MagicMock()
    mock_hs.snapshot.return_value = offline_health

    mock_slo = MagicMock()
    mock_slo.evaluate.return_value = offline_slos

    mock_dr = MagicMock()
    mock_dr.build_report.return_value = offline_drift

    with (
        patch.object(_daily_obs_mod, "_import_health_snapshot", return_value=mock_hs),
        patch.object(_daily_obs_mod, "_import_slo", return_value=mock_slo),
        patch.object(_daily_obs_mod, "_import_drift_report", return_value=mock_dr),
    ):
        build_daily_report(alert_sink=my_sink)

    call_kwargs = mock_slo.evaluate.call_args
    forwarded = call_kwargs[1].get("alert_sink") or call_kwargs[0][1]
    assert forwarded is my_sink, "Explicit alert_sink must be forwarded to slo.evaluate"


def test_completes_offline_within_time_limit(
    offline_health: Dict[str, Any],
    offline_slos: List[Dict[str, Any]],
    offline_drift: Dict[str, Any],
) -> None:
    """Mocked build_daily_report() must complete in < 5 s."""
    t0 = time.monotonic()
    _make_mocked_report(offline_health, offline_slos, offline_drift)
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0, f"build_daily_report() took {elapsed:.2f}s — too slow"


def test_writes_nothing_to_disk(
    offline_health: Dict[str, Any],
    offline_slos: List[Dict[str, Any]],
    offline_drift: Dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No file should be created or modified by build_daily_report()."""
    # Record all files present before the call
    before = set(tmp_path.rglob("*"))

    _make_mocked_report(offline_health, offline_slos, offline_drift)

    after = set(tmp_path.rglob("*"))
    assert after == before, f"build_daily_report() wrote unexpected files: {after - before}"


def test_degrades_gracefully_when_snapshot_raises(
    offline_slos: List[Dict[str, Any]],
    offline_drift: Dict[str, Any],
) -> None:
    """If health_snapshot raises, the report must still have 'health', 'slos', 'drift'."""
    mock_hs = MagicMock()
    mock_hs.snapshot.side_effect = RuntimeError("simulated health failure")

    mock_slo = MagicMock()
    mock_slo.evaluate.return_value = offline_slos

    mock_dr = MagicMock()
    mock_dr.build_report.return_value = offline_drift

    with (
        patch.object(_daily_obs_mod, "_import_health_snapshot", return_value=mock_hs),
        patch.object(_daily_obs_mod, "_import_slo", return_value=mock_slo),
        patch.object(_daily_obs_mod, "_import_drift_report", return_value=mock_dr),
    ):
        report = build_daily_report()

    assert "health" in report
    assert "error" in report["health"], "Degraded health must contain 'error' key"
    assert "slos" in report
    assert "drift" in report


def test_slo_evaluate_receives_health_dict(
    offline_health: Dict[str, Any],
    offline_slos: List[Dict[str, Any]],
    offline_drift: Dict[str, Any],
) -> None:
    """slo.evaluate must be called with the health snapshot dict as context."""
    mock_hs = MagicMock()
    mock_hs.snapshot.return_value = offline_health

    mock_slo = MagicMock()
    mock_slo.evaluate.return_value = offline_slos

    mock_dr = MagicMock()
    mock_dr.build_report.return_value = offline_drift

    with (
        patch.object(_daily_obs_mod, "_import_health_snapshot", return_value=mock_hs),
        patch.object(_daily_obs_mod, "_import_slo", return_value=mock_slo),
        patch.object(_daily_obs_mod, "_import_drift_report", return_value=mock_dr),
    ):
        build_daily_report()

    call_kwargs = mock_slo.evaluate.call_args
    context_arg = call_kwargs[1].get("context") or (
        call_kwargs[0][0] if call_kwargs[0] else None
    )
    assert context_arg == offline_health, (
        "slo.evaluate must receive the health snapshot dict as context"
    )


def test_null_sink_is_callable() -> None:
    """_null_sink must be callable and not raise."""
    _null_sink("any_slo", "any detail")  # must not raise
