"""Per-file test for latency_scoreboard.event_reactive_supported (fail-closed).

Run: python -m pytest tests/platformkit/ingame/test_latency_scoreboard.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import latency_scoreboard as lsb


def test_fail_closed_on_missing_measurement(monkeypatch):
    monkeypatch.setattr(lsb.latency, "measure_sport",
                        lambda sport, grade_dir=None: {})
    assert lsb.event_reactive_supported("mlb") is False


def test_supported_when_fast_and_covered(monkeypatch):
    monkeypatch.setattr(lsb.latency, "measure_sport",
                        lambda sport, grade_dir=None: {
                            "lag_p90_sec": 3.2, "src_ts_coverage_pct": 99.0})
    assert lsb.event_reactive_supported("mlb") is True


def test_rejected_when_lag_too_slow(monkeypatch):
    monkeypatch.setattr(lsb.latency, "measure_sport",
                        lambda sport, grade_dir=None: {
                            "lag_p90_sec": 45.0, "src_ts_coverage_pct": 99.0})
    assert lsb.event_reactive_supported("nba") is False


def test_rejected_when_coverage_too_low(monkeypatch):
    monkeypatch.setattr(lsb.latency, "measure_sport",
                        lambda sport, grade_dir=None: {
                            "lag_p90_sec": 2.0, "src_ts_coverage_pct": 40.0})
    assert lsb.event_reactive_supported("soccer") is False


def test_fail_closed_on_measurement_error(monkeypatch):
    def _boom(sport, grade_dir=None):
        raise RuntimeError("corpus unreadable")

    monkeypatch.setattr(lsb.latency, "measure_sport", _boom)
    assert lsb.event_reactive_supported("mlb") is False
