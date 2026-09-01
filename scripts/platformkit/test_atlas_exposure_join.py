"""Fixture-only tests for atlas_exposure_join (per-file tests ONLY -- no full pytest run)."""
from scripts.platformkit.atlas_exposure_join import (
    build, join_rows, strength_atlas_cache, team_deltas, team_mechanism_counts,
)

ATLAS = {
    "generated_at": "2026-09-01T00:00:00+00:00",
    "sports": {
        "basketball_nba": {
            "status": "ok", "as_of": "2026-05-23", "source": "data/domains/basketball_nba/odds.parquet",
            "latest_ratings": {
                "top_5": [{"team": "OKC", "rating": 1728.092}],
                "bottom_5": [{"team": "WAS", "rating": 1350.0}],
            },
        },
        "soccer": {"status": "skipped", "as_of": None, "note": "no two-sided market"},
    },
}

EXPOSURE = {
    "as_of": "2026-05-24",
    "game_sheets": [
        {"game_id": "g1", "date": "2025-10-24", "home_team": "OKC", "away_team": "WAS",
         "exposures": [{"mechanism": "14. Back-to-back (B2B) rest penalty"}]},
        {"game_id": "g2", "date": "2025-11-01", "home_team": "OKC", "away_team": "SAS",
         "exposures": []},
    ],
}


def test_team_deltas_skips_non_ok_sport_and_uses_start_rating():
    deltas = team_deltas(ATLAS["sports"]["basketball_nba"])
    assert deltas == {"OKC": 228.092, "WAS": -150.0}
    assert team_deltas(ATLAS["sports"]["soccer"]) == {}


def test_team_mechanism_counts_tallies_across_all_of_a_teams_games():
    counts = team_mechanism_counts(EXPOSURE["game_sheets"])
    # OKC appears in both g1 (exposure) and g2 (none) -> one B2B game total.
    assert counts["OKC"] == {"14. Back-to-back (B2B) rest penalty": 1}
    assert counts["WAS"] == {"14. Back-to-back (B2B) rest penalty": 1}
    assert counts.get("SAS", {}) == {}


def test_join_rows_sorted_by_absolute_delta_and_cites_both_artifacts():
    rows = join_rows(ATLAS, EXPOSURE)
    assert [r["team"] for r in rows] == ["OKC", "WAS"]  # |228.092| > |150.0|
    assert rows[1]["live_mechanism_game_counts"] == {"14. Back-to-back (B2B) rest penalty": 1}


def test_strength_atlas_cache_envelope_has_contract_fields():
    cache = strength_atlas_cache(ATLAS)
    assert cache["status"] == "ok"
    assert cache["source_artifact"].startswith("scripts/platformkit/analytics_showcase/out/")
    assert cache["as_of"] == "2026-05-23"
    assert cache["source_corpus"]["basketball_nba"] == "data/domains/basketball_nba/odds.parquet"
    assert cache["edge_claimed"] is False


def test_build_is_descriptive_only_and_cites_both_sources():
    result = build(ATLAS, EXPOSURE)
    assert result["edge_claimed"] is False
    assert result["source_artifact"] == [
        "scripts/platformkit/analytics_showcase/out/market_strength_atlas.json",
        "scripts/platformkit/analytics_showcase/out/mechanism_exposure.json",
    ]
    assert result["as_of"] == "2026-05-24"  # max of the two source as_of values
    assert result["n_teams"] == 2
    assert "edge" not in result["verdict"].lower()


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
