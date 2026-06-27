"""Per-file test: frontend.edge_api -- fresh TOTAL/SPREAD line merge.

A canonical snapshot often carries ONLY moneyline (the model prices ML). The
captured line history, however, holds fresh TOTAL and SPREAD (run-line) book
quotes for the SAME game. build_edge_view must merge those captured quotes in so
total/spread surface as their own comparison rows -- WITHOUT clobbering the
snapshot's vetted moneyline rows and WITHOUT fabricating anything.

Asserts:
  * a snapshot with only moneyline + a (patched) line store carrying total/spread
    yields comparison rows for moneyline AND total AND spread;
  * the snapshot's moneyline row is the vetted one (not overridden by the store);
  * total/spread rows carry the captured line + best_book + market_prob and have
    model_prob None (the model did not price them -- never fabricated);
  * when the line store returns {} the view is moneyline-only (no fabrication);
  * NO dollar / $ key anywhere.

Run: cd /c/Users/neelj/nba-ai-system && \
  python -m pytest tests/frontend/test_edge_api_line_merge.py -q
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

import frontend.edge_api as edge_mod
from frontend.edge_api import build_edge_view
from predict_service import store
from predict_service.contracts import MarketRow, PredictionRecord, SnapshotEnvelope

_SPORT = "nba"
_GID = "tst_line_merge_1"
_GEN_AT = "2026-06-20T22:01:00+00:00"
_FORBIDDEN = ("$", "dollar", "roi", "pnl", "profit", "bankroll")


def _envelope() -> SnapshotEnvelope:
    m_home = MarketRow(sport=_SPORT, game_id=_GID, market_type="moneyline",
                       side="home", line=None, odds=2.10, book="espn:DK",
                       devigged_prob=0.460, captured_at="2026-06-20T22:00:00+00:00",
                       is_close=False, clv_is_proxy=True)
    m_away = MarketRow(sport=_SPORT, game_id=_GID, market_type="moneyline",
                       side="away", line=None, odds=1.80, book="espn:DK",
                       devigged_prob=0.540, captured_at="2026-06-20T22:00:00+00:00",
                       is_close=False, clv_is_proxy=True)
    record = PredictionRecord(
        sport=_SPORT, game_id=_GID, home="Home", away="Away",
        tipoff="2026-06-20T23:30:00+00:00",
        pregame_probs={"home_ml": 0.52, "away_ml": 0.48},
        markets=[m_home, m_away], leak_guard={"in_sample": False},
        produced_at="2026-06-20T21:00:00+00:00")
    return SnapshotEnvelope(sport=_SPORT, generated_at=_GEN_AT, status="ok",
                            predictions=[record], markets=[m_home, m_away],
                            edges=[])


def _fresh_quotes() -> Dict[Any, Dict[str, Any]]:
    """What a patched line_store.get_latest returns: ML + total + spread."""
    return {
        ("moneyline", "home"): {"book": "espn:OTHER", "line": None, "odds": 9.9,
                                "devigged_prob": 0.10,
                                "captured_at": "2026-06-20T22:05:00+00:00"},
        ("total", "over"): {"book": "Pinnacle", "line": 216.5, "odds": 1.93,
                            "devigged_prob": 0.495,
                            "captured_at": "2026-06-20T22:05:00+00:00"},
        ("total", "under"): {"book": "Pinnacle", "line": 216.5, "odds": 1.89,
                             "devigged_prob": 0.505,
                             "captured_at": "2026-06-20T22:05:00+00:00"},
        ("spread", "home"): {"book": "Pinnacle", "line": -5.5, "odds": 1.93,
                             "devigged_prob": 0.495,
                             "captured_at": "2026-06-20T22:05:00+00:00"},
        ("spread", "away"): {"book": "Pinnacle", "line": 5.5, "odds": 1.89,
                             "devigged_prob": 0.505,
                             "captured_at": "2026-06-20T22:05:00+00:00"},
    }


@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    store.save(_envelope(), out_dir=tmp_path, append=False)
    monkeypatch.setattr(edge_mod, "_freshness",
                        lambda *a, **k: {"status": "fresh", "age_sec": 60.0})
    return tmp_path


def _no_money(obj: Any) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            for bad in _FORBIDDEN:
                assert bad not in str(k).lower(), "forbidden key %r" % k
            _no_money(v)
    elif isinstance(obj, list):
        for i in obj:
            _no_money(i)


def test_total_spread_merge_into_comparison(store_dir, monkeypatch):
    monkeypatch.setattr(edge_mod, "_fresh_line_quotes",
                        lambda gid: _fresh_quotes())
    view = build_edge_view(_SPORT, store_out_dir=store_dir)
    comp = view["games"][0]["comparison"]
    by_market = {}
    for r in comp:
        by_market.setdefault(r["market_type"], []).append(r)
    assert "moneyline" in by_market
    assert "total" in by_market, "fresh total line must surface"
    assert "spread" in by_market, "fresh spread (run-line) must surface"

    # The snapshot's moneyline row WINS -- not overridden by the store's odds 9.9.
    ml_home = next(r for r in by_market["moneyline"] if r["side"] == "home")
    assert ml_home["best_book"] == "espn:DK"
    assert ml_home["best_odds"] == 2.10
    assert ml_home["model_prob"] == 0.52  # model priced ML

    # Total / spread carry the captured line + book; model did NOT price them.
    total_over = next(r for r in by_market["total"] if r["side"] == "over")
    assert total_over["line"] == 216.5
    assert total_over["best_book"] == "Pinnacle"
    assert total_over["model_prob"] is None, "must NOT fabricate a total model prob"
    assert total_over["market_prob"] is not None

    spread_home = next(r for r in by_market["spread"] if r["side"] == "home")
    assert spread_home["line"] == -5.5
    assert spread_home["model_prob"] is None


def test_no_history_is_moneyline_only(store_dir, monkeypatch):
    monkeypatch.setattr(edge_mod, "_fresh_line_quotes", lambda gid: {})
    view = build_edge_view(_SPORT, store_out_dir=store_dir)
    comp = view["games"][0]["comparison"]
    markets = {r["market_type"] for r in comp}
    assert markets == {"moneyline"}, "no fabrication when no fresh line history"


def test_no_money_keys(store_dir, monkeypatch):
    monkeypatch.setattr(edge_mod, "_fresh_line_quotes",
                        lambda gid: _fresh_quotes())
    _no_money(build_edge_view(_SPORT, store_out_dir=store_dir))
