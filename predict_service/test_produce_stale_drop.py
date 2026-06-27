"""Per-file tests: producer drops finished/past games (BE-R3-2 stale-never-green).

Uses fully INJECTED feeds (schedule_feed/odds_feed/predict_fn) + an injected *now*
so there is NO corpus, NO network, NO real clock. Proves:

  * a 'post' (finished) game is NOT surfaced -- the NBA Spurs/Knicks bug,
  * a past-tipoff-beyond-grace game is dropped,
  * future/live games ARE surfaced,
  * an ALL-stale slate (a day rollover) -> status='unavailable' (honest empty,
    never stale-green, never a crash),
  * markets/edges of dropped games do not linger on the envelope.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    predict_service/test_produce_stale_drop.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from predict_service import produce
from predict_service.stale_drop import PAST_TIPOFF_GRACE_SECONDS

NOW = datetime(2026, 6, 21, 3, 0, tzinfo=timezone.utc)


def _odds_for(games):
    """Build an aggregate-shaped payload with a live.state per game (post/live/pre)."""
    events = []
    for g in games:
        events.append({
            "event_id": g["game_id"], "home": g["home"], "away": g["away"],
            "commence_time": g["tipoff"], "live": {"state": g.get("state", "pre")},
            "prices": {"moneyline": {"home": {"odds": 1.8}, "away": {"odds": 2.0}}},
        })
    return {"events": events, "as_of": NOW.isoformat()}


_PROB_SEQ = {}


def _predict_fn(_sport, home, _away):
    # Distinct per-home probs so the degeneracy guard never fires on these slates;
    # each unique home string gets its own incrementing probability.
    if home not in _PROB_SEQ:
        _PROB_SEQ[home] = 0.40 + len(_PROB_SEQ) * 0.011
    p = round(_PROB_SEQ[home], 4)
    return {"pregame": {"p_home_win": p, "p_away_win": round(1.0 - p, 4)}}


def _produce(games):
    sched = lambda _s: list(games)  # noqa: E731
    odds = lambda _s: _odds_for(games)  # noqa: E731
    return produce.produce_sport(
        "nba", schedule_feed=sched, odds_feed=odds,
        predict_fn=_predict_fn, now=NOW)


def test_post_state_game_not_surfaced():
    games = [{"game_id": "401859967", "home": "San Antonio Spurs",
              "away": "New York Knicks", "tipoff": "2026-06-14T00:30Z",
              "state": "post"}]
    env = _produce(games)
    # Whole slate is the one post game -> honest unavailable, not a stale 'ok'.
    assert env.status == "unavailable"
    assert all(p.game_id != "401859967" for p in env.predictions)


def test_future_games_surfaced():
    fut = (NOW + timedelta(hours=5)).isoformat()
    games = [
        {"game_id": "f1", "home": "Lakers", "away": "Celtics", "tipoff": fut,
         "state": "pre"},
        {"game_id": "f2", "home": "Heat", "away": "Bulls", "tipoff": fut,
         "state": "pre"},
        {"game_id": "f3", "home": "Suns", "away": "Nuggets", "tipoff": fut,
         "state": "pre"},
    ]
    env = _produce(games)
    assert env.status == "ok"
    assert {p.game_id for p in env.predictions} == {"f1", "f2", "f3"}


def test_all_stale_slate_is_unavailable_not_green():
    # A full yesterday slate (all post) on a tomorrow clock -> honest empty.
    games = [{"game_id": f"g{i}", "home": f"Home{i}", "away": f"Away{i}",
              "tipoff": "2026-06-20T20:10Z", "state": "post"} for i in range(6)]
    env = _produce(games)
    assert env.status == "unavailable"
    assert env.predictions == []
    assert env.markets == [] and env.edges == []
    # honest reason, no $ claim
    assert "no upcoming games" in env.note


def test_mixed_slate_keeps_future_drops_post():
    fut = (NOW + timedelta(hours=4)).isoformat()
    games = [
        {"game_id": "old", "home": "Spurs", "away": "Knicks",
         "tipoff": "2026-06-14T00:30Z", "state": "post"},
        {"game_id": "new1", "home": "Lakers", "away": "Heat", "tipoff": fut,
         "state": "pre"},
        {"game_id": "new2", "home": "Bulls", "away": "Suns", "tipoff": fut,
         "state": "pre"},
        {"game_id": "new3", "home": "Nuggets", "away": "Magic", "tipoff": fut,
         "state": "pre"},
    ]
    env = _produce(games)
    assert env.status == "ok"
    assert "old" not in {p.game_id for p in env.predictions}
    assert {p.game_id for p in env.predictions} == {"new1", "new2", "new3"}
    # markets + edges for the dropped game must not linger
    assert all(m.game_id != "old" for m in env.markets)
    assert all(e.game_id != "old" for e in env.edges)


def test_past_tipoff_without_post_state_dropped():
    # No 'post' live signal, but tipoff older than grace -> still dropped.
    old = (NOW - timedelta(seconds=PAST_TIPOFF_GRACE_SECONDS + 600)).isoformat()
    fut = (NOW + timedelta(hours=4)).isoformat()
    games = [
        {"game_id": "stale", "home": "AAA", "away": "BBB", "tipoff": old,
         "state": "pre"},
        {"game_id": "ok1", "home": "CCC", "away": "DDD", "tipoff": fut,
         "state": "pre"},
        {"game_id": "ok2", "home": "EEE", "away": "FFF", "tipoff": fut,
         "state": "pre"},
        {"game_id": "ok3", "home": "GGG", "away": "HHH", "tipoff": fut,
         "state": "pre"},
    ]
    env = _produce(games)
    assert "stale" not in {p.game_id for p in env.predictions}
