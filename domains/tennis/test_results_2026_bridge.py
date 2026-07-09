"""Per-file test for domains.tennis.results_2026_bridge -- no network, no real disk paths."""
from __future__ import annotations

import pandas as pd
import pytest

from domains.tennis import results_2026_bridge as mod


@pytest.fixture
def players_df():
    return pd.DataFrame([
        {"player_id": 1, "full_name": "Novak Djokovic", "tour": "atp"},
        {"player_id": 2, "full_name": "Carlos Alcaraz", "tour": "atp"},
        {"player_id": 3, "full_name": "Iga Swiatek", "tour": "wta"},
        {"player_id": 4, "full_name": "Aryna Sabalenka", "tour": "wta"},
    ])


def test_build_sackmann_index(players_df, tmp_path):
    p = tmp_path / "players.parquet"
    players_df.to_parquet(p)
    idx = mod.build_sackmann_index(p)
    assert idx["atp"][mod.normalize_sackmann("Novak Djokovic")] == 1
    assert idx["wta"][mod.normalize_sackmann("Iga Swiatek")] == 3
    assert "atp" in idx and "wta" in idx


def test_resolve_player_id_hits_and_misses(players_df, tmp_path):
    p = tmp_path / "players.parquet"
    players_df.to_parquet(p)
    idx = mod.build_sackmann_index(p)
    assert mod._resolve_player_id("Novak Djokovic", idx["atp"]) == 1
    assert mod._resolve_player_id("Some Nobody", idx["atp"]) is None


def test_surface_from_name():
    assert mod._surface_from_name("Wimbledon") == "Grass"
    assert mod._surface_from_name("Australian Open") == "Hard"
    assert mod._surface_from_name("Roland Garros") == "Clay"
    assert mod._surface_from_name("ATP Rotterdam") == "Unknown"


def test_build_matches_2026_end_to_end(players_df, tmp_path):
    players_path = tmp_path / "players.parquet"
    players_df.to_parquet(players_path)
    espn_path = tmp_path / "espn_matches.parquet"
    espn = pd.DataFrame([
        {"comp_id": "c1", "date": "2026-01-15T10:00Z", "league": "atp",
         "tournament_id": "t1", "tournament_name": "Australian Open", "major": True,
         "season_year": 2026, "best_of": 5, "discipline": "Men's Singles",
         "round_name": "R32", "status": "STATUS_FINAL", "player_name": "Novak Djokovic",
         "winner": True, "sets_won": 3},
        {"comp_id": "c1", "date": "2026-01-15T10:00Z", "league": "atp",
         "tournament_id": "t1", "tournament_name": "Australian Open", "major": True,
         "season_year": 2026, "best_of": 5, "discipline": "Men's Singles",
         "round_name": "R32", "status": "STATUS_FINAL", "player_name": "Carlos Alcaraz",
         "winner": False, "sets_won": 1},
        # unresolved-name match -- must be dropped, never guessed
        {"comp_id": "c2", "date": "2026-01-16T10:00Z", "league": "atp",
         "tournament_id": "t1", "tournament_name": "Australian Open", "major": True,
         "season_year": 2026, "best_of": 3, "discipline": "Men's Singles",
         "round_name": "R64", "status": "STATUS_FINAL", "player_name": "Nobody Atall",
         "winner": True, "sets_won": 2},
        {"comp_id": "c2", "date": "2026-01-16T10:00Z", "league": "atp",
         "tournament_id": "t1", "tournament_name": "Australian Open", "major": True,
         "season_year": 2026, "best_of": 3, "discipline": "Men's Singles",
         "round_name": "R64", "status": "STATUS_FINAL", "player_name": "Carlos Alcaraz",
         "winner": False, "sets_won": 0},
    ])
    espn.to_parquet(espn_path)
    out_path = tmp_path / "matches_2026.parquet"
    df, diag = mod.build_matches_2026(espn_path, players_path, out_path)
    assert diag["matches_both_resolved"] == 1
    assert diag["matches_dropped_unresolved_name"] == 1
    assert len(df) == 1
    row = df.iloc[0]
    assert {row["p1_id"], row["p2_id"]} == {1, 2}
    assert row["surface"] == "Hard"
    assert out_path.exists()
