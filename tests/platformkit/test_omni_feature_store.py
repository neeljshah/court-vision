"""Tests for scripts.platformkit.omni.feature_store.

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_feature_store.py -q
"""
from __future__ import annotations

import uuid

import pandas as pd
import pytest

from scripts.platformkit.omni import feature_store as fs


@pytest.fixture()
def sport(monkeypatch, tmp_path):
    """Isolate each test to its own tmp store root + a unique sport name."""
    monkeypatch.setattr(fs, "_STORE_ROOT", tmp_path)
    return f"testsport_{uuid.uuid4().hex[:8]}"


def _row(entity, key, value, knowable_at, computed_at="2026-01-01T00:00:00Z", pv="v1"):
    return {
        "entity": entity,
        "key": key,
        "value": value,
        "knowable_at": knowable_at,
        "computed_at": computed_at,
        "pipeline_version": pv,
    }


def test_round_trip(sport):
    df = pd.DataFrame([_row("p1", "pace", 100.0, "2026-01-01T00:00:00Z")])
    n = fs.put_features(sport, df)
    assert n == 1
    out = fs.get_asof(sport, ["p1"], ["pace"], "2026-06-01T00:00:00Z")
    assert len(out) == 1
    assert out.iloc[0]["value"] == 100.0
    assert out.iloc[0]["entity"] == "p1"
    assert out.iloc[0]["key"] == "pace"


def test_leak_guard_future_knowable_at_not_returned(sport):
    df = pd.DataFrame(
        [
            _row("p1", "pace", 90.0, "2026-01-01T00:00:00Z"),
            _row("p1", "pace", 999.0, "2026-12-31T00:00:00Z"),  # future, must not leak
        ]
    )
    fs.put_features(sport, df)
    out = fs.get_asof(sport, ["p1"], ["pace"], "2026-06-01T00:00:00Z")
    assert len(out) == 1
    assert out.iloc[0]["value"] == 90.0  # never the future row


def test_get_asof_returns_latest_visible_row(sport):
    df = pd.DataFrame(
        [
            _row("p1", "pace", 90.0, "2026-01-01T00:00:00Z"),
            _row("p1", "pace", 95.0, "2026-03-01T00:00:00Z"),
        ]
    )
    fs.put_features(sport, df)
    out = fs.get_asof(sport, ["p1"], ["pace"], "2026-06-01T00:00:00Z")
    assert len(out) == 1
    assert out.iloc[0]["value"] == 95.0


def test_missing_coverage_raises(sport):
    df = pd.DataFrame([_row("p1", "pace", 100.0, "2026-01-01T00:00:00Z")])
    fs.put_features(sport, df)
    out = fs.get_asof(sport, ["p1", "p2"], ["pace"], "2026-06-01T00:00:00Z")
    with pytest.raises(ValueError, match="missing feature coverage"):
        fs.assert_coverage(out, ["p1", "p2"], ["pace"])


def test_coverage_passes_when_complete(sport):
    df = pd.DataFrame(
        [
            _row("p1", "pace", 100.0, "2026-01-01T00:00:00Z"),
            _row("p2", "pace", 101.0, "2026-01-01T00:00:00Z"),
        ]
    )
    fs.put_features(sport, df)
    out = fs.get_asof(sport, ["p1", "p2"], ["pace"], "2026-06-01T00:00:00Z")
    fs.assert_coverage(out, ["p1", "p2"], ["pace"])  # must not raise


def test_missing_knowable_at_rejected_at_put(sport):
    df = pd.DataFrame([_row("p1", "pace", 100.0, None)])
    with pytest.raises(ValueError, match="knowable_at"):
        fs.put_features(sport, df)


def test_missing_required_column_rejected_at_put(sport):
    df = pd.DataFrame([{"entity": "p1", "key": "pace", "value": 1.0}])
    with pytest.raises(ValueError, match="missing required columns"):
        fs.put_features(sport, df)
