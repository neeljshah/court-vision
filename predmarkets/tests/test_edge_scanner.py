"""Unit tests for EdgeScanner — pure logic, no network."""

from __future__ import annotations

import pytest

from predmarkets.edge_scanner import (
    EdgeScanner,
    EdgeScannerConfig,
    Forecast,
    Forecaster,
    ManualForecaster,
    _kelly_fraction,
    _walk_book,
    market_implied_yes_prob,
)


def _market(market_id: str, yes_bid: float, yes_ask: float, category: str = "Test",
            volume: float = 1_000.0, status: str = "open") -> dict:
    return {
        "venue": "test",
        "market_id": market_id,
        "question_or_title": f"Test market {market_id}",
        "category": category,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "volume": volume,
        "status": status,
    }


def test_kelly_fraction_positive_edge() -> None:
    # 60% model probability, buying at 0.50: b = 1, f* = (1*0.6 - 0.4)/1 = 0.20
    assert _kelly_fraction(0.6, 0.5) == pytest.approx(0.2)


def test_kelly_fraction_negative_edge_returns_zero() -> None:
    assert _kelly_fraction(0.4, 0.5) == 0.0


def test_kelly_fraction_degenerate_price() -> None:
    assert _kelly_fraction(0.5, 0.0) == 0.0
    assert _kelly_fraction(0.5, 1.0) == 0.0


def test_market_implied_yes_prob_mid() -> None:
    m = {"yes_bid": 0.4, "yes_ask": 0.5}
    assert market_implied_yes_prob(m) == pytest.approx(0.45)


def test_market_implied_yes_prob_fallback_to_last() -> None:
    m = {"last_price": 0.55}
    assert market_implied_yes_prob(m) == 0.55


def test_walk_book_unconstrained_fill() -> None:
    # Buying YES at best 0.50 with 0.02 slip cap, $100 stake; deep book at 0.50.
    book = [(0.50, 1000.0), (0.51, 500.0)]
    walk = _walk_book(book, best_price=0.50, max_slip_pp=0.02, bankroll_dollars=1000.0, stake_dollars=100.0)
    assert walk["capped_by_slippage"] is False
    assert walk["effective_price"] == pytest.approx(0.50)
    assert walk["contracts_fillable"] == pytest.approx(200.0)


def test_walk_book_slippage_cap_kicks_in() -> None:
    book = [(0.50, 10.0), (0.55, 10.0), (0.60, 100.0)]
    walk = _walk_book(book, best_price=0.50, max_slip_pp=0.02, bankroll_dollars=1000.0, stake_dollars=100.0)
    # First level fills 10@0.50 = $5. Second @0.55 exceeds cap 0.52 -> stop.
    assert walk["capped_by_slippage"] is True
    assert walk["contracts_fillable"] == pytest.approx(10.0)
    assert walk["effective_price"] == pytest.approx(0.50)


def test_edge_scanner_finds_yes_edge() -> None:
    markets = [_market("A", 0.40, 0.45)]
    forecaster = ManualForecaster({"A": 0.65}, confidence=0.7)
    scanner = EdgeScanner([forecaster], EdgeScannerConfig(bankroll=1000.0, edge_threshold=0.05))
    out = scanner.scan(markets)
    assert out["n_edges"] == 1
    edge = out["edges"][0]
    assert edge["side"] == "YES"
    assert edge["price"] == 0.45
    assert edge["model_prob"] == 0.65
    assert edge["edge_pp"] == pytest.approx(0.20)
    assert edge["stake_dollars"] > 0
    assert edge["expected_value_dollars"] > 0


def test_edge_scanner_finds_no_edge_when_model_says_no() -> None:
    markets = [_market("B", 0.55, 0.60)]
    forecaster = ManualForecaster({"B": 0.20})
    scanner = EdgeScanner([forecaster], EdgeScannerConfig(edge_threshold=0.05))
    out = scanner.scan(markets)
    assert out["n_edges"] == 1
    edge = out["edges"][0]
    # buying NO at 1 - 0.55 = 0.45, model says NO at 0.80 -> edge 0.35
    assert edge["side"] == "NO"
    assert edge["price"] == pytest.approx(0.45)
    assert edge["edge_pp"] == pytest.approx(0.35)


def test_edge_scanner_respects_threshold() -> None:
    markets = [_market("C", 0.40, 0.45)]
    forecaster = ManualForecaster({"C": 0.50})  # only 0.05 edge
    scanner = EdgeScanner([forecaster], EdgeScannerConfig(edge_threshold=0.10))
    assert scanner.scan(markets)["n_edges"] == 0


def test_edge_scanner_per_bet_cap() -> None:
    markets = [_market("D", 0.20, 0.25)]
    forecaster = ManualForecaster({"D": 0.95})  # huge edge
    scanner = EdgeScanner([forecaster], EdgeScannerConfig(
        bankroll=1000.0,
        per_bet_cap=0.01,
        kelly_fraction_of_full=1.0,
    ))
    edge = scanner.scan(markets)["edges"][0]
    assert edge["stake_dollars"] == pytest.approx(10.0)  # 1% of 1000


def test_edge_scanner_category_cap_across_bets() -> None:
    # Three markets in the same category each with strong edges; per-category
    # cap should sum the first N stakes and zero the rest.
    markets = [
        _market("M1", 0.20, 0.25, category="Crypto"),
        _market("M2", 0.20, 0.25, category="Crypto"),
        _market("M3", 0.20, 0.25, category="Crypto"),
    ]
    forecaster = ManualForecaster({"M1": 0.90, "M2": 0.90, "M3": 0.90})
    cfg = EdgeScannerConfig(
        bankroll=1000.0,
        per_bet_cap=0.05,
        per_category_cap=0.08,   # only $80 across the category
        kelly_fraction_of_full=1.0,
    )
    out = EdgeScanner([forecaster], cfg).scan(markets)
    total = sum(e["stake_dollars"] for e in out["edges"])
    assert total <= 80.01, f"category cap breached: total={total}"


def test_edge_scanner_skips_closed_markets() -> None:
    m = _market("X", 0.10, 0.15, status="resolved")
    forecaster = ManualForecaster({"X": 0.90})
    out = EdgeScanner([forecaster]).scan([m])
    assert out["n_edges"] == 0


def test_forecast_validates_probability() -> None:
    with pytest.raises(ValueError):
        Forecast(market_id="A", prob_yes=1.5, confidence=0.5, model_name="bad")
    with pytest.raises(ValueError):
        Forecast(market_id="A", prob_yes=0.5, confidence=2.0, model_name="bad")
