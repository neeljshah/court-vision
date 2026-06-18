"""Per-file tests for the MLB player-name resolver (false-negative biased).

Run (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_player_resolver_mlb.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.player_resolver_mlb import build_name_index, resolve_player


def _canned_df() -> pd.DataFrame:
    # Mirrors the real gamelog schema (one row per player-game; many repeats).
    rows = [
        # Unambiguous, accented surname.
        {"player_id": "666969", "player": "Adolis García", "team": "PHI"},
        {"player_id": "666969", "player": "Adolis García", "team": "PHI"},
        # Suffix case: roster carries the Jr.; scrape may or may not.
        {"player_id": "682928", "player": "Bobby Witt Jr.", "team": "KC"},
        {"player_id": "682928", "player": "Bobby Witt Jr.", "team": "KC"},
        # Ambiguous "Luis Garcia": two distinct players, one Jr. one not.
        {"player_id": "671277", "player": "Luis García Jr.", "team": "WSH"},
        {"player_id": "472610", "player": "Luis García", "team": "NYM"},
        # Same surname+initial as above-but for team disambiguation we want a
        # clean pair: two "J Jones" on different teams.
        {"player_id": "111111", "player": "Jacob Jones", "team": "TB"},
        {"player_id": "222222", "player": "Jared Jones", "team": "PIT"},
        # A lone clean player for an exact happy path.
        {"player_id": "333333", "player": "Taylor Walls", "team": "TB"},
    ]
    return pd.DataFrame(rows)


def test_exact_match():
    df = _canned_df()
    r = resolve_player(df, "Taylor Walls")
    assert r["status"] == "ok"
    assert r["player_id"] == "333333"
    assert r["matched_name"] == "Taylor Walls"


def test_exact_match_accents_dropped():
    df = _canned_df()
    # Scrape without the accent still resolves the accented roster entry.
    r = resolve_player(df, "Adolis Garcia")
    assert r["status"] == "ok"
    assert r["player_id"] == "666969"


def test_suffix_jr_match():
    df = _canned_df()
    # Roster has "Bobby Witt Jr."; scrape omits the suffix -> still resolves.
    r = resolve_player(df, "Bobby Witt")
    assert r["status"] == "ok"
    assert r["player_id"] == "682928"
    assert r["reason"] == "exact_deaccented"
    # And the reverse: scrape WITH the suffix also resolves.
    r2 = resolve_player(df, "Bobby Witt Jr.")
    assert r2["status"] == "ok"
    assert r2["player_id"] == "682928"


def test_ambiguous_lastname_unresolved():
    df = _canned_df()
    # "Luis Garcia" maps to two distinct player_ids (Jr. + non-Jr.) -> unresolved.
    r = resolve_player(df, "Luis Garcia")
    assert r["status"] == "unresolved"
    assert r["player_id"] is None
    assert "ambiguous" in r["reason"]


def test_unknown_unresolved():
    df = _canned_df()
    r = resolve_player(df, "Nonexistent Player")
    assert r["status"] == "unresolved"
    assert r["player_id"] is None


def test_team_disambiguation():
    df = _canned_df()
    # Two "J Jones" overall -> ambiguous without a team.
    r_amb = resolve_player(df, "J Jones")
    assert r_amb["status"] == "unresolved"
    # With the team, the lastname+initial becomes unique.
    r_pit = resolve_player(df, "J Jones", team="PIT")
    assert r_pit["status"] == "ok"
    assert r_pit["player_id"] == "222222"
    assert r_pit["reason"] == "lastname_initial_unique_team"
    r_tb = resolve_player(df, "J Jones", team="TB")
    assert r_tb["status"] == "ok"
    assert r_tb["player_id"] == "111111"


def test_empty_and_single_token():
    df = _canned_df()
    assert resolve_player(df, "")["status"] == "unresolved"
    assert resolve_player(df, None)["status"] == "unresolved"
    # Single-token name has no surname+initial key.
    r = resolve_player(df, "Garcia")
    assert r["status"] == "unresolved"


def test_prebuilt_index_matches_inline():
    df = _canned_df()
    idx = build_name_index(df)
    a = resolve_player(df, "Taylor Walls", index=idx)
    b = resolve_player(df, "Taylor Walls")
    assert a == b


def test_never_raises_on_garbage():
    # Bad df shape must degrade, not raise.
    bad = pd.DataFrame({"foo": [1, 2]})
    r = resolve_player(bad, "Anyone")
    assert r["status"] == "unresolved"
