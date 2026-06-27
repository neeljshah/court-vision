"""Per-file test: frontend.edge_api -- deep lines-vs-predictions comparison.

Stubs a canonical store envelope on disk (via store_out_dir), then asserts:
  * build_edge_view returns the full top-level shape (sport/generated_at/count/
    games/honest_note/edge_claimed=false) with every game carrying model probs,
    every market quote (per book), and a per-(market_type, side) comparison;
  * the comparison computes edge = model_prob - market_prob correctly, picks the
    BEST devigged book as market_prob/best_book, and carries the snapshot's tier;
  * build_game_edge returns the single-game object and unavailable handling works;
  * cache_key tracks the envelope generated_at;
  * NO dollar / $edge / roi / pnl key appears ANYWHERE in the output.

Run: python -m pytest tests/frontend/test_edge_api.py -q
"""
from __future__ import annotations

from typing import Any

import pytest

from predict_service.contracts import (EdgeRow, MarketRow, PredictionRecord,
                                       SnapshotEnvelope)
from predict_service import store
import frontend.edge_api as edge_mod
from frontend.edge_api import build_edge_view, build_game_edge, cache_key

_SPORT = "nba"
_GID = "0042500401"
_GEN_AT = "2026-06-18T22:01:00+00:00"
_FORBIDDEN = ("$", "dollar", "roi", "pnl", "profit", "stake", "bankroll")


def _envelope() -> SnapshotEnvelope:
    # Realistic monotone fixture: higher odds <-> lower devigged_prob (standard
    # market relationship).  DK posts the longer odds (2.10 -> fair ~0.460) which
    # is the BEST price for the bettor; FD posts shorter odds (1.90 -> fair ~0.513).
    # The correct _best_quote picks DK (min fair / longest price).  The old
    # max(fair) code would pick FD (0.513 > 0.460) -- the worst price -- so this
    # fixture NOW distinguishes correct from inverted logic.
    m_dk = MarketRow(sport=_SPORT, game_id=_GID, market_type="moneyline",
                     side="home", line=None, odds=2.10, book="espn:DK",
                     devigged_prob=0.460, captured_at="2026-06-18T22:00:00+00:00",
                     is_close=False, clv_is_proxy=True)
    m_fd = MarketRow(sport=_SPORT, game_id=_GID, market_type="moneyline",
                     side="home", line=None, odds=1.90, book="espn:FD",
                     devigged_prob=0.513, captured_at="2026-06-18T21:55:00+00:00",
                     is_close=False, clv_is_proxy=True)
    record = PredictionRecord(
        sport=_SPORT, game_id=_GID, home="Boston Celtics", away="New York Knicks",
        tipoff="2026-06-18T23:30:00+00:00",
        pregame_probs={"home_ml": 0.52, "away_ml": 0.48},
        markets=[m_dk, m_fd], leak_guard={"in_sample": False},
        produced_at="2026-06-18T21:00:00+00:00")
    # EdgeRow reflects the correct best book (DK, market_prob 0.460, ev = 0.52*2.10-1).
    edge = EdgeRow(game_id=_GID, market_type="moneyline", side="home",
                   model_prob=0.52, market_prob=0.460, ev=0.092, tier="A",
                   book="espn:DK", line=None, clv_is_proxy=True)
    return SnapshotEnvelope(sport=_SPORT, generated_at=_GEN_AT, status="ok",
                            predictions=[record], markets=[m_dk, m_fd],
                            edges=[edge])


@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    store.save(_envelope(), out_dir=tmp_path, append=False)
    # Hermetic: don't let freshness reach for real config; deterministic stub.
    monkeypatch.setattr(edge_mod, "_freshness",
                        lambda *a, **k: {"status": "fresh", "age_sec": 60.0})
    return tmp_path


def _assert_no_money(obj: Any) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            low = str(k).lower()
            for bad in _FORBIDDEN:
                assert bad not in low, "forbidden key %r in output" % k
            _assert_no_money(v)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_money(item)


def test_edge_view_full_shape(store_dir):
    view = build_edge_view(_SPORT, store_out_dir=store_dir)
    assert view["status"] == "ok"
    assert view["sport"] == _SPORT
    assert view["generated_at"] == _GEN_AT
    assert view["count"] == 1
    assert view["edge_claimed"] is False
    assert isinstance(view["honest_note"], str) and view["honest_note"]
    assert len(view["games"]) == 1

    game = view["games"][0]
    assert game["game_id"] == _GID
    assert game["home"] == "Boston Celtics"
    assert game["away"] == "New York Knicks"
    assert game["status"] == "ok"
    assert game["model"]["probs"]["home_ml"] == 0.52
    assert game["model"]["leak_guard"]["in_sample"] is False
    assert game["freshness"]["status"] == "fresh"
    assert game["as_of"]

    # Both book quotes present, verbatim.
    assert len(game["markets"]) == 2
    books = {m["book"] for m in game["markets"]}
    assert books == {"espn:DK", "espn:FD"}


def test_comparison_edge_and_best_book(store_dir):
    """Best book = LONGEST odds / LOWEST devigged fair prob (bettor-favourable price).

    DK posts odds 2.10 -> fair 0.460; FD posts odds 1.90 -> fair 0.513.
    Correct pick: DK (min fair = 0.460, longest price).
    Old max(fair) code would have picked FD (0.513) -- the SHORT price and negative EV.
    This fixture is monotone (higher odds <-> lower fair) so it CATCHES the inversion.
    """
    view = build_edge_view(_SPORT, store_out_dir=store_dir)
    comp = view["games"][0]["comparison"]
    assert len(comp) == 1
    row = comp[0]
    assert row["market_type"] == "moneyline"
    assert row["side"] == "home"
    # Best = DK: lowest fair prob (0.460) = longest odds (2.10) = best obtainable price.
    assert row["market_prob"] == 0.460
    assert row["best_book"] == "espn:DK"
    assert row["best_odds"] == 2.10
    # edge = model_prob - market_prob = 0.52 - 0.460.
    assert row["model_prob"] == 0.52
    assert abs(row["edge"] - 0.06) < 1e-9
    # ev + tier carried from the snapshot EdgeRow (A-tier, positive EV).
    assert row["ev"] == 0.092
    assert row["tier"] == "A"
    assert row["clv_is_proxy"] is True


def test_build_game_edge_and_unavailable(store_dir):
    game = build_game_edge(_SPORT, _GID, store_out_dir=store_dir)
    assert game["status"] == "ok"
    assert game["game_id"] == _GID
    assert game["generated_at"] == _GEN_AT
    assert game["edge_claimed"] is False
    assert len(game["comparison"]) == 1

    missing = build_game_edge(_SPORT, "no-such-game", store_out_dir=store_dir)
    assert missing["status"] == "unavailable"
    assert missing["game_id"] == "no-such-game"

    # An unavailable snapshot (empty store dir) -> clean sentinel, no crash.
    empty = build_edge_view(_SPORT, store_out_dir=store_dir / "empty")
    assert empty["status"] == "unavailable"
    assert empty["count"] == 0
    assert empty["games"] == []
    assert empty["edge_claimed"] is False


def test_cache_key_tracks_generated_at(store_dir):
    assert cache_key(_SPORT, store_out_dir=store_dir) == _GEN_AT
    # Missing store -> empty token (cheap miss, never raises).
    assert cache_key(_SPORT, store_out_dir=store_dir / "empty") == ""


def test_no_money_keys_anywhere(store_dir):
    _assert_no_money(build_edge_view(_SPORT, store_out_dir=store_dir))
    _assert_no_money(build_game_edge(_SPORT, _GID, store_out_dir=store_dir))
