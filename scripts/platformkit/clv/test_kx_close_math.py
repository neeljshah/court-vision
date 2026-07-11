"""Per-file tests for scripts.platformkit.clv.kx_close_math (W1 proxy CLV).

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/clv/test_kx_close_math.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.clv import kx_close_math as M


def test_close_decimals_naive_complement():
    ch, ca = M.close_decimals(0.6)
    assert round(ch, 4) == round(1 / 0.6, 4)
    assert round(ca, 4) == round(1 / 0.4, 4)


def test_close_decimals_degenerate_returns_none():
    assert M.close_decimals(0.0) is None
    assert M.close_decimals(1.0) is None
    assert M.close_decimals(None) is None


def test_clv_pct_no_devig_matches_sign_convention():
    # taken_p (implied by the price) > fair close prob -> worse number -> negative CLV.
    pct_bad = M.clv_pct_no_devig("home", 1.5, 0.6)  # taken_p=.667, fair=.6 -> negative
    assert pct_bad < 0.0
    # taken_p < fair close prob -> better number -> positive CLV.
    pct_good = M.clv_pct_no_devig("home", 2.5, 0.6)  # taken_p=.4, fair=.6 -> positive
    assert pct_good > 0.0


def test_clv_pct_no_devig_never_raises_on_shin_style_booksum_1():
    # This is the exact input shape that crashes clv_ledger.compute_clv's
    # Shin devig (booksum==1.0 for a naive complement pair) -- must NOT raise here.
    pct = M.clv_pct_no_devig("home", 1.9, 0.5405405405405406)
    assert pct is not None


def test_clv_pct_no_devig_invalid_side_returns_none():
    assert M.clv_pct_no_devig("draw", 1.9, 0.5) is None


def test_proxy_clv_for_row_hit(monkeypatch):
    def fake_get_close_prob(ticker, sport, **kw):
        assert ticker == "KXMLBGAME-X"
        assert sport == "mlb"
        return {"close_prob": 0.65, "close_ts": "2026-07-01T00:00:00Z"}
    monkeypatch.setattr(M._kx, "get_close_prob", fake_get_close_prob)
    row = {"game_id": "KXMLBGAME-X", "sport": "mlb", "side": "home",
           "taken_decimal": 1.9, "clv_status": "no_close"}
    out = M.proxy_clv_for_row(row)
    assert out is not None
    assert out["clv_status"] == "proxy"
    assert out["clv_is_proxy"] is True
    assert out["clv_pct"] is not None
    assert out["fair_close_prob"] == 0.65
    assert out["close_kind"] == "last_tick"
    assert row["clv_status"] == "no_close"  # original never mutated


def test_proxy_clv_for_row_miss_no_derived_close(monkeypatch):
    monkeypatch.setattr(M._kx, "get_close_prob", lambda t, s, **kw: None)
    row = {"game_id": "KXMLBGAME-Y", "sport": "mlb", "side": "home",
           "taken_decimal": 1.9}
    assert M.proxy_clv_for_row(row) is None


def test_proxy_clv_for_row_missing_ticker_or_sport_returns_none():
    assert M.proxy_clv_for_row({"sport": "mlb", "side": "home", "taken_decimal": 1.9}) is None
    assert M.proxy_clv_for_row({"game_id": "X", "side": "home", "taken_decimal": 1.9}) is None


def test_is_measurable_proxy_requires_proxy_status():
    assert M.is_measurable_proxy(
        {"clv_status": "proxy", "clv_pct": 1.0, "clv_is_proxy": True}) is True
    assert M.is_measurable_proxy(
        {"clv_status": "true_close", "clv_pct": 1.0, "clv_is_proxy": False}) is False
    assert M.is_measurable_proxy(
        {"clv_status": "no_close", "clv_pct": None, "clv_is_proxy": False}) is False


def test_enrich_paper_ingame_no_close_only_touches_target_rows(monkeypatch):
    monkeypatch.setattr(M, "proxy_clv_for_row",
                        lambda r: {**r, "clv_status": "proxy", "clv_pct": 5.0})
    hit = M.enrich_paper_ingame_no_close(
        {"channel": "paper_ingame", "clv_status": "no_close"})
    assert hit["clv_status"] == "proxy"

    # wrong channel -> untouched
    other = {"channel": "paper", "clv_status": "no_close"}
    assert M.enrich_paper_ingame_no_close(other) is other

    # already resolved (true_close) -> untouched
    resolved = {"channel": "paper_ingame", "clv_status": "true_close"}
    assert M.enrich_paper_ingame_no_close(resolved) is resolved


def test_enrich_paper_ingame_no_close_miss_passes_through(monkeypatch):
    monkeypatch.setattr(M, "proxy_clv_for_row", lambda r: None)
    row = {"channel": "paper_ingame", "clv_status": "no_close", "game_id": "X"}
    out = M.enrich_paper_ingame_no_close(row)
    assert out is row
