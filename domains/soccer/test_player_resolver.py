"""Per-file tests for domains.soccer.player_resolver.

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_player_resolver.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.soccer.player_resolver import build_name_index, resolve_player


def _df():
    return pd.DataFrame([
        {"player_id": "1", "player": "Luis Diaz", "team_abbr": "COL"},
        {"player_id": "2", "player": "James Rodriguez", "team_abbr": "COL"},
        # Two same-last-name players on different teams (team disambiguates).
        {"player_id": "3", "player": "John Smith", "team_abbr": "USA"},
        {"player_id": "4", "player": "Jane Smith", "team_abbr": "ENG"},
        # Two players sharing last name + first initial on the SAME team
        # (ambiguous -> must stay unresolved).
        {"player_id": "5", "player": "Sergio Ramos", "team_abbr": "ESP"},
        {"player_id": "6", "player": "Saul Ramos", "team_abbr": "ESP"},
    ])


def test_exact_match():
    df = _df()
    r = resolve_player(df, "James Rodriguez")
    assert r["status"] == "ok"
    assert r["player_id"] == "2"
    assert r["matched_name"] == "James Rodriguez"


def test_accented_vs_unaccented_match():
    df = _df()
    # Scraped name carries diacritics; roster does not (and vice-versa works too).
    r = resolve_player(df, "Luis Diaz".replace("i", "i"))  # plain
    assert r["status"] == "ok" and r["player_id"] == "1"
    r2 = resolve_player(df, "Luis Díaz")  # accented input
    assert r2["status"] == "ok" and r2["player_id"] == "1"


def test_ambiguous_lastname_initial_unresolved():
    df = _df()
    # "S. Ramos" -> Sergio/Saul Ramos both match last+initial on ESP -> unresolved.
    r = resolve_player(df, "S Ramos", team="ESP")
    assert r["status"] == "unresolved"
    assert "ambiguous" in r["reason"]
    assert r["player_id"] is None


def test_unknown_player_unresolved():
    df = _df()
    r = resolve_player(df, "Cristiano Ronaldo")
    assert r["status"] == "unresolved"
    assert r["player_id"] is None


def test_team_disambiguates_same_lastname():
    df = _df()
    # "J. Smith" overall is ambiguous (John/Jane) but team narrows it to one.
    overall = resolve_player(df, "J Smith")
    assert overall["status"] == "unresolved"
    usa = resolve_player(df, "J Smith", team="USA")
    assert usa["status"] == "ok" and usa["player_id"] == "3"
    eng = resolve_player(df, "J Smith", team="ENG")
    assert eng["status"] == "ok" and eng["player_id"] == "4"


def test_prebuilt_index_and_no_raise():
    df = _df()
    idx = build_name_index(df)
    r = resolve_player(df, "Luis Diaz", index=idx)
    assert r["status"] == "ok"
    # Bad input must NOT raise.
    assert resolve_player(None, None)["status"] == "unresolved"
    assert resolve_player(df, "")["status"] == "unresolved"
    assert resolve_player(pd.DataFrame(), "Anyone")["status"] == "unresolved"
