"""test_L13_cross_exchange.py — Tests for L13_cross_exchange_ev.py

Six focused tests using in-memory data only — no CSV on disk required for
most cases; one test exercises load_quotes_from_snapshot with a tmp file.
"""
from __future__ import annotations

import csv
import io
import logging
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — import L13 directly
# ---------------------------------------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent
_LOOP_DIR = _TEST_DIR.parent
sys.path.insert(0, str(_LOOP_DIR))

import L13_cross_exchange_ev as L13

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(
    book="BookA",
    market="player_prop_pts",
    player="LeBron James",
    stat="pts",
    side="OVER",
    line=25.5,
    price=-110,
    liquidity=1000.0,
    ts="2026-05-25T18:00:00Z",
) -> L13.ExchangeQuote:
    return L13.ExchangeQuote(
        book=book,
        market=market,
        player=player,
        stat=stat,
        side=side,
        line=line,
        price=price,
        liquidity=liquidity,
        ts=ts,
    )


def _preds(player="LeBron James", stat="pts", p_over=0.55, p_under=0.45) -> dict:
    return {(player, stat): {"p_over": p_over, "p_under": p_under}}


# ---------------------------------------------------------------------------
# Test 1: shop_best_price returns the quote with the highest decimal payout
#          Three quotes at -110, -105, +100 → +100 wins
# ---------------------------------------------------------------------------

def test_shop_best_price_highest_payout():
    """shop_best_price with -110, -105, +100 must return the +100 quote."""
    q_110 = _q(book="BookA", price=-110, liquidity=1000)
    q_105 = _q(book="BookB", price=-105, liquidity=1000)
    q_100 = _q(book="BookC", price=100,  liquidity=1000)

    best = L13.shop_best_price("OVER", [q_110, q_105, q_100])
    assert best.price == 100, f"Expected +100, got {best.price}"


# ---------------------------------------------------------------------------
# Test 2: find_ev_opportunities — model_prob=0.6 at -110 is +EV; at -150 is not
# ---------------------------------------------------------------------------

def test_find_ev_opportunities_positive_and_negative():
    """0.6 prob at -110 should exceed 2% EV; 0.6 prob at -150 should be excluded."""
    # -110 at 0.6: payout=1.909; ev = 0.6*(0.909) - 0.4 = 0.5454 - 0.4 = +0.1454 (14.5%) → included
    q_good = _q(price=-110, liquidity=500)
    opps_good = L13.find_ev_opportunities(
        _preds(p_over=0.60, p_under=0.40),
        [q_good],
        min_ev_pct=2.0,
    )
    assert len(opps_good) == 1
    assert opps_good[0].side == "OVER"
    assert opps_good[0].ev_per_dollar > 0.0

    # -150 at 0.6: payout=1.667; ev = 0.6*(0.667) - 0.4 = 0.400 - 0.4 = 0.000 → right at boundary
    # In practice slightly negative due to rounding; definitely < 2%
    q_bad = _q(price=-150, liquidity=500)
    opps_bad = L13.find_ev_opportunities(
        _preds(p_over=0.60, p_under=0.40),
        [q_bad],
        min_ev_pct=2.0,
    )
    # OVER side: ev_pct ≈ 0% which is below 2.0 — excluded
    # UNDER side: model_prob=0.40 at -150 is also low EV
    for opp in opps_bad:
        assert opp.ev_per_dollar * 100 >= 2.0, (
            f"Unexpected opportunity above threshold: ev={opp.ev_per_dollar:.4f}, side={opp.side}"
        )


# ---------------------------------------------------------------------------
# Test 3: Tie-break on price → higher liquidity wins
# ---------------------------------------------------------------------------

def test_shop_best_price_tiebreak_liquidity():
    """Two +100 quotes: liquidity 100 vs 500 → returns the 500 one."""
    q_low  = _q(book="BookA", price=100, liquidity=100)
    q_high = _q(book="BookB", price=100, liquidity=500)

    best = L13.shop_best_price("OVER", [q_low, q_high])
    assert best.liquidity == 500.0, f"Expected 500 liquidity, got {best.liquidity}"
    assert best.book == "BookB"


# ---------------------------------------------------------------------------
# Test 4: Zero-liquidity quotes are excluded from shopping
# ---------------------------------------------------------------------------

def test_zero_liquidity_excluded():
    """A quote with liquidity=0 must not be returned even if it has the best price."""
    q_zero  = _q(book="DryBook",  price=200, liquidity=0.0)
    q_valid = _q(book="WetBook",  price=-110, liquidity=500.0)

    # find_ev_opportunities filters liquidity > 0 before calling shop_best_price
    opps = L13.find_ev_opportunities(
        _preds(p_over=0.60, p_under=0.40),
        [q_zero, q_valid],
        min_ev_pct=0.0,
    )
    # All opportunities must use the valid quote, not the zero-liquidity one
    for opp in opps:
        assert opp.best_quote.book != "DryBook", (
            "Zero-liquidity quote should not be selected"
        )

    # Also verify shop_best_price itself correctly ranks the positive-liquidity quote
    # when fed directly (caller guarantees positive liquidity upstream)
    best = L13.shop_best_price("OVER", [q_valid])
    assert best.book == "WetBook"


# ---------------------------------------------------------------------------
# Test 5: model_prob=0.999 → WARN logged, opportunity skipped
# ---------------------------------------------------------------------------

def test_extreme_model_prob_skipped(caplog):
    """model_prob=0.999 exceeds safe range → opportunity must be skipped."""
    q = _q(price=-110, liquidity=1000)
    with caplog.at_level(logging.WARNING, logger="L13_cross_exchange_ev"):
        opps = L13.find_ev_opportunities(
            _preds(p_over=0.999, p_under=0.001),
            [q],
            min_ev_pct=0.0,
        )

    # Both sides have extreme probs — both should be skipped
    assert opps == [], f"Expected no opportunities, got {opps}"
    # Warning must have been emitted
    warn_texts = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("out of safe range" in t for t in warn_texts), (
        f"Expected 'out of safe range' warning, got: {warn_texts}"
    )


# ---------------------------------------------------------------------------
# Test 6: load_quotes_from_snapshot parses a fixture CSV correctly
# ---------------------------------------------------------------------------

def test_load_quotes_from_snapshot_fixture():
    """load_quotes_from_snapshot must return correct ExchangeQuote objects from CSV."""
    csv_content = (
        "book,market,player,stat,side,line,price,liquidity,ts\n"
        "DraftKings,player_prop_pts,Stephen Curry,pts,OVER,29.5,-110,2500,2026-05-25T18:00:00Z\n"
        "FanDuel,player_prop_pts,Stephen Curry,pts,OVER,29.5,-105,1800,2026-05-25T18:00:00Z\n"
        "BetMGM,player_prop_pts,Stephen Curry,pts,UNDER,29.5,+100,900,2026-05-25T18:00:00Z\n"
        "DraftKings,player_prop_reb,LeBron James,reb,OVER,7.5,-115,1200,2026-05-25T18:00:00Z\n"
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(csv_content)
        tmp_path = tmp.name

    try:
        quotes = L13.load_quotes_from_snapshot(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    assert len(quotes) == 4, f"Expected 4 quotes, got {len(quotes)}"

    curry_overs = [q for q in quotes if q.player == "Stephen Curry" and q.side == "OVER"]
    assert len(curry_overs) == 2

    curry_under = [q for q in quotes if q.player == "Stephen Curry" and q.side == "UNDER"]
    assert len(curry_under) == 1
    assert curry_under[0].price == 100

    lebron = [q for q in quotes if q.player == "LeBron James"]
    assert len(lebron) == 1
    assert lebron[0].stat == "reb"
    assert lebron[0].line == 7.5
    assert lebron[0].price == -115
    assert lebron[0].liquidity == 1200.0


# ---------------------------------------------------------------------------
# Bonus: american_to_decimal and prob_to_american round-trip sanity
# ---------------------------------------------------------------------------

def test_odds_math_helpers():
    """american_to_decimal and prob_to_american basic sanity checks."""
    # -110 → 1.909...
    assert abs(L13.american_to_decimal(-110) - (1 + 100 / 110)) < 1e-9

    # +150 → 2.5
    assert abs(L13.american_to_decimal(150) - 2.5) < 1e-9

    # prob=0.5 → -100
    assert L13.prob_to_american(0.5) == -100

    # prob=0.6 → -150
    assert L13.prob_to_american(0.6) == -150

    # prob=0.4 → +150
    assert L13.prob_to_american(0.4) == 150


# ---------------------------------------------------------------------------
# Bonus: find_ev_opportunities result is sorted DESC by ev_per_dollar
# ---------------------------------------------------------------------------

def test_find_ev_opportunities_sorted_desc():
    """Returned opportunities must be sorted by ev_per_dollar descending."""
    # Two players: one at +120 (high payout), one at -110
    q1 = _q(player="Player A", stat="pts", price=120, liquidity=1000)
    q2 = _q(player="Player B", stat="pts", price=-110, liquidity=1000)

    preds = {
        ("Player A", "pts"): {"p_over": 0.55, "p_under": 0.45},
        ("Player B", "pts"): {"p_over": 0.55, "p_under": 0.45},
    }

    opps = L13.find_ev_opportunities(preds, [q1, q2], min_ev_pct=0.0)
    ev_values = [o.ev_per_dollar for o in opps]
    assert ev_values == sorted(ev_values, reverse=True), (
        f"Results not sorted DESC: {ev_values}"
    )
    # Player A at +120 has higher EV than Player B at -110
    player_a_opps = [o for o in opps if o.player == "Player A" and o.side == "OVER"]
    player_b_opps = [o for o in opps if o.player == "Player B" and o.side == "OVER"]
    if player_a_opps and player_b_opps:
        assert player_a_opps[0].ev_per_dollar > player_b_opps[0].ev_per_dollar
