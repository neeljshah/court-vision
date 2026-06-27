"""Offline test for predict_service.produce -- the NBA envelope producer.

Runs with PURE FAKE feeds (no network, no corpus): a fake odds aggregate, a fake
schedule, and a fake build_result. Asserts the envelope validates against the
frozen contract, the pregame numbers are VERBATIM from the (faked) build_result,
leak_guard.in_sample is False, edges are probability/EV (no $ field), and the
snapshot round-trips through store.save / read_latest.

Per-file run only:
    python -m pytest tests/predict_service/test_produce.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from predict_service import produce, store
from predict_service.contracts import EdgeRow, SnapshotEnvelope

# The fake NBA game tips at 2026-06-18T23:30Z; pin *now* to ~1h after tip so the
# stale-drop keeps it as a live slate regardless of the real wall clock (these
# tests assert the OK/markets/edges shape, not stale-drop timing).
_NBA_NOW = datetime(2026, 6, 19, 0, 30, 0, tzinfo=timezone.utc)

# --- fake feeds ----------------------------------------------------------- #
_HOME_PROB = 0.6123
_AWAY_PROB = 0.3877  # devigged/model away derived from the fake build_result


def _fake_odds(sport: str) -> Dict[str, Any]:
    """Aggregate-shaped payload: one NBA game, two books, decimal moneyline."""
    return {
        "sport": sport, "status": "ok", "as_of": "2026-06-18T18:00:00+00:00",
        "sources": {"fakebook": "ok"},
        "events": [{
            "event_id": "G1", "sport": sport,
            "home": "Boston Celtics", "away": "Los Angeles Lakers",
            "commence_time": "2026-06-18T23:30:00Z",
            "prices": {
                "bookA": {"home": 1.62, "away": 2.45, "draw": None},
                "bookB": {"home": 1.59, "away": 2.55, "draw": None},
            },
            "source": "fake", "as_of": "2026-06-18T18:00:00+00:00",
        }],
    }


def _fake_schedule(sport: str) -> List[Dict[str, Any]]:
    return produce.games_from_odds(_fake_odds(sport))


def _fake_predict(sport: str, home: str, away: str) -> Dict[str, Any]:
    """build_result-shaped: only the pregame block the producer reads is needed."""
    return {
        "sport": sport, "home": home, "away": away, "edge_claimed": False,
        "pregame": {
            "p_home_win": _HOME_PROB, "p_away_win": _AWAY_PROB,
            "total_mean": 224.5, "margin_home": 3.1,
            "honest_note": "calibration only; no $ edge",
        },
    }


def _build() -> SnapshotEnvelope:
    return produce.produce_sport(
        "nba", schedule_feed=_fake_schedule, odds_feed=_fake_odds,
        predict_fn=_fake_predict, now=_NBA_NOW)


# --- tests ---------------------------------------------------------------- #
def test_envelope_validates_and_is_ok():
    env = _build()
    assert env.status == "ok"
    assert env.sport == "nba"
    assert env.schema_version  # stamped
    assert len(env.predictions) == 1
    # round-trips through the frozen contract unchanged
    assert SnapshotEnvelope.from_dict(env.to_dict()).to_dict() == env.to_dict()


def test_pregame_numbers_are_verbatim():
    env = _build()
    rec = env.predictions[0]
    # VERBATIM from the faked build_result -- no transform drifted them.
    assert rec.pregame_probs["home_ml"] == _HOME_PROB
    assert rec.pregame_probs["away_ml"] == _AWAY_PROB
    assert rec.home == "Boston Celtics"
    assert rec.away == "Los Angeles Lakers"
    assert rec.tipoff == "2026-06-18T23:30:00Z"


def test_leak_guard_in_sample_false():
    env = _build()
    for rec in env.predictions:
        assert rec.leak_guard == {"in_sample": False}


def test_markets_and_edges_present_and_honest():
    env = _build()
    assert env.markets, "expected moneyline market rows from the fake books"
    # markets carry decimal odds + a devigged fair prob, flagged proxy-close
    for m in env.markets:
        assert m.market_type == "moneyline"
        assert m.odds and m.odds > 1.0
        assert m.clv_is_proxy is True
        assert m.is_close is False
    assert env.edges, "expected at least one model-vs-market edge"
    for e in env.edges:
        assert isinstance(e, EdgeRow)
        d = e.to_dict()
        # HONESTY: no dollar / roi / profit field anywhere on an edge.
        for banned in ("$edge", "dollar", "roi", "profit", "stake"):
            assert banned not in d
        assert "ev" in d and "model_prob" in d and "market_prob" in d
    # the home edge uses the verbatim model prob
    home_edge = [e for e in env.edges if e.side == "home"]
    assert home_edge and home_edge[0].model_prob == _HOME_PROB


def test_store_round_trip(tmp_path):
    env = _build()
    store.save(env, out_dir=str(tmp_path))
    loaded = store.read_latest("nba", out_dir=str(tmp_path))
    assert loaded.status == "ok"
    assert loaded.to_dict() == env.to_dict()
    hist = store.read_history("nba", out_dir=str(tmp_path))
    assert len(hist) == 1
    assert hist[0].to_dict() == env.to_dict()


def test_produce_once_persists(tmp_path):
    # produce_sport(now=...) + store.save mirrors produce_once but pins the clock so
    # the fixed-date fake tipoff is not aged out by the real wall clock.
    env = _build()
    path = store.save(env, out_dir=str(tmp_path))
    assert str(path).endswith("latest.json")
    loaded = store.read_latest("nba", out_dir=str(tmp_path))
    assert loaded.status == "ok"
    assert len(loaded.predictions) == 1


def test_no_games_degrades_to_unavailable():
    env = produce.produce_sport(
        "nba", schedule_feed=lambda s: [], odds_feed=lambda s: {"events": []},
        predict_fn=_fake_predict)
    assert env.status == "unavailable"
    assert env.predictions == []


# --- game_state derivation + stale-drop interplay (REGRESSION fix) --------- #
from datetime import datetime, timedelta, timezone  # noqa: E402

from predict_service.contracts import (  # noqa: E402
    GAME_STATE_LIVE,
    GAME_STATE_POST,
)


def _mlb_odds(tipoff_iso: str) -> Dict[str, Any]:
    """An MLB-shaped aggregate payload (no live/state field, like the real one)."""
    return {
        "sport": "mlb", "status": "ok", "as_of": "2026-06-21T02:00:00+00:00",
        "sources": {"fakebook": "ok"},
        "events": [{
            "event_id": "MLB1", "sport": "mlb",
            "home": "New York Yankees", "away": "Boston Red Sox",
            "commence_time": tipoff_iso,
            "prices": {"bookA": {"home": 1.62, "away": 2.45, "draw": None}},
            "source": "fake", "as_of": "2026-06-21T02:00:00+00:00",
        }],
    }


def _build_mlb(tipoff_iso: str) -> SnapshotEnvelope:
    odds = lambda s: _mlb_odds(tipoff_iso)  # noqa: E731
    return produce.produce_sport(
        "mlb", schedule_feed=lambda s: produce.games_from_odds(_mlb_odds(tipoff_iso)),
        odds_feed=odds, predict_fn=_fake_predict)


def test_started_live_mlb_game_keeps_prior():
    """A started MLB game whose tipoff is ~3h ago (a long live game, no live-feed
    signal) is derived 'live', NOT purged -- so its leak-free pregame prior survives
    in latest.json for the in-game pregame_carry reprice. This is the regression."""
    now = datetime.now(timezone.utc)
    tipoff = (now - timedelta(hours=3)).isoformat()
    env = _build_mlb(tipoff)
    assert env.status == "ok"
    assert len(env.predictions) == 1
    rec = env.predictions[0]
    assert rec.game_state == GAME_STATE_LIVE          # started but still live
    # The pregame prior the in-game carry reads is present and unchanged.
    assert rec.pregame_probs["home_ml"] == _HOME_PROB


def test_finished_mlb_game_still_purged():
    """A finished MLB game (tipoff well beyond any real game's duration, no live
    signal) is derived 'post' and purged -- the finished-as-prediction fix holds."""
    now = datetime.now(timezone.utc)
    tipoff = (now - timedelta(hours=8)).isoformat()
    env = _build_mlb(tipoff)
    # The only game on the slate aged out -> honest unavailable, no stale card.
    assert env.status == "unavailable"
    assert env.predictions == []


def test_derive_game_state_live_window():
    """Unit: the tipoff-only derivation keeps a just-started game 'live' across the
    whole real-game window and only flips to 'post' beyond the generous threshold."""
    now = datetime.now(timezone.utc)
    just_started = (now - timedelta(minutes=20)).isoformat()
    long_but_live = (now - timedelta(hours=3)).isoformat()
    clearly_over = (now - timedelta(hours=8)).isoformat()
    assert produce._derive_game_state(just_started) == GAME_STATE_LIVE
    assert produce._derive_game_state(long_but_live) == GAME_STATE_LIVE
    assert produce._derive_game_state(clearly_over) == GAME_STATE_POST
