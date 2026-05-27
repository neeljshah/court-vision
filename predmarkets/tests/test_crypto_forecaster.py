"""Unit tests for CryptoThresholdForecaster — math + parsing, no network."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from predmarkets.forecasters.crypto_threshold import (
    _gbm_prob_above,
    _gbm_prob_touch,
    _parse_date,
    _parse_price,
    _parse_question,
    _phi,
)


# -------- math --------------------------------------------------------------


def test_phi_at_zero_is_half() -> None:
    assert _phi(0.0) == pytest.approx(0.5, abs=1e-10)


def test_phi_at_one_is_known_value() -> None:
    assert _phi(1.0) == pytest.approx(0.8413447, abs=1e-5)


def test_gbm_prob_above_at_strike_drift_zero_below_half() -> None:
    # Risk-neutral GBM with drift=0 is a martingale on the price, NOT on the
    # log-price. Lognormal is right-skewed so median < mean — P(S_T > S_0) < 0.5
    # at expiry. With sigma=0.5, T=0.25: d = -0.125, N(-0.125) ~ 0.45.
    p = _gbm_prob_above(spot=100.0, strike=100.0, sigma_annual=0.5, years=0.25)
    assert 0.40 < p < 0.50

    # Add a vol-drag-cancelling drift (0.5 * sigma^2) and we should land at 0.5.
    p2 = _gbm_prob_above(spot=100.0, strike=100.0, sigma_annual=0.5, years=0.25,
                         drift=0.5 * 0.5 ** 2)
    assert p2 == pytest.approx(0.5, abs=1e-6)


def test_gbm_prob_above_high_strike_low_prob() -> None:
    # Strike 2x spot in 30 days with 50% annualized vol — should be quite small.
    p = _gbm_prob_above(spot=100.0, strike=200.0, sigma_annual=0.50, years=30/365)
    assert 0.0 < p < 0.05


def test_gbm_prob_touch_at_least_terminal() -> None:
    # P(touch >= K) is always >= P(end above K).
    sp, k, sig, t = 100.0, 130.0, 0.6, 60 / 365.0
    p_touch = _gbm_prob_touch(sp, k, sig, t)
    p_term = _gbm_prob_above(sp, k, sig, t)
    assert p_touch >= p_term - 1e-9


def test_gbm_prob_touch_already_above_is_one() -> None:
    p = _gbm_prob_touch(spot=120.0, strike=100.0, sigma_annual=0.5, years=0.1)
    assert p == 1.0


def test_gbm_prob_touch_below_already_below_is_one() -> None:
    p = _gbm_prob_touch(spot=80.0, strike=100.0, sigma_annual=0.5, years=0.1,
                        direction="below")
    assert p == 1.0


# -------- price parsing -----------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("Will Bitcoin be above $150,000 by June 30?", 150_000.0),
    ("Will BTC hit $85k in May?", 85_000.0),
    ("Will ETH dip to $1,800", 1_800.0),
    ("Bitcoin reaches $100K", 100_000.0),
    ("Solana above $300.50 by Q3", 300.50),
    # Regression: '$72,000 May 25-31?' must NOT eat the 'M' from May as a suffix.
    ("Will Bitcoin dip to $72,000 May 25-31?", 72_000.0),
    ("Will Bitcoin dip to $72,000 Mar 25?", 72_000.0),
])
def test_parse_price(text: str, expected: float) -> None:
    assert _parse_price(text) == pytest.approx(expected)


def test_parse_price_missing() -> None:
    assert _parse_price("Will Bitcoin keep going up?") is None


# -------- question parsing --------------------------------------------------


def test_parse_question_bitcoin_terminal() -> None:
    p = _parse_question("Will the price of Bitcoin be above $80,000 on May 27?")
    assert p is not None
    assert p.asset_id == "bitcoin"
    assert p.strike == pytest.approx(80_000.0)
    assert p.direction == "above"


def test_parse_question_ethereum_touch() -> None:
    p = _parse_question("Will Ethereum reach $5,000 by June 30, 2026?")
    assert p is not None
    assert p.asset_id == "ethereum"
    assert p.strike == pytest.approx(5_000.0)
    assert p.is_touch is True


def test_parse_question_below() -> None:
    p = _parse_question("Will BTC dip to $70,000 in May?")
    assert p is not None
    assert p.direction == "below"


def test_parse_question_rejects_non_crypto() -> None:
    """The 'eth' substring inside 'Netherlands' must not match — word boundaries."""
    p = _parse_question("Will Netherlands win the 2026 FIFA World Cup?")
    assert p is None


def test_parse_question_no_strike_returns_none() -> None:
    assert _parse_question("Will Bitcoin keep rising forever?") is None


@pytest.mark.parametrize("question", [
    "Will the price of Bitcoin be between $70,000 and $72,000 on May 27?",
    "Will Bitcoin land in the range $70k-$80k?",
    "Will ETH stay $1,800-$2,000 by Friday?",
])
def test_parse_question_skips_range_markets(question: str) -> None:
    """Range markets ('between A and B') are multi-strike — the single-strike
    parser must skip them rather than mis-pricing as 'above A'."""
    assert _parse_question(question) is None


def test_parse_question_uses_market_end_date_when_supplied() -> None:
    p = _parse_question(
        "Will Bitcoin hit $200,000?",
        end_date_iso="2027-01-01T05:00:00Z",
    )
    assert p is not None
    expected = datetime(2027, 1, 1, 5, 0, tzinfo=timezone.utc).timestamp()
    assert p.resolution_ts == pytest.approx(expected, abs=1.0)


# -------- end-to-end (offline) ---------------------------------------------


def test_forecaster_applies_to_only_crypto_category() -> None:
    from predmarkets.forecasters.crypto_threshold import CryptoThresholdForecaster
    fc = CryptoThresholdForecaster()
    assert not fc.applies_to({"category": "Sports", "question_or_title": "Will BTC hit $150k?"})
    assert fc.applies_to({
        "category": "Crypto",
        "question_or_title": "Will Bitcoin hit $150,000 by June 30, 2026?",
        "end_date": "2026-06-30T05:00:00Z",
    })


def test_forecaster_terminal_above() -> None:
    """Inject mocked spot+vol; verify end-to-end Forecast produced."""
    from predmarkets.forecasters.crypto_threshold import CryptoThresholdForecaster
    fc = CryptoThresholdForecaster()
    fc._spot_cache["bitcoin"] = 70_000.0
    fc._vol_cache["bitcoin"] = 0.5
    forecast = fc.forecast({
        "market_id": "M1",
        "category": "Crypto",
        "question_or_title": "Will the price of Bitcoin be above $80,000 on December 31?",
        "end_date": "2026-12-31T05:00:00Z",
    })
    assert forecast is not None
    assert 0.05 < forecast.prob_yes < 0.95
    assert forecast.model_name == "crypto_threshold_gbm"
    assert "GBM BTC spot=$70,000" in forecast.reasoning
