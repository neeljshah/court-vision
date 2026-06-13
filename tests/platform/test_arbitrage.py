"""tests/platform/test_arbitrage.py — unit tests for
scripts.platformkit.frontend.arbitrage.

Synthetic in-memory dicts only — NO parquet, NO adapters, NO slow loads.
Coverage: odds conversions · devig_* sum-to-one · arbitrage detect/stake-split/
none/single-book · middles total/free-arb/rejects · slate graceful degrade ·
no banned words · no src/kernel import.

Run:  python -m pytest tests/platform/test_arbitrage.py -q
"""
from __future__ import annotations

import inspect
import json

from scripts.platformkit.frontend.arbitrage import (
    ARB_VALUE_LABEL, DEVIG_LABEL, INSUFFICIENT_BOOKS_NOTE, MIDDLE_VALUE_LABEL,
    american_to_decimal, decimal_to_implied, detect_arbitrage, detect_middles,
    devig_fair_probs, devig_multiplicative, devig_power, devig_proportional,
    devig_shin, implied_to_decimal, scan_slate,
)
from scripts.platformkit.frontend import arbitrage as arb_mod

_BANNED = ("guaranteed", "beat the market", "+ev edge", "profit", "lock")


# --- helpers ----------------------------------------------------------------
def _ml_game(home_book_dec, away_book_dec, *, two_books=True, eid="g1"):
    books = [
        {"book": "A", "side": "home", "decimal_odds": home_book_dec, "line": None},
        {"book": "B" if two_books else "A", "side": "away",
         "decimal_odds": away_book_dec, "line": None},
    ]
    return {
        "event_id": eid, "sport": "basketball_nba", "commence_time": None,
        "home": "H", "away": "A",
        "markets": {"moneyline": {"outcomes": ["home", "away"], "books": books}},
    }


# --- odds conversions -------------------------------------------------------
def test_american_to_decimal():
    assert abs(american_to_decimal(120) - 2.20) < 1e-9
    assert abs(american_to_decimal(-110) - (1.0 + 100.0 / 110.0)) < 1e-9
    assert american_to_decimal(None) is None
    assert american_to_decimal(0) is None
    assert american_to_decimal("nope") is None


def test_decimal_to_implied():
    assert abs(decimal_to_implied(2.0) - 0.5) < 1e-9
    assert decimal_to_implied(None) is None
    assert decimal_to_implied(0) is None


def test_implied_to_decimal():
    assert abs(implied_to_decimal(0.5) - 2.0) < 1e-9
    assert implied_to_decimal(None) is None
    assert implied_to_decimal(0) is None


# --- devig sums-to-one ------------------------------------------------------
def test_devig_proportional_sums_to_one():
    out = devig_proportional([0.55, 0.52])
    assert abs(sum(out) - 1.0) < 1e-9


def test_devig_multiplicative_two_way_sums_to_one():
    out = devig_multiplicative([0.55, 0.52])
    assert abs(sum(out) - 1.0) < 1e-9
    assert len(out) == 2


def test_devig_power_three_way_sums_to_one():
    out = devig_power([0.40, 0.40, 0.30])
    assert abs(sum(out) - 1.0) < 1e-9
    assert len(out) == 3


def test_devig_shin_pair_sums_to_one():
    out = devig_shin([0.55, 0.52])
    assert abs(sum(out) - 1.0) < 1e-9


def test_devig_no_vig_passthrough_unchanged():
    """Already-fair [0.5,0.5] passes through unchanged for every method."""
    for fn in (devig_proportional, devig_multiplicative, devig_power, devig_shin):
        out = fn([0.5, 0.5])
        assert abs(out[0] - 0.5) < 1e-9 and abs(out[1] - 0.5) < 1e-9


def test_devig_fair_probs_structure():
    res = devig_fair_probs(
        [{"side": "over", "decimal_odds": 1.91}, {"side": "under", "decimal_odds": 1.91}],
        method="multiplicative",
    )
    assert res["method"] == "multiplicative"
    assert abs(sum(res["fair_probs"].values()) - 1.0) < 1e-9
    assert res["overround"] > 0.0
    assert res["label"] == DEVIG_LABEL


# --- arbitrage --------------------------------------------------------------
def test_detect_arbitrage_positive():
    res = detect_arbitrage(_ml_game(2.10, 2.10))
    assert res is not None
    assert abs(res["return_pct"] - 5.0) < 1e-9
    assert abs(sum(leg["stake_fraction"] for leg in res["legs"]) - 1.0) < 1e-9
    assert res["label"] == ARB_VALUE_LABEL


def test_detect_arbitrage_stake_split_equal_payout():
    """stake_fraction_i * decimal_i equal across legs (locked equal payout)."""
    res = detect_arbitrage(_ml_game(2.30, 1.95))
    assert res is not None
    payouts = [leg["stake_fraction"] * leg["decimal_odds"] for leg in res["legs"]]
    assert abs(payouts[0] - payouts[1]) < 1e-9


def test_detect_arbitrage_none_when_no_gap():
    assert detect_arbitrage(_ml_game(1.90, 1.90)) is None


def test_detect_arbitrage_single_book_none():
    assert detect_arbitrage(_ml_game(2.10, 2.10, two_books=False)) is None


# --- middles ----------------------------------------------------------------
def _total_game(over, under):
    books = [
        {"book": "A", "side": "over", "decimal_odds": over[1], "line": over[0]},
        {"book": "B", "side": "under", "decimal_odds": under[1], "line": under[0]},
    ]
    return {
        "event_id": "g2", "sport": "basketball_nba", "commence_time": None,
        "home": "H", "away": "A",
        "markets": {"total": {"outcomes": ["over", "under"], "books": books}},
    }


def test_detect_middles_total():
    res = detect_middles(_total_game((24.5, 1.95), (25.5, 1.95)))
    assert len(res) == 1
    assert abs(res[0]["width"] - 1.0) < 1e-9
    assert res[0]["is_free_arb"] is False
    assert res[0]["label"] == MIDDLE_VALUE_LABEL


def test_detect_middles_free_arb_flag():
    res = detect_middles(_total_game((24.5, 2.10), (25.5, 2.10)))
    assert len(res) == 1
    assert res[0]["is_free_arb"] is True
    assert res[0]["arb_return_pct"] is not None and res[0]["arb_return_pct"] > 0


def test_detect_middles_rejects_same_book_and_below_min_width():
    # Same book for both legs -> rejected.
    same_book = {
        "event_id": "g3", "sport": "s", "commence_time": None, "home": None, "away": None,
        "markets": {"total": {"outcomes": ["over", "under"], "books": [
            {"book": "A", "side": "over", "decimal_odds": 2.0, "line": 24.5},
            {"book": "A", "side": "under", "decimal_odds": 2.0, "line": 25.5},
        ]}},
    }
    assert detect_middles(same_book) == []
    # Width below min_width (0.5) -> rejected (over 24.5 / under 24.8 = 0.3).
    assert detect_middles(_total_game((24.5, 1.95), (24.8, 1.95))) == []


# --- slate scan -------------------------------------------------------------
def test_scan_slate_degrades_gracefully():
    single = _ml_game(2.10, 2.10, two_books=False)
    res = scan_slate([single])
    assert res["arbitrage"] == []
    assert res["middles"] == []
    assert res["n_multibook_games"] == 0
    assert res["note"] == INSUFFICIENT_BOOKS_NOTE


def test_scan_slate_finds_multibook_arb():
    res = scan_slate([_ml_game(2.10, 2.10)])
    assert res["n_multibook_games"] == 1
    assert len(res["arbitrage"]) == 1
    assert len(res["devig"]) == 1


def test_scan_slate_no_banned_words():
    res = scan_slate([_ml_game(2.10, 2.10), _total_game((24.5, 2.10), (25.5, 2.10)),
                      _ml_game(2.10, 2.10, two_books=False)])
    low = json.dumps(res).lower()
    for w in _BANNED:
        assert w not in low
    assert "not model alpha" in res["value_class"].lower()


def test_module_strings_no_banned_words():
    low = json.dumps([ARB_VALUE_LABEL, MIDDLE_VALUE_LABEL, DEVIG_LABEL,
                      INSUFFICIENT_BOOKS_NOTE]).lower()
    for w in _BANNED:
        assert w not in low


def test_no_src_or_kernel_import():
    source = inspect.getsource(arb_mod)
    assert "from src" not in source
    assert "import src" not in source
    assert "kernel" not in source
    assert "import numpy" not in source
