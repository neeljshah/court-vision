"""Per-file tests for scripts.platformkit.pm_trading.run_paper_today.

NO NETWORK: live_board / bet_board / odds index are all injected with stubs.

Run ONLY this file (the full suite freezes the box):
    python -m pytest scripts/platformkit/pm_trading/test_run_paper_today.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List

from scripts.platformkit import clv_ledger as L
from scripts.platformkit.pm_trading.run_paper_today import run_paper_cycle


# --------------------------------------------------------------------------- #
# Stubs (no network): a live feed, a bet board, and an odds index.
# --------------------------------------------------------------------------- #
def _live_one_game(sport: str) -> Dict[str, Any]:
    return {"sport": sport, "status": "ok", "games": [
        {"sport": sport, "home": "Boston Red Sox", "away": "Toronto Blue Jays",
         "state": "pre", "home_score": None, "away_score": None, "clock": None},
    ]}


def _live_no_games(sport: str) -> Dict[str, Any]:
    return {"sport": sport, "status": "unavailable", "games": [],
            "note": "feed down (degraded, not fabricated)"}


def _board_priced(sport, home, away, *, odds_lookup=None, live=None, **_):
    """Board with one PRICED moneyline (home) + one UNPRICED total row."""
    return {"sport": sport, "home": home, "away": away, "status": "ok",
            "live": None, "best_bets": [], "honest_note": "stub",
            "groups": [
                {"name": "Moneyline", "bets": [
                    {"group": "Moneyline", "selection": home, "model_prob": 0.58,
                     "line": None, "fair_odds": 1.72, "best_book": "stub_book",
                     "best_price": 1.95, "ev_pct": 13.1, "verdict": "PRICED+EV"},
                    {"group": "Moneyline", "selection": away, "model_prob": 0.42,
                     "line": None, "fair_odds": 2.38, "best_book": None,
                     "best_price": None, "ev_pct": None, "verdict": "MODEL_VIEW"},
                ]},
                {"name": "Total", "bets": [
                    {"group": "Total", "selection": "Over 8.5", "model_prob": 0.51,
                     "line": 8.5, "fair_odds": 1.96, "best_book": None,
                     "best_price": None, "ev_pct": None, "verdict": "MODEL_VIEW"},
                ]},
            ]}


def _odds_index_stub(sport: str):
    """Odds lookup returning a VIGGED two-way book (booksum > 1) for the stub game.

    1.90/1.90 implies 0.526+0.526 = 1.052 (a real ~5% hold), so the close-proxy
    devig succeeds -- exercising the proxy-target path for the grader.
    """
    def _lookup(s, home, away):
        if home == "Boston Red Sox":
            return {"stub_book": {home: 1.95, away: 1.90}}
        return None
    return _lookup, []


def _run(tmp_path, **kw):
    return run_paper_cycle(
        sports=("mlb",),
        ledger_path=tmp_path / "ledger.jsonl",
        predictions_path=tmp_path / "preds.jsonl",
        live_fetch=kw.get("live_fetch", _live_one_game),
        board_fn=kw.get("board_fn", _board_priced),
        odds_index=kw.get("odds_index", _odds_index_stub),
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_priced_pick_recorded_paper_only(tmp_path):
    out = _run(tmp_path)
    assert out["executed_any"] is False
    assert out["channel"] == "paper"
    assert out["n_recorded"] == 1            # the priced home moneyline
    assert out["n_logged"] >= 1              # the unpriced rows logged
    bet = out["bets"][0]
    assert bet["side"] == "home"
    assert bet["executed"] is False
    assert bet["channel"] == "paper"
    assert bet["would_pass_real_gate"] is True   # +EV at the book price
    assert bet["price"] == 1.95
    # the ledger row itself is unexecuted / paper
    rows = L.load_ledger(tmp_path / "ledger.jsonl")
    assert rows and all(r.get("executed") is False for r in rows)


def test_idempotent_second_run_adds_nothing(tmp_path):
    first = _run(tmp_path)
    assert first["n_recorded"] == 1
    n_pred_first = first["n_logged"]
    second = _run(tmp_path)
    assert second["n_recorded"] == 0
    assert second["n_logged"] == 0
    # the stores did not grow on the second pass
    assert len(L.load_ledger(tmp_path / "ledger.jsonl")) == 1
    preds = [l for l in (tmp_path / "preds.jsonl").read_text().splitlines() if l]
    assert len(preds) == n_pred_first


def test_unpriced_rows_logged_with_proxy_target(tmp_path):
    out = _run(tmp_path)
    preds = out["predictions"]
    assert preds, "expected unpriced model predictions to be logged"
    # the unpriced AWAY moneyline maps to a side, so it carries a close proxy
    away_ml = [p for p in preds if p["selection"] == "Toronto Blue Jays"]
    assert away_ml, "away moneyline should be logged as a model-view prediction"
    proxy = away_ml[0]["close_proxy"]
    assert proxy is not None
    assert proxy["fair_close_prob"] is not None   # devigged from the book proxy
    assert away_ml[0]["price"] is None            # NEVER a fabricated price
    assert away_ml[0]["channel"] == "paper"
    # a non-two-way row (Over 8.5) is still logged but has no side -> no proxy
    over = [p for p in preds if p["selection"] == "Over 8.5"]
    assert over and over[0]["close_proxy"] is None


def test_no_games_degrades_cleanly(tmp_path):
    out = _run(tmp_path, live_fetch=_live_no_games)
    assert out["n_recorded"] == 0
    assert out["n_logged"] == 0
    assert out["sports"]["mlb"]["status"] == "unavailable"
    assert out["sports"]["mlb"]["n_games"] == 0
    # nothing written
    assert L.load_ledger(tmp_path / "ledger.jsonl") == []


def test_negative_ev_recorded_but_flagged_not_gate_passing(tmp_path):
    """A priced but -EV pick is still recorded (permissive paper policy) yet
    tagged would_pass_real_gate=False with zero stake."""
    def _board_neg(sport, home, away, *, odds_lookup=None, live=None, **_):
        b = _board_priced(sport, home, away)
        # MILD -EV within the permissive floor: 0.51 * 1.95 - 1 = -0.0055 (> -0.02),
        # so it is recorded (paper measurement) but flagged not gate-passing.
        b["groups"][0]["bets"][0]["model_prob"] = 0.51
        return b
    out = _run(tmp_path, board_fn=_board_neg)
    assert out["n_recorded"] == 1
    bet = out["bets"][0]
    assert bet["would_pass_real_gate"] is False
    assert bet["stake"] == 0.0


def test_event_metadata_attached(tmp_path):
    """When the odds index supplies an event, its id/commence_time ride along."""
    from scripts.platformkit.odds_provider.base import OddsEvent

    def _idx(sport):
        ev = OddsEvent(event_id="evt-123", sport=sport, home="Boston Red Sox",
                       away="Toronto Blue Jays", commence_time="2026-06-17T23:00Z",
                       prices={"stub_book": {"home": 1.95, "away": 2.10}})

        def _lookup(s, home, away):
            return {"stub_book": {home: 1.95, away: 2.10}}
        return _lookup, [ev]

    out = _run(tmp_path, odds_index=_idx)
    bet = out["bets"][0]
    assert bet["event_id"] == "evt-123"
    assert bet["commence_time"] == "2026-06-17T23:00Z"
