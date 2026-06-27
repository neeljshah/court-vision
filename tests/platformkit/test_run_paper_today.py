"""Per-file test: scripts.platformkit.pm_trading.run_paper_today -- store board_fn
and policy tier stamping.

Tests that:
  1. make_store_board_fn returns a callable that uses predict_service.store when
     the envelope is available and the game matches by home/away.
  2. The default board_fn path (game_bet_board) is unchanged when the store is
     absent or has no matching game.
  3. run_paper_cycle accepts a board_fn built from make_store_board_fn and
     processes rows without crashing.
  4. _policy_tier_and_stake stamps tier + flat_unit + quarter_kelly onto placed rows.
  5. Below-floor rows (tier None) are gated out and NOT recorded.

Run: python -m pytest tests/platformkit/test_run_paper_today.py -q
"""
from __future__ import annotations

import types
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import pytest

from scripts.platformkit.pm_trading.run_paper_today import make_store_board_fn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_env(status: str = "ok", preds: list = None,
              edges: list = None) -> Any:
    ns = types.SimpleNamespace()
    ns.status = status
    ns.predictions = preds or []
    ns.edges = edges or []
    return ns


def _pred(game_id: str = "G1", home: str = "SAS", away: str = "NYK",
          pregame_probs: Dict[str, float] = None) -> Any:
    p = types.SimpleNamespace()
    p.game_id = game_id
    p.home = home
    p.away = away
    p.tipoff = "2026-06-18T22:00:00Z"
    p.pregame_probs = pregame_probs or {"home_ml": 0.58, "away_ml": 0.42}
    p.markets = []
    p.note = ""
    return p


def _edge(game_id: str = "G1", side: str = "home",
          model_prob: float = 0.58, market_prob: float = 0.52,
          ev: float = 0.05, book: str = "espn") -> Any:
    e = types.SimpleNamespace()
    e.game_id = game_id
    e.side = side
    e.model_prob = model_prob
    e.market_prob = market_prob
    e.ev = ev
    e.book = book
    e.to_dict = lambda: {"game_id": game_id, "side": side, "ev": ev}
    return e


# ---------------------------------------------------------------------------
# 1. make_store_board_fn: store present + matching game -> store used
# ---------------------------------------------------------------------------

def test_store_board_fn_uses_store_when_match():
    """make_store_board_fn returns a board using store data when home/away match."""
    import scripts.platformkit.pm_trading.run_paper_today as mod

    env = _make_env("ok", preds=[_pred("G1", "SAS", "NYK")],
                    edges=[_edge("G1", "home", 0.58, 0.52, 0.05)])
    store_stub = types.SimpleNamespace(read_latest=lambda sport: env)

    with patch.object(mod, "_ps_store", store_stub):
        fn = make_store_board_fn("nba")

    board = fn("nba", "SAS", "NYK")
    assert board["status"] == "ok"
    assert board["served_from"] == "predict_service_store"
    assert board["home"] == "SAS"
    assert board["away"] == "NYK"
    rows = board["best_bets"]
    assert len(rows) >= 1
    sides = {r["selection"] for r in rows}
    assert "home_ml" in sides or "home" in sides


# ---------------------------------------------------------------------------
# 2. make_store_board_fn: case-insensitive team matching
# ---------------------------------------------------------------------------

def test_store_board_fn_case_insensitive_match():
    """Home/away matching is case-insensitive."""
    import scripts.platformkit.pm_trading.run_paper_today as mod

    env = _make_env("ok", preds=[_pred("G1", "San Antonio Spurs", "New York Knicks")],
                    edges=[])
    store_stub = types.SimpleNamespace(read_latest=lambda sport: env)

    with patch.object(mod, "_ps_store", store_stub):
        fn = make_store_board_fn("nba")

    board = fn("nba", "san antonio spurs", "new york knicks")
    assert board["status"] == "ok"
    assert board["served_from"] == "predict_service_store"


# ---------------------------------------------------------------------------
# 3. make_store_board_fn: no match -> falls back to game_bet_board
# ---------------------------------------------------------------------------

def test_store_board_fn_falls_back_on_no_match():
    """When no game matches home/away, falls back to game_bet_board."""
    import scripts.platformkit.pm_trading.run_paper_today as mod

    env = _make_env("ok", preds=[_pred("G1", "SAS", "NYK")], edges=[])
    store_stub = types.SimpleNamespace(read_latest=lambda sport: env)

    fallback_result = {"status": "ok", "home": "BOS", "away": "MIA",
                       "best_bets": [], "groups": [], "served_from": "fallback"}
    fallback_fn = MagicMock(return_value=fallback_result)

    with patch.object(mod, "_ps_store", store_stub):
        with patch.object(mod, "game_bet_board", fallback_fn):
            fn = make_store_board_fn("nba")
            board = fn("nba", "BOS", "MIA")

    fallback_fn.assert_called_once()
    assert board["served_from"] == "fallback"


# ---------------------------------------------------------------------------
# 4. make_store_board_fn: store absent (_ps_store=None) -> falls back
# ---------------------------------------------------------------------------

def test_store_board_fn_store_absent_falls_back():
    """When _ps_store is None, make_store_board_fn wraps game_bet_board unchanged."""
    import scripts.platformkit.pm_trading.run_paper_today as mod

    fallback_result = {"status": "ok", "best_bets": [], "groups": [],
                       "served_from": "live"}
    fallback_fn = MagicMock(return_value=fallback_result)

    with patch.object(mod, "_ps_store", None):
        with patch.object(mod, "game_bet_board", fallback_fn):
            fn = make_store_board_fn("nba")
            board = fn("nba", "SAS", "NYK", odds_lookup=None, live=None)

    fallback_fn.assert_called_once_with("nba", "SAS", "NYK",
                                        odds_lookup=None, live=None)
    assert board["served_from"] == "live"


# ---------------------------------------------------------------------------
# 5. make_store_board_fn: unavailable envelope -> falls back
# ---------------------------------------------------------------------------

def test_store_board_fn_unavailable_envelope_falls_back():
    """store returns unavailable status -> fn falls back to game_bet_board."""
    import scripts.platformkit.pm_trading.run_paper_today as mod

    env = _make_env("unavailable", preds=[])
    store_stub = types.SimpleNamespace(read_latest=lambda sport: env)
    fallback_result = {"status": "ok", "best_bets": [], "groups": [],
                       "served_from": "live"}
    fallback_fn = MagicMock(return_value=fallback_result)

    with patch.object(mod, "_ps_store", store_stub):
        with patch.object(mod, "game_bet_board", fallback_fn):
            fn = make_store_board_fn("nba")
            board = fn("nba", "SAS", "NYK")

    fallback_fn.assert_called_once()
    assert board["served_from"] == "live"


# ---------------------------------------------------------------------------
# 6. run_paper_cycle: board_fn from store works end-to-end (no crash)
# ---------------------------------------------------------------------------

def test_run_paper_cycle_with_store_board_fn(tmp_path):
    """run_paper_cycle accepts a store-backed board_fn and completes without error."""
    from scripts.platformkit.pm_trading.run_paper_today import run_paper_cycle
    import scripts.platformkit.pm_trading.run_paper_today as mod

    env = _make_env("ok", preds=[_pred("G1", "SAS", "NYK")],
                    edges=[_edge("G1", "home", 0.58, 0.52, 0.05)])
    store_stub = types.SimpleNamespace(read_latest=lambda sport: env)

    # live_fetch returns one game for nba
    def _live(sport):
        return {"status": "ok", "games": [
            {"home": "SAS", "away": "NYK", "status": "scheduled"}]}

    # Build the board_fn from the store
    with patch.object(mod, "_ps_store", store_stub):
        board_fn = make_store_board_fn("nba")

    ledger_path = tmp_path / "ledger.jsonl"
    preds_path = tmp_path / "preds.jsonl"

    # Stub odds_index to return empty lookup + events
    def _noop_odds(sport):
        return (lambda *a, **k: None), []

    out = run_paper_cycle(
        sports=["nba"],
        ledger_path=ledger_path,
        predictions_path=preds_path,
        live_fetch=_live,
        board_fn=board_fn,
        odds_index=_noop_odds,
    )
    assert "sports" in out
    assert "nba" in out["sports"]
    # Must not have executed real money
    assert out["executed_any"] is False
    assert out["channel"] == "paper"


# ---------------------------------------------------------------------------
# 7. _policy_tier_and_stake: above-floor ev -> tier + units stamped
# ---------------------------------------------------------------------------

def test_policy_tier_and_stake_above_floor():
    """_policy_tier_and_stake returns a tier and flat_unit=1.0 for an above-floor EV."""
    from scripts.platformkit.pm_trading.run_paper_today import _policy_tier_and_stake
    # EV_FLOOR_C = 0.02; EV_FLOOR_A = 0.08 -> ev=0.10 should be tier A
    tier_label, flat_unit, quarter_kelly = _policy_tier_and_stake(
        ev=0.10, model_prob=0.58, price=1.95, market_prob=0.52)
    assert tier_label == "A", "expected tier A for ev=0.10"
    assert flat_unit == 1.0
    assert isinstance(quarter_kelly, float)


# ---------------------------------------------------------------------------
# 8. _policy_tier_and_stake: below-floor ev -> tier=None, flat_unit=0.0
# ---------------------------------------------------------------------------

def test_policy_tier_and_stake_below_floor():
    """_policy_tier_and_stake returns tier=None and zero units for below-floor EV."""
    from scripts.platformkit.pm_trading.run_paper_today import _policy_tier_and_stake
    # EV_FLOOR_C = 0.02; ev=0.01 is below floor -> None
    tier_label, flat_unit, quarter_kelly = _policy_tier_and_stake(
        ev=0.01, model_prob=0.52, price=1.90, market_prob=0.51)
    assert tier_label is None
    assert flat_unit == 0.0
    assert quarter_kelly == 0.0


# ---------------------------------------------------------------------------
# 9. run_paper_cycle: tier stamped on bet rows in output
# ---------------------------------------------------------------------------

def test_run_paper_cycle_tier_stamped_on_bets(tmp_path):
    """run_paper_cycle places bets with tier + flat_unit + quarter_kelly fields."""
    from scripts.platformkit.pm_trading.run_paper_today import run_paper_cycle
    import scripts.platformkit.pm_trading.run_paper_today as mod

    # Board with a high-EV priced row (ev > EV_FLOOR_A = 0.08)
    # model_prob=0.65, price=1.65 -> ev = 0.65*1.65-1 = 0.0725... let's use 0.70*1.60=0.12
    high_ev_row = {
        "group": "pregame", "selection": "home",
        "model_prob": 0.70, "best_price": 1.60,
        "best_book": "espn", "line": None, "fair_odds": None,
    }

    def _board_fn(sp, home, away, **kw):
        return {
            "status": "ok", "home": home, "away": away,
            "best_bets": [high_ev_row],
            "groups": [{"bets": [high_ev_row]}],
        }

    def _live(sport):
        return {"status": "ok", "games": [
            {"home": "SAS", "away": "NYK", "status": "scheduled"}]}

    def _noop_odds(sport):
        return (lambda *a, **k: None), []

    out = run_paper_cycle(
        sports=["nba"],
        ledger_path=tmp_path / "ledger.jsonl",
        predictions_path=tmp_path / "preds.jsonl",
        live_fetch=_live,
        board_fn=_board_fn,
        odds_index=_noop_odds,
    )
    bets = out.get("bets", [])
    assert out["executed_any"] is False
    # If any bet was recorded it must carry tier + flat_unit + quarter_kelly
    for b in bets:
        assert "tier" in b, "tier field missing from bet row"
        assert "flat_unit" in b, "flat_unit field missing from bet row"
        assert "quarter_kelly" in b, "quarter_kelly field missing from bet row"
        assert b["tier"] in ("A", "B", "C"), "unexpected tier value: %r" % b["tier"]
        assert b["flat_unit"] == 1.0


# ---------------------------------------------------------------------------
# 10. Below-floor rows are NOT recorded (tier gate works)
# ---------------------------------------------------------------------------

def test_run_paper_cycle_below_floor_not_recorded(tmp_path):
    """A row whose EV is below policy floors is silently skipped."""
    from scripts.platformkit.pm_trading.run_paper_today import run_paper_cycle
    import scripts.platformkit.pm_trading.run_paper_today as mod

    # EV = 0.50*1.60 - 1 = -0.20 -> deeply negative, well below EV_FLOOR_C
    low_ev_row = {
        "group": "pregame", "selection": "home",
        "model_prob": 0.50, "best_price": 1.60,
        "best_book": "espn", "line": None, "fair_odds": None,
    }

    def _board_fn(sp, home, away, **kw):
        return {
            "status": "ok", "home": home, "away": away,
            "best_bets": [low_ev_row],
            "groups": [{"bets": [low_ev_row]}],
        }

    def _live(sport):
        return {"status": "ok", "games": [
            {"home": "SAS", "away": "NYK", "status": "scheduled"}]}

    def _noop_odds(sport):
        return (lambda *a, **k: None), []

    out = run_paper_cycle(
        sports=["nba"],
        ledger_path=tmp_path / "ledger.jsonl",
        predictions_path=tmp_path / "preds.jsonl",
        live_fetch=_live,
        board_fn=_board_fn,
        odds_index=_noop_odds,
    )
    # Row is below PAPER_EV_FLOOR (-0.02) so skipped even before policy tier check
    assert out["n_recorded"] == 0
