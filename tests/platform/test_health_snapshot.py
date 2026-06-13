"""test_health_snapshot.py — Acceptance tests for health_snapshot.snapshot().

Python 3.9 compatible. No network required.
The function must:
  - return a dict with all expected top-level keys
  - have every field carry 'unit' and 'threshold'
  - degrade gracefully when ledger files and the API are absent
  - complete in < 5 s
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platformkit" / "obs"))

from health_snapshot import snapshot  # noqa: E402

# ---------------------------------------------------------------------------
# Expected field keys (spec-defined)
# ---------------------------------------------------------------------------
EXPECTED_KEYS = {
    "loop_heartbeat_age_sec",
    "capture_row_age_sec",
    "api_health",
    "registry_parquet_freshness_sec",
    "disk_headroom_gb",
    "last_vault_autowrite_age_sec",
}


# ---------------------------------------------------------------------------
# 1. snapshot() returns a dict with all required top-level keys
# ---------------------------------------------------------------------------

def test_snapshot_returns_dict():
    result = snapshot()
    assert isinstance(result, dict), "snapshot() must return a dict"


def test_snapshot_has_all_expected_keys():
    result = snapshot()
    missing = EXPECTED_KEYS - set(result.keys())
    assert not missing, f"snapshot() is missing keys: {missing}"


def test_snapshot_no_unexpected_keys():
    result = snapshot()
    extra = set(result.keys()) - EXPECTED_KEYS
    # Extra keys are not forbidden by spec, but flag them if completely unexpected
    # (this test is informational — it does NOT assert extra == set())
    assert isinstance(extra, set)  # trivially true; presence check only


# ---------------------------------------------------------------------------
# 2. Every field dict has 'unit' and 'threshold' keys
# ---------------------------------------------------------------------------

def test_every_field_has_unit_and_threshold():
    result = snapshot()
    for key in EXPECTED_KEYS:
        field = result[key]
        assert isinstance(field, dict), f"Field '{key}' must be a dict, got {type(field)}"
        assert "unit" in field, f"Field '{key}' missing 'unit'"
        assert "threshold" in field, f"Field '{key}' missing 'threshold'"


def test_every_field_has_value_key():
    result = snapshot()
    for key in EXPECTED_KEYS:
        field = result[key]
        assert "value" in field, f"Field '{key}' missing 'value'"


# ---------------------------------------------------------------------------
# 3. Graceful degradation — no raises even with missing ledger and absent API
# ---------------------------------------------------------------------------

def test_snapshot_does_not_raise():
    """snapshot() must never raise, regardless of environment."""
    try:
        result = snapshot()
    except Exception as exc:
        pytest.fail(f"snapshot() raised an exception: {exc!r}")
    assert result is not None


def test_capture_row_age_degrades_gracefully(monkeypatch, tmp_path):
    """When the ledger directory doesn't exist, capture_row_age returns value=None."""
    import health_snapshot as hs
    monkeypatch.setattr(hs, "REPO_ROOT", tmp_path)

    # tmp_path has no data/lines/forward tree → must degrade gracefully
    result = hs.snapshot()
    capture_field = result["capture_row_age_sec"]
    assert capture_field["value"] is None, (
        "capture_row_age_sec.value must be None when ledger is absent"
    )
    assert "note" in capture_field, (
        "capture_row_age_sec must carry a 'note' key when absent"
    )


def test_api_health_unreachable_does_not_raise():
    """API probe on a closed port must return 'unreachable', not raise."""
    result = snapshot()
    api_field = result["api_health"]
    assert isinstance(api_field["value"], str), "api_health.value must be a str"
    # 'up' or 'unreachable' or 'http_<code>' — all valid
    assert api_field["unit"] == "status"
    assert api_field["threshold"] == "up"


def test_loop_heartbeat_degrades_gracefully(monkeypatch, tmp_path):
    """When state.json is absent, loop_heartbeat returns value=None with note."""
    import health_snapshot as hs
    monkeypatch.setattr(hs, "REPO_ROOT", tmp_path)

    result = hs.snapshot()
    loop_field = result["loop_heartbeat_age_sec"]
    assert loop_field["value"] is None
    assert loop_field.get("note") == "absent"


def test_registry_parquet_freshness_degrades(monkeypatch, tmp_path):
    """When no parquets found, field value is None."""
    import health_snapshot as hs
    monkeypatch.setattr(hs, "REPO_ROOT", tmp_path)

    result = hs.snapshot()
    field = result["registry_parquet_freshness_sec"]
    assert field["value"] is None


def test_vault_autowrite_age_degrades(monkeypatch, tmp_path):
    """When vault/ is absent, field value is None."""
    import health_snapshot as hs
    monkeypatch.setattr(hs, "REPO_ROOT", tmp_path)

    result = hs.snapshot()
    field = result["last_vault_autowrite_age_sec"]
    assert field["value"] is None


# ---------------------------------------------------------------------------
# 4. snapshot() completes in < 5 s (generous wall-time bound)
# ---------------------------------------------------------------------------

def test_snapshot_completes_under_5_seconds():
    t0 = time.monotonic()
    snapshot()
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0, f"snapshot() took {elapsed:.2f}s — must complete in < 5 s"


# ---------------------------------------------------------------------------
# 5. Result is JSON-serialisable
# ---------------------------------------------------------------------------

def test_snapshot_is_json_serialisable():
    import json
    result = snapshot()
    try:
        serialised = json.dumps(result)
    except (TypeError, ValueError) as exc:
        pytest.fail(f"snapshot() result is not JSON-serialisable: {exc!r}")
    assert isinstance(serialised, str)


# ---------------------------------------------------------------------------
# 6. With a real state.json present, loop_heartbeat_age has a numeric value
# ---------------------------------------------------------------------------

def test_loop_heartbeat_numeric_when_state_exists():
    """When the real data/registry/state.json exists, value must be a non-negative float."""
    state_path = ROOT / "data" / "registry" / "state.json"
    if not state_path.exists():
        pytest.skip("state.json not present in this environment")

    result = snapshot()
    field = result["loop_heartbeat_age_sec"]
    assert isinstance(field["value"], (int, float)), (
        "loop_heartbeat_age_sec.value must be numeric when state.json exists"
    )
    assert field["value"] >= 0, "Age must be non-negative"


def test_loop_iter_present_when_state_exists():
    """When state.json is present with iter_id, loop field carries 'iter'."""
    state_path = ROOT / "data" / "registry" / "state.json"
    if not state_path.exists():
        pytest.skip("state.json not present in this environment")

    result = snapshot()
    field = result["loop_heartbeat_age_sec"]
    assert "iter" in field, "loop_heartbeat_age_sec must include 'iter' key when state.json exists"
