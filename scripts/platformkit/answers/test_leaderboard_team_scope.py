"""Per-file test: coverage_stress Family D additions -- team-scoped
leaderboard, category aliases, and the concept-miss -> leaderboard-top-1
superlative bridge. Synthetic profiles df + synthetic player_boxscores
parquet, no data/ dependency.

Run: python -m pytest scripts/platformkit/answers/test_leaderboard_team_scope.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.answers import leaderboard_resolver as LB
from scripts.platformkit.answers import resolver_registry as R


def _row(entity_id, entity_name, attribute, raw_value, window="season_2024_25",
         percentile=50.0, n=250.0, status="DESCRIPTIVE"):
    return {"entity_id": entity_id, "entity_name": entity_name, "sport": "nba", "kind": "player",
            "window": window, "attribute": attribute, "raw_value": raw_value, "percentile": percentile,
            "rating_2k": 62.0, "n": n, "ingredients": json.dumps({}), "status": status, "sources": "synthetic"}


def _profiles_df():
    return pd.DataFrame([
        _row(1, "Nikola Jokic", "reb_per36", 14.0),
        _row(2, "Jamal Murray", "reb_per36", 4.5),
        _row(3, "LeBron James", "reb_per36", 7.0),
    ])


@pytest.fixture
def profiles(monkeypatch):
    df = _profiles_df()
    monkeypatch.setattr(LB._ask, "load_profiles", lambda *a, **k: df)
    return df


@pytest.fixture
def crosswalk(tmp_path, monkeypatch):
    """entity_id 1,2 -> DEN; entity_id 3 -> LAL, via a synthetic
    player_boxscores.parquet (only player_id/team/date are read)."""
    box = pd.DataFrame([
        {"player_id": 1, "team": "DEN", "date": "2024-11-01"},
        {"player_id": 2, "team": "DEN", "date": "2024-11-01"},
        {"player_id": 3, "team": "LAL", "date": "2024-11-01"},
    ])
    box_path = tmp_path / "player_boxscores.parquet"
    box.to_parquet(box_path, index=False)
    monkeypatch.setattr(LB, "_NBA_BOX", box_path)
    return box_path


# ---------------------------------------------------------------------------
# Team-scoped leaderboard
# ---------------------------------------------------------------------------
def test_team_scope_filters_to_roster(profiles, crosswalk):
    r = LB.leaderboard("nba", "reb_per36", top_n=10, team="Nuggets")
    assert r["status"] == "ok"
    ids = {row["entity_id"] for row in r["rows"]}
    assert ids == {1, 2}  # Jokic + Murray, not LeBron
    assert r["team"] == "Nuggets"


def test_team_scope_unresolved_team_name_is_not_supported(profiles, crosswalk):
    r = LB.leaderboard("nba", "reb_per36", team="Not A Real Team")
    assert r["status"] == "not_supported"


def test_team_scope_non_nba_sport_is_not_supported(profiles):
    r = LB.leaderboard("mlb", "reb_per36", team="Nuggets")
    assert r["status"] == "not_supported"


def test_team_scope_missing_crosswalk_is_no_data(profiles, tmp_path, monkeypatch):
    monkeypatch.setattr(LB, "_NBA_BOX", tmp_path / "nope.parquet")
    r = LB.leaderboard("nba", "reb_per36", team="Nuggets")
    assert r["status"] == "no_data"


def test_who_leads_the_team_in_x_query_parses_and_resolves(profiles, crosswalk):
    assert LB.is_ranking_query("who leads the Nuggets in reb_per36")
    r = R.resolve("who leads the Nuggets in reb_per36", sport="nba")
    assert r["status"] == "ok"
    assert r["category"] == "ranking"
    ids = {row["entity_id"] for row in r["rows"]}
    assert ids == {1, 2}


# ---------------------------------------------------------------------------
# Category aliases (pure routing onto attributes that already exist)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("category,expected", [
    ("corner three", "zone_efg_corner3"),
    ("wing", "zone_efg_above_break_3"),
    ("deep", "zone_efg_above_break_3"),
    ("free throw shooter", "ft_pct"),
    ("three point percentage", "fg3_pct"),
    ("three-point percentage", "fg3_pct"),
    ("points per game", "ppg"),
])
def test_category_alias_resolves_to_one_real_attribute(category, expected):
    # uses the REAL attribute_registry.py (importable with no data/ dependency)
    candidates = LB._candidate_attributes("nba", category)
    assert candidates == [expected]


# ---------------------------------------------------------------------------
# Bare-superlative -> leaderboard bridge (concept-rating miss)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query,expected_residual", [
    ("Who is the best free throw shooter?", "free throw shooter"),
    ("Who is the sharpest shooter?", "shooter"),
    ("Who has the highest three-point percentage in the NBA?", "three-point percentage"),
    ("Who shoots best from the corner three?", "corner three"),
    ("top 5 gravity", None),  # not a superlative shape -- no bridge needed
])
def test_superlative_category_extraction(query, expected_residual):
    assert R._superlative_category(query) == expected_residual


def test_concept_miss_bridges_to_leaderboard(monkeypatch, profiles):
    # force a concept miss (no registered concept matched) so the bridge fires
    monkeypatch.setattr(R._contracts, "answer_question", lambda *a, **k: {"error": "no concept"})
    monkeypatch.setattr(R, "_CONCEPT_SPORTS", {"nba"})
    r = R.resolve("Who is the best reb_per36?", sport="nba", category="concept_rating")
    assert r["status"] == "ok"
    assert r["category"] == "ranking"
    assert r["attribute"] == "reb_per36"
