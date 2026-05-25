"""test_L13_cross_exchange.py — Tests for L13_cross_exchange_ev.py

Six focused tests using in-memory data only — no CSV on disk required for
most cases; one test exercises load_quotes_from_snapshot with a tmp file.
v2 tests cover fetch_quotes_from_paper_clients and the new source kwarg.
"""
from __future__ import annotations

import csv
import io
import logging
import sys
import tempfile
import types
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


# ===========================================================================
# v2 tests — fetch_quotes_from_paper_clients + source="paper_clients"
# ===========================================================================

# ---------------------------------------------------------------------------
# Shared fake orderbook shapes per exchange
# ---------------------------------------------------------------------------

def _make_fake_kalshi_module():
    mod = types.SimpleNamespace()
    mod.get_orderbook = lambda market_id: {
        "yes_bids": [[60, 100]],
        "yes_asks": [[62, 80]],
        "no_bids": [[38, 90]],
        "no_asks": [[40, 70]],
    }
    return mod


def _make_fake_polymarket_module():
    mod = types.SimpleNamespace()
    # PolyOrderbook-like object with asks/bids as list of dicts
    class FakeOB:
        asks = [{"price": 0.55, "size": 200.0}]
        bids = [{"price": 0.53, "size": 150.0}]
    mod.get_orderbook = lambda market_id: FakeOB()
    return mod


def _make_fake_sporttrade_module():
    mod = types.SimpleNamespace()
    mod.get_orderbook = lambda market_id: {
        "asks": [[55, 80]],
        "bids": [[53, 60]],
    }
    return mod


def _make_fake_prophet_module():
    mod = types.SimpleNamespace()
    mod.get_orderbook = lambda market_id: {
        "asks": [[1.90, 50.0]],
        "bids": [[2.10, 40.0]],
    }
    return mod


_FAKE_MODULES = {
    "scripts.execute_loop.L09_kalshi_client":    _make_fake_kalshi_module(),
    "scripts.execute_loop.L10_polymarket_client": _make_fake_polymarket_module(),
    "scripts.execute_loop.L11_sporttrade_client": _make_fake_sporttrade_module(),
    "scripts.execute_loop.L12_prophet_client":   _make_fake_prophet_module(),
}


# ---------------------------------------------------------------------------
# Test v2-1: all four clients succeed → dict has 4 keys
# ---------------------------------------------------------------------------

def test_fetch_quotes_paper_clients_all_succeed(monkeypatch):
    """All four exchange modules succeed → result dict has exactly 4 keys."""
    for module_path, fake_mod in _FAKE_MODULES.items():
        monkeypatch.setitem(sys.modules, module_path, fake_mod)

    result = L13.fetch_quotes_from_paper_clients(
        market_id="test_market",
        player="LeBron James",
        stat="pts",
        line=25.5,
    )

    assert set(result.keys()) == {"kalshi", "polymarket", "sporttrade", "prophet"}, (
        f"Expected all 4 exchanges, got: {set(result.keys())}"
    )
    # Each key must have at least one ExchangeQuote
    for name, qs in result.items():
        assert len(qs) >= 1, f"{name} returned no quotes"
        for q in qs:
            assert isinstance(q, L13.ExchangeQuote), f"{name} returned non-ExchangeQuote: {q}"


# ---------------------------------------------------------------------------
# Test v2-2: one client raises → skips it, returns 3 keys, no exception
# ---------------------------------------------------------------------------

def test_fetch_quotes_skips_failed_client(monkeypatch):
    """If kalshi's get_orderbook raises, it is skipped — 3 keys returned."""
    for module_path, fake_mod in _FAKE_MODULES.items():
        monkeypatch.setitem(sys.modules, module_path, fake_mod)

    # Override kalshi to raise
    broken_kalshi = types.SimpleNamespace()
    broken_kalshi.get_orderbook = lambda market_id: (_ for _ in ()).throw(
        RuntimeError("Kalshi unavailable")
    )
    monkeypatch.setitem(sys.modules, "scripts.execute_loop.L09_kalshi_client", broken_kalshi)

    result = L13.fetch_quotes_from_paper_clients(market_id="test_market")

    assert "kalshi" not in result, "Kalshi should have been skipped on error"
    assert set(result.keys()) == {"polymarket", "sporttrade", "prophet"}, (
        f"Expected 3 exchanges without kalshi, got: {set(result.keys())}"
    )


# ---------------------------------------------------------------------------
# Test v2-3: missing module (sys.modules entry is None) → skips gracefully
# ---------------------------------------------------------------------------

def test_fetch_quotes_skips_missing_module(monkeypatch):
    """If a module entry in sys.modules is None (soft-import miss), it is skipped."""
    for module_path, fake_mod in _FAKE_MODULES.items():
        monkeypatch.setitem(sys.modules, module_path, fake_mod)

    # Setting sys.modules entry to None makes importlib.import_module raise ImportError
    monkeypatch.setitem(sys.modules, "scripts.execute_loop.L09_kalshi_client", None)

    result = L13.fetch_quotes_from_paper_clients(market_id="test_market")

    assert "kalshi" not in result, "kalshi with None module entry should be skipped"
    # Others still succeed
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Test v2-4: find_ev_opportunities source="paper_clients" surfaces +EV opp
# ---------------------------------------------------------------------------

def test_find_ev_opportunities_source_paper_clients(monkeypatch):
    """source='paper_clients' with 1 client returning +120 at 0.55 model_prob → 1 EV opp."""
    # Build a fake module that returns a +120 quote (American)
    # We'll inject a quote via the prophet normalizer path:
    # prophet decimal 2.20 → american +120
    fake_prophet = types.SimpleNamespace()
    fake_prophet.get_orderbook = lambda market_id: {
        "asks": [[2.20, 100.0]],
        "bids": [],
    }
    monkeypatch.setitem(sys.modules, "scripts.execute_loop.L12_prophet_client", fake_prophet)

    # Suppress other exchanges so only prophet succeeds
    for name in ["scripts.execute_loop.L09_kalshi_client",
                 "scripts.execute_loop.L10_polymarket_client",
                 "scripts.execute_loop.L11_sporttrade_client"]:
        broken = types.SimpleNamespace()
        broken.get_orderbook = lambda mid: (_ for _ in ()).throw(RuntimeError("skip"))
        monkeypatch.setitem(sys.modules, name, broken)

    preds = {("LeBron James", "pts"): {"p_over": 0.55, "p_under": 0.45}}
    # +120 at p=0.55: payout=2.2; ev = 0.55*(1.2) - 0.45 = 0.66-0.45 = 0.21 (21%) → included
    opps = L13.find_ev_opportunities(
        preds,
        quotes=[],
        min_ev_pct=2.0,
        source="paper_clients",
        market_id="nba_lebron_pts",
        exchanges=["kalshi", "polymarket", "sporttrade", "prophet"],
    )

    assert len(opps) == 1, f"Expected 1 EV opportunity, got {len(opps)}"
    assert opps[0].side == "OVER"
    assert opps[0].best_quote.book == "prophet"
    assert opps[0].ev_per_dollar > 0.0


# ---------------------------------------------------------------------------
# Test v2-5: parametrized normalizer — each exchange produces valid AmericanOdds ExchangeQuotes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("exchange,orderbook,expected_sides", [
    (
        "kalshi",
        {"yes_bids": [[60, 100]], "yes_asks": [], "no_bids": [[40, 80]], "no_asks": []},
        {"OVER", "UNDER"},
    ),
    (
        "polymarket",
        {"asks": [{"price": 0.55, "size": 200.0}], "bids": []},
        {"OVER", "UNDER"},
    ),
    (
        "sporttrade",
        {"asks": [[55, 80]], "bids": [[53, 60]]},
        {"OVER", "UNDER"},
    ),
    (
        "prophet",
        {"asks": [[1.90, 50.0]], "bids": [[2.10, 40.0]]},
        {"OVER", "UNDER"},
    ),
])
def test_normalizer_produces_valid_exchange_quotes(exchange, orderbook, expected_sides):
    """Each exchange normalizer must produce ExchangeQuotes with valid American odds."""
    normalizer_name = L13._EXCHANGE_REGISTRY[exchange][2]
    normalizer = L13._NORMALIZER_MAP[normalizer_name]

    quotes = normalizer(orderbook, f"{exchange}_mkt", "Player X", "pts", 20.5)

    assert len(quotes) >= 1, f"{exchange} normalizer returned no quotes"
    actual_sides = {q.side for q in quotes}
    assert actual_sides == expected_sides, (
        f"{exchange}: expected sides {expected_sides}, got {actual_sides}"
    )
    for q in quotes:
        assert isinstance(q.price, int), f"{exchange}: price must be int, got {type(q.price)}"
        assert q.price != 0, f"{exchange}: price should not be 0"
        assert q.book == exchange, f"{exchange}: book field mismatch"
        assert q.liquidity >= 0.0


# ---------------------------------------------------------------------------
# Test v2-6: source="snapshot" (default) behaviour unchanged (regression guard)
# ---------------------------------------------------------------------------

def test_find_ev_opportunities_snapshot_default_unchanged():
    """source='snapshot' with a pre-built quotes list still works identically to v1."""
    q = _q(price=120, liquidity=500, player="Stephen Curry", stat="pts", side="OVER")
    preds = {("Stephen Curry", "pts"): {"p_over": 0.55, "p_under": 0.45}}

    # Call without source kwarg (default) and with explicit source="snapshot" — both identical
    opps_default = L13.find_ev_opportunities(preds, [q], min_ev_pct=2.0)
    opps_explicit = L13.find_ev_opportunities(preds, [q], min_ev_pct=2.0, source="snapshot")

    assert len(opps_default) == len(opps_explicit) == 1
    assert opps_default[0].ev_per_dollar == opps_explicit[0].ev_per_dollar
    assert opps_default[0].best_quote.book == "BookA"
