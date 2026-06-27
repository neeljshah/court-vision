"""Per-file tests for ingame_box_soccer (keyless ESPN live realized reader).

  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/ingame/test_ingame_box_soccer.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import ingame_box_soccer as box

_SITE = box._SITE

# --- fixtures mirroring the real ESPN soccer scoreboard + summary shape ----------
_SCOREBOARD = {
    "events": [
        {  # in progress at minute 67
            "id": "900001",
            "competitions": [{
                "status": {"type": {"state": "in"}, "displayClock": "67'"},
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": "Brazil"}},
                    {"homeAway": "away", "team": {"displayName": "Scotland"}},
                ],
            }],
        },
        {  # scheduled -> must be ignored
            "id": "900002",
            "competitions": [{
                "status": {"type": {"state": "pre"}, "displayClock": "0'"},
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": "Mexico"}},
                    {"homeAway": "away", "team": {"displayName": "Czechia"}},
                ],
            }],
        },
    ]
}

_SUMMARY = {
    "rosters": [
        {"roster": [
            {"starter": True, "athlete": {"displayName": "Vinicius Junior"}},
            {"starter": True, "athlete": {"displayName": "Raphinha"}},
            {"subbedIn": True, "athlete": {"displayName": "Endrick"}},
            {"starter": False, "subbedIn": False,
             "athlete": {"displayName": "Bench Guy"}},  # never on pitch -> omitted
        ]},
        {"roster": [
            {"starter": True, "athlete": {"displayName": "Andy Robertson"}},
        ]},
    ],
    "keyEvents": [
        {"type": {"text": "Goal"}, "scoringPlay": True,
         "participants": [{"athlete": {"displayName": "Vinicius Junior"}},
                          {"athlete": {"displayName": "Raphinha"}}]},  # goal + assist
        {"type": {"text": "Penalty - Scored"}, "scoringPlay": True,
         "participants": [{"athlete": {"displayName": "Vinicius Junior"}}]},  # 2nd goal, no assist
        {"type": {"text": "Own Goal"}, "scoringPlay": True,
         "participants": [{"athlete": {"displayName": "Andy Robertson"}}]},  # excluded
        {"type": {"text": "Yellow Card"}, "scoringPlay": False,
         "participants": [{"athlete": {"displayName": "Andy Robertson"}}]},
    ],
}


def _fake_http(scoreboard=_SCOREBOARD, summary=_SUMMARY):
    def _get(url):
        if url.endswith("/scoreboard"):
            return scoreboard
        if "/summary?event=" in url:
            return summary
        return {}
    return _get


# --- live_games -----------------------------------------------------------------
def test_live_games_keeps_only_in_progress_and_computes_frac():
    games = box.live_games("soccer_intl", http_get=_fake_http())
    assert len(games) == 1
    g = games[0]
    assert g["game_pk"] == "900001"
    assert g["home"] == "Brazil" and g["away"] == "Scotland"
    assert abs(g["frac_elapsed"] - 67.0 / 90.0) < 1e-6


def test_live_games_empty_on_no_board():
    assert box.live_games("soccer_intl", http_get=lambda u: {}) == []


# --- boxscore_stat_map ----------------------------------------------------------
def test_boxscore_tally_goals_assists_cards_and_own_goal_excluded():
    sm = box.boxscore_stat_map("900001", http_get=_fake_http(), sport="soccer_intl")
    from scripts.platformkit.bestbets.prop_settler_mlb import _norm
    vini = sm[_norm("Vinicius Junior")]
    assert vini["Goals"] == 2.0 and vini["Assists"] == 0.0
    assert sm[_norm("Raphinha")]["Assists"] == 1.0
    robbo = sm[_norm("Andy Robertson")]
    assert robbo["Goals"] == 0.0          # own goal does NOT credit the player
    assert robbo["Cards"] == 1.0
    # a player on the pitch with no event is honestly 0 (seeded), not absent
    assert box.realized_for("Goals", sm, "Endrick") == 0.0
    # a bench player who never entered is omitted -> unknown (None), never a fake 0
    assert box.realized_for("Goals", sm, "Bench Guy") is None


# --- realized_for / is_known_stat ----------------------------------------------
def test_realized_for_goal_plus_assist_composite():
    sm = box.boxscore_stat_map("900001", http_get=_fake_http(), sport="soccer_intl")
    # Vini: 2 goals + 0 assists = 2 ; Raphinha: 0 goals + 1 assist = 1
    assert box.realized_for("Goal+Assist", sm, "Vinicius Junior") == 2.0
    assert box.realized_for("Goal+Assist", sm, "Raphinha") == 1.0


def test_is_known_stat_only_event_derivable():
    for s in ("Goals", "Assists", "Goal+Assist", "Cards"):
        assert box.is_known_stat(s) is True
    for s in ("Shots", "Shots On Target", "Saves", "Fouls", ""):
        assert box.is_known_stat(s) is False
    # an unreadable stat -> realized_for returns None (never a fabricated 0)
    sm = box.boxscore_stat_map("900001", http_get=_fake_http())
    assert box.realized_for("Shots On Target", sm, "Vinicius Junior") is None
