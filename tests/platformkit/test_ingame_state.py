"""Per-file tests for the in-game STATE spine (Milestone-6).

Covers, with a CANNED ESPN scoreboard payload (NO network, NO corpus):
  * NBA parse -> correct GameState (period / clock_sec / scores / status);
  * StateBus publish/latest round-trip + unknown game -> None;
  * ingest_router: nba routes to the NBA parser; an unknown sport -> [] / None;
  * HONESTY: a malformed/absent game -> None (never fabricated);
  * FRESHNESS: fraction_elapsed() rises Q1 -> Q4 (the validated in-game lever).

Run (per-file ONLY -- full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest tests/platformkit/test_ingame_state.py -q
"""
from __future__ import annotations

from domains.basketball_nba import live_state_nba as lsn
from scripts.platformkit.ingame import ingest_router as router
from scripts.platformkit.ingame.state_bus import (
    GameState, StateBus, latest, publish,
)


# --------------------------------------------------------------------------- payload
def _event(eid, home_abbr, home_name, home_score, away_abbr, away_name, away_score,
           state, detail, clock, period):
    return {"id": eid, "competitions": [{"competitors": [
        {"homeAway": "home", "score": home_score,
         "team": {"abbreviation": home_abbr, "displayName": home_name}},
        {"homeAway": "away", "score": away_score,
         "team": {"abbreviation": away_abbr, "displayName": away_name}}]}],
        "status": {"displayClock": clock, "period": period,
                   "type": {"state": state, "shortDetail": detail}}}


# LAL leading BOS 58-55, Q3, 5:00 remaining (LIVE); plus a FINAL and a PRE game.
_NBA_PAYLOAD = {"events": [
    _event("401766001", "LAL", "Los Angeles Lakers", "58",
           "BOS", "Boston Celtics", "55", "in", "Q3 5:00", "5:00", 3),
    _event("401766002", "GS", "Golden State Warriors", "120",
           "DEN", "Denver Nuggets", "110", "post", "Final", "0:00", 4),
    _event("401766003", "MIA", "Miami Heat", "0",
           "NYK", "New York Knicks", "0", "pre", "8:00 PM ET", None, None),
]}


# --------------------------------------------------------------------------- parse
def test_nba_parse_live_gamestate():
    states = lsn.parse_scoreboard(_NBA_PAYLOAD)
    assert len(states) == 3
    live = states[0]
    assert live.sport == "nba"
    assert live.game_id == "401766001"
    assert live.status == "live"
    assert live.period == 3
    # 5:00 remaining in the quarter -> 300 seconds.
    assert live.clock_sec == 300.0
    assert live.home_score == 58 and live.away_score == 55
    # ESPN scoreboard has no possession -> honest None, not fabricated.
    assert live.possession is None
    assert live.extras["home_team"] == "Los Angeles Lakers"
    assert live.extras["away_abbr"] == "BOS"


def test_status_mapping_pre_live_final():
    states = {gs.game_id: gs for gs in lsn.parse_scoreboard(_NBA_PAYLOAD)}
    assert states["401766001"].status == "live"
    assert states["401766002"].status == "final"
    assert states["401766003"].status == "pre"


def test_freshness_fraction_rises_q1_to_q4():
    # The only validated in-game lever: fraction_elapsed must rise as the game
    # progresses (variance must shrink downstream). Q3 5:00 left -> 31/48 min.
    live = lsn.parse_scoreboard(_NBA_PAYLOAD)[0]
    frac_q3 = live.fraction_elapsed()
    assert frac_q3 is not None
    # elapsed = 2*12 + (12-5) = 31 min; 31/48 ~ 0.6458.
    assert abs(frac_q3 - (31.0 / 48.0)) < 1e-6

    q1 = GameState(sport="nba", game_id="x", period=1, clock_sec=600.0,
                   status="live",
                   extras={"elapsed_min": 2.0, "period_len_sec": 720.0})
    q4 = GameState(sport="nba", game_id="x", period=4, clock_sec=60.0,
                   status="live",
                   extras={"elapsed_min": 47.0, "period_len_sec": 720.0})
    assert q1.fraction_elapsed() < frac_q3 < q4.fraction_elapsed()
    # A final game is fully elapsed.
    final = GameState(sport="nba", game_id="x", status="final")
    assert final.fraction_elapsed() == 1.0


# --------------------------------------------------------------------------- honesty
def test_malformed_event_returns_none_not_fabricated():
    # No competitors -> unparseable -> None, never an invented game.
    bad = {"id": "z", "competitions": [{"competitors": []}],
           "status": {"type": {"state": "in"}}}
    assert lsn.state_from_event(bad) is None
    # And it is simply dropped from the slate (not faked).
    payload = {"events": [bad]}
    assert lsn.parse_scoreboard(payload) == []


def test_state_for_absent_game_is_none():
    assert lsn.state_for_game(_NBA_PAYLOAD, "does-not-exist") is None
    got = lsn.state_for_game(_NBA_PAYLOAD, "401766001")
    assert got is not None and got.home_score == 58


def test_empty_or_garbage_payload_is_empty():
    assert lsn.parse_scoreboard(None) == []
    assert lsn.parse_scoreboard({}) == []
    assert lsn.parse_scoreboard({"events": "nope"}) == []


# --------------------------------------------------------------------------- bus
def test_bus_publish_latest_roundtrip():
    bus = StateBus()
    gs = lsn.parse_scoreboard(_NBA_PAYLOAD)[0]
    assert bus.publish(gs) is True
    back = bus.latest("401766001", sport="nba")
    assert back is gs
    # Unknown game / wrong sport -> None (never fabricated).
    assert bus.latest("nope", sport="nba") is None
    assert bus.latest("401766001", sport="mlb") is None


def test_bus_publish_none_is_ignored_and_pure():
    bus = StateBus()
    assert bus.publish(None) is False
    assert bus.publish("not a state") is False  # type: ignore[arg-type]
    assert bus.all_live() == {}


def test_bus_all_live_filters_to_live_only():
    bus = StateBus()
    for gs in lsn.parse_scoreboard(_NBA_PAYLOAD):
        bus.publish(gs)
    live = bus.all_live()
    assert list(live) == ["nba:401766001"]


def test_module_level_default_bus_roundtrip():
    gs = GameState(sport="nba", game_id="default-bus-test", status="live",
                   home_score=10, away_score=8)
    assert publish(gs) is True
    assert latest("default-bus-test", sport="nba") is gs


# --------------------------------------------------------------------------- router
def test_router_nba_routes_to_parser_and_publishes():
    bus = StateBus()
    states = router.ingest("nba", _NBA_PAYLOAD, bus=bus)
    assert len(states) == 3
    assert all(isinstance(s, GameState) for s in states)
    # Published onto the supplied bus.
    assert bus.latest("401766001", sport="nba").home_score == 58


def test_router_accepts_alias_sport_id():
    states = router.parse("basketball_nba", _NBA_PAYLOAD)
    assert len(states) == 3 and states[0].sport == "nba"


def test_router_unknown_sport_returns_empty_and_none_parser():
    assert router.get_parser("cricket") is None
    assert router.parse("cricket", _NBA_PAYLOAD) == []
    assert router.ingest("cricket", _NBA_PAYLOAD, bus=StateBus()) == []


def test_router_parse_error_is_guarded():
    # A payload that makes the parser explode internally must degrade to [].
    class _Boom(dict):
        def get(self, *a, **k):  # noqa: ANN002
            raise RuntimeError("boom")

    assert router.parse("nba", _Boom()) == []


def test_router_supported_sports_lists_nba():
    assert "nba" in router.supported_sports()
