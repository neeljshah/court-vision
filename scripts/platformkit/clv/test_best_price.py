"""Tests for best_price -- price-edge / CLV detection. Per-file:
python -m pytest scripts/platformkit/clv/test_best_price.py -q
"""
from __future__ import annotations

import math

from scripts.platformkit.clv import best_price as B


def test_sharp_fair_prefers_pinnacle():
    bp = {
        "pinnacle": {"home": 2.0, "away": 2.0},      # fair 50/50
        "softbook": {"home": 5.0, "away": 1.2},      # skewed
    }
    f = B.sharp_fair(bp, "home", "away")
    assert f["source"] == "pinnacle"
    assert abs(f["fair_a"] - 0.5) < 0.02 and abs(f["fair_b"] - 0.5) < 0.02


def test_sharp_fair_median_fallback_without_pinnacle():
    bp = {"a": {"home": 1.9, "away": 1.95}, "b": {"home": 2.0, "away": 1.9}}
    f = B.sharp_fair(bp, "home", "away")
    assert f["source"].startswith("median")
    assert 0.4 < f["fair_a"] < 0.6


def test_best_price_takes_highest_decimal_sportsbook():
    bp = {
        "draftkings": {"home": 2.05, "away": 1.85},
        "fanduel": {"home": 2.12, "away": 1.80},   # better home price
        "pinnacle": {"home": 2.00, "away": 1.95},
    }
    b = B.best_price(bp, "home")
    assert b["book"] == "fanduel" and b["price"] == 2.12


def test_price_edge_positive_when_best_beats_fair():
    # Pinnacle fair ~50/50; a soft book offers home at 2.20 (implied .4545 < .5) = +CLV
    bp = {
        "pinnacle": {"home": 2.0, "away": 2.0},
        "softbook": {"home": 2.20, "away": 1.70},
    }
    pe = B.price_edge(bp, "home", "away", "home")
    assert pe["is_value"] is True
    assert pe["expected_clv_pct"] > 0
    assert pe["best_book"] == "softbook" and pe["best_price"] == 2.20


def test_price_edge_negative_when_no_book_beats_fair():
    # Vigged sharp (1.90/1.90 -> fair ~.5 but implied .526); best book is no better,
    # so taking it pays the vig = negative CLV vs the no-vig fair.
    bp = {"pinnacle": {"home": 1.90, "away": 1.90},
          "soft": {"home": 1.85, "away": 1.88}}
    pe = B.price_edge(bp, "home", "away", "home")
    assert pe["is_value"] is False
    assert pe["expected_clv_pct"] < 0


def test_value_bets_ranks_and_filters():
    games = [
        {"matchup": "A@B", "side_a": "home", "side_b": "away",
         "book_prices": {"pinnacle": {"home": 2.0, "away": 2.0},
                         "soft": {"home": 2.30, "away": 1.65}}},   # big home value
        {"matchup": "C@D", "side_a": "home", "side_b": "away",
         "book_prices": {"pinnacle": {"home": 2.0, "away": 2.0},
                         "soft": {"home": 1.80, "away": 1.80}}},   # no value
    ]
    vb = B.value_bets(games, min_clv_pct=1.0)
    assert len(vb) == 1
    assert vb[0]["matchup"] == "A@B" and vb[0]["side"] == "home"


def test_missing_two_way_degrades_to_none():
    assert B.price_edge({"x": {"home": 2.0}}, "home", "away", "home") is None


# --- NaN / inf robustness (the non-finite leak fix) ---

def test_both_rejects_nan_price():
    """_both must return None when either price is NaN."""
    # Access the private helper via the module for a focused unit test.
    assert B._both({"home": float("nan"), "away": 2.0}, "home", "away") is None
    assert B._both({"home": 2.0, "away": float("nan")}, "home", "away") is None
    assert B._both({"home": float("nan"), "away": float("nan")}, "home", "away") is None


def test_both_rejects_inf_price():
    """_both must return None when either price is inf."""
    assert B._both({"home": float("inf"), "away": 2.0}, "home", "away") is None
    assert B._both({"home": 2.0, "away": float("inf")}, "home", "away") is None
    assert B._both({"home": float("-inf"), "away": 2.0}, "home", "away") is None


def test_sharp_fair_nan_book_does_not_poison_median():
    """A book quoting NaN on one side must be silently dropped; the other
    valid book must still produce a finite fair via the median fallback."""
    bp = {
        "bad_book": {"home": float("nan"), "away": 1.95},  # NaN side -- drop whole row
        "good_book": {"home": 1.91, "away": 1.91},         # valid two-way
    }
    f = B.sharp_fair(bp, "home", "away")
    assert f is not None, "sharp_fair must not return None when a valid book exists"
    assert math.isfinite(f["fair_a"]), "fair_a must be finite (not NaN)"
    assert math.isfinite(f["fair_b"]), "fair_b must be finite (not NaN)"
    assert 0.4 < f["fair_a"] < 0.6, "fair must be roughly 50/50"


def test_sharp_fair_inf_book_does_not_poison_median():
    """A book quoting inf must be dropped; remaining books still yield finite fair."""
    bp = {
        "inf_book": {"home": float("inf"), "away": 1.90},
        "ok_book1": {"home": 1.95, "away": 1.95},
        "ok_book2": {"home": 1.90, "away": 2.00},
    }
    f = B.sharp_fair(bp, "home", "away")
    assert f is not None
    assert math.isfinite(f["fair_a"]) and math.isfinite(f["fair_b"])


def test_value_bets_nan_book_does_not_crash_or_nan_clv():
    """value_bets on a slate where one book has a NaN quote must not crash and
    must not return NaN expected_clv_pct for the game."""
    games = [
        {
            "matchup": "X@Y",
            "side_a": "home",
            "side_b": "away",
            "book_prices": {
                "pinnacle": {"home": 2.0, "away": 2.0},      # sharp anchor is clean
                "nan_book": {"home": float("nan"), "away": 1.80},  # poison book
                "soft": {"home": 2.10, "away": 1.75},         # valid soft
            },
        }
    ]
    results = B.value_bets(games, min_clv_pct=0.0)
    for r in results:
        assert math.isfinite(r["expected_clv_pct"]), (
            "expected_clv_pct must be finite, got %r" % r["expected_clv_pct"]
        )
