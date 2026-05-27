"""Tests for the backtest harness — pure logic, no network."""

from __future__ import annotations

import pytest

from predmarkets.backtest import (
    BacktestConfig,
    _median,
    _settle_pm,
    _simulate_bet,
    _to_unix,
)


def test_median_odd_len() -> None:
    assert _median([1.0, 2.0, 3.0]) == 2.0


def test_median_even_len() -> None:
    assert _median([1.0, 2.0, 3.0, 4.0]) == 2.5


def test_settle_pm_yes_won() -> None:
    assert _settle_pm({"outcomePrices": ["1", "0"]}) is True


def test_settle_pm_no_won() -> None:
    assert _settle_pm({"outcomePrices": ["0", "1"]}) is False


def test_settle_pm_ambiguous_returns_none() -> None:
    assert _settle_pm({"outcomePrices": ["0.5", "0.5"]}) is None
    assert _settle_pm({"outcomePrices": []}) is None


def test_to_unix_handles_iso_z() -> None:
    ts = _to_unix("2026-05-27T12:00:00Z")
    assert ts is not None
    assert ts > 1_000_000_000


def test_to_unix_handles_gamma_space_offset() -> None:
    """Gamma's closedTime format: '2026-05-27 12:13:30+00'."""
    ts = _to_unix("2026-05-27 12:13:30+00")
    assert ts is not None


def test_simulate_bet_below_threshold_skips() -> None:
    cfg = BacktestConfig(edge_threshold=0.10, bankroll=1000.0)
    # Edge is only +0.04 on YES side
    assert _simulate_bet(forecaster_prob=0.34, market_price=0.30, cfg=cfg) is None


def test_simulate_bet_picks_yes_side() -> None:
    cfg = BacktestConfig(edge_threshold=0.05, bankroll=1000.0)
    out = _simulate_bet(forecaster_prob=0.60, market_price=0.40, cfg=cfg)
    assert out is not None
    assert out["side"] == "YES"
    assert out["price"] == pytest.approx(0.40)
    assert out["prob_win"] == pytest.approx(0.60)


def test_simulate_bet_picks_no_side() -> None:
    cfg = BacktestConfig(edge_threshold=0.05, bankroll=1000.0)
    out = _simulate_bet(forecaster_prob=0.30, market_price=0.70, cfg=cfg)
    assert out is not None
    assert out["side"] == "NO"
    assert out["price"] == pytest.approx(0.30)  # 1 - market_price


def test_simulate_bet_respects_per_bet_cap() -> None:
    cfg = BacktestConfig(edge_threshold=0.05, bankroll=1000.0,
                         per_bet_cap=0.01, kelly_fraction_of_full=1.0)
    # Massive edge
    out = _simulate_bet(forecaster_prob=0.90, market_price=0.20, cfg=cfg)
    assert out is not None
    assert out["stake_dollars"] <= 10.01  # 1% of 1000
