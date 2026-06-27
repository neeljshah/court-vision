"""Per-file test for kalshi_edge_finder -- generalized multi-type Kalshi pricing.

Offline. Pins: the YES devig (mid), edge candidates only where a pricer exists + clears
the floor, the YES/NO side from edge sign, honest skip-counting for types with no model,
and the no-$/no-edge-claim envelope.

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/pm_trading/test_kalshi_edge_finder.py -q
"""
from __future__ import annotations

from scripts.platformkit.pm_trading import kalshi_edge_finder as E


def _m(ticker, yb, ya, title=""):
    return {"ticker": ticker, "yes_bid_dollars": yb, "yes_ask_dollars": ya, "title": title}


def test_devig_yes_mid():
    assert E.devig_yes(0.48, 0.50) == 0.49
    assert E.devig_yes(None, 0.5) is None
    assert E.devig_yes(0.6, 0.4) is None        # crossed/one-sided -> None


def test_emits_candidate_when_model_beats_fair():
    # KXMLBTOTAL fair = mid(0.48,0.50)=0.49; model says 0.60 -> +0.11 edge -> YES.
    markets = [_m("KXMLBTOTAL-X-9", 0.48, 0.50, "Total Runs")]
    pricers = {"team_total": lambda m: 0.60}
    out = E.find_edges(markets, pricers)
    assert out["n_candidates"] == 1
    c = out["candidates"][0]
    assert c["side"] == "yes" and c["market_type"] == "team_total"
    assert abs(c["edge"] - 0.11) < 1e-9
    assert c["executed"] is False and c["edge_claimed"] is False


def test_negative_edge_takes_no_side():
    markets = [_m("KXMLBTOTAL-X-9", 0.60, 0.62)]   # fair 0.61
    out = E.find_edges(markets, {"team_total": lambda m: 0.50})  # model below fair -> NO
    assert out["candidates"][0]["side"] == "no"


def test_skips_type_with_no_model():
    # a season-future market we have no model for -> counted as no_model, never priced.
    markets = [_m("KXNHLVEZINA-X", 0.20, 0.22, "Vezina")]
    out = E.find_edges(markets, {"team_total": lambda m: 0.9})
    assert out["n_candidates"] == 0 and out["n_no_model"] == 1


def test_inside_floor_no_candidate():
    markets = [_m("KXMLBTOTAL-X-9", 0.48, 0.50)]   # fair 0.49
    out = E.find_edges(markets, {"team_total": lambda m: 0.50}, edge_floor=0.03)
    assert out["n_candidates"] == 0 and out["n_no_edge"] == 1


def test_pricer_none_is_no_price_not_crash():
    markets = [_m("KXMLBTOTAL-X-9", 0.48, 0.50)]
    out = E.find_edges(markets, {"team_total": lambda m: None})
    assert out["n_candidates"] == 0 and out["n_no_price"] == 1
