"""Per-file tests for prop_settler_soccer (keyless ESPN post-match prop resolver).

  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/bestbets/test_prop_settler_soccer.py -q
"""
from __future__ import annotations

from scripts.platformkit.bestbets import prop_settler_soccer as S


def _scoreboard(state="post"):
    return {"events": [{
        "id": "900001",
        "competitions": [{
            "status": {"type": {"state": state}},
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "Brazil"}},
                {"homeAway": "away", "team": {"displayName": "Scotland"}},
            ],
        }],
    }]}


_SUMMARY = {
    "rosters": [
        {"roster": [
            {"starter": True, "athlete": {"displayName": "Vinicius Junior"}},
            {"starter": True, "athlete": {"displayName": "Raphinha"}},
            {"subbedIn": True, "athlete": {"displayName": "Endrick"}},
        ]},
        {"roster": [{"starter": True, "athlete": {"displayName": "Angus Gunn"}}]},
    ],
    "keyEvents": [
        {"type": {"text": "Goal"}, "scoringPlay": True,
         "participants": [{"athlete": {"displayName": "Vinicius Junior"}},
                          {"athlete": {"displayName": "Raphinha"}}]},
        {"type": {"text": "Penalty - Scored"}, "scoringPlay": True,
         "participants": [{"athlete": {"displayName": "Vinicius Junior"}}]},
        {"type": {"text": "Yellow Card"}, "scoringPlay": False,
         "participants": [{"athlete": {"displayName": "Raphinha"}}]},
    ],
    "leaders": [
        {"leaders": [
            {"name": "totalShots", "leaders": [
                {"athlete": {"displayName": "Vinicius Junior"}, "value": 5}]},
            {"name": "saves", "leaders": [
                {"athlete": {"displayName": "Angus Gunn"}, "value": 3}]},
        ]},
    ],
}


def _http(state="post"):
    def _get(url):
        if "/scoreboard" in url:
            return _scoreboard(state)
        if "/summary?event=" in url:
            return _SUMMARY
        return {}
    return _get


def _row(player, stat):
    return {"sport": "soccer_intl", "matchup": "Brazil vs Scotland",
            "game_date": "2026-06-22", "prop_player": player, "prop_stat": stat}


# --- event-derivable families (full coverage) -----------------------------------
def test_goals_from_key_events():
    assert S.soccer_realized_stat(_row("Vinicius Junior", "Goals"), http_get=_http()) == 2.0


def test_goal_plus_assist_composite():
    assert S.soccer_realized_stat(_row("Raphinha", "Goal+Assist"), http_get=_http()) == 1.0


def test_cards_from_key_events():
    assert S.soccer_realized_stat(_row("Raphinha", "Cards"), http_get=_http()) == 1.0


def test_rostered_non_scorer_is_zero_not_pending():
    # Endrick came on, no goal event -> a genuine 0 (settleable), never None.
    assert S.soccer_realized_stat(_row("Endrick", "Goals"), http_get=_http()) == 0.0


# --- leader-only families (shots / saves) ---------------------------------------
def test_shots_resolves_for_the_match_leader():
    assert S.soccer_realized_stat(_row("Vinicius Junior", "Shots"), http_get=_http()) == 5.0


def test_shots_pending_for_a_non_leader():
    # Endrick is not the shot leader -> unresolvable keyless -> None (pending, never a fab 0).
    assert S.soccer_realized_stat(_row("Endrick", "Shots"), http_get=_http()) is None


def test_saves_resolves_for_the_keeper_leader():
    assert S.soccer_realized_stat(_row("Angus Gunn", "Saves"), http_get=_http()) == 3.0


# --- honest boundaries ----------------------------------------------------------
def test_shots_on_target_is_never_resolvable_keyless():
    assert S.soccer_realized_stat(_row("Vinicius Junior", "Shots On Target"),
                                  http_get=_http()) is None


def test_match_not_final_stays_pending():
    assert S.soccer_realized_stat(_row("Vinicius Junior", "Goals"),
                                  http_get=_http(state="in")) is None


def test_dispatch_through_prop_settler():
    # the settler's default resolver must route soccer_intl to this module.
    from scripts.platformkit.bestbets.prop_settler import _default_realized_fn
    import scripts.platformkit.bestbets.prop_settler_soccer as mod
    orig = mod._http_get_json
    mod._http_get_json = _http()  # patch the module default the dispatch will use
    try:
        val = _default_realized_fn(_row("Vinicius Junior", "Goals"))
    finally:
        mod._http_get_json = orig
    assert val == 2.0
