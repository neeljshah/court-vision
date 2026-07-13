"""Tests for scripts.platformkit.models.registry."""

import copy

from scripts.platformkit.models import registry


def test_validate_real_registry_green():
    issues = registry.validate()
    assert issues == [], issues


def test_every_market_has_champion_and_challenger():
    for sport, market in registry.all_markets():
        entry = registry.get_spec(sport, market)
        assert entry["champion"] is not None
        assert len(entry["challengers"]) >= 1


def test_grid_covers_at_least_four_sports():
    sports = {sport for sport, _market in registry.all_markets()}
    assert len(sports) >= 4


def test_get_spec_roundtrips_with_all_markets():
    for sport, market in registry.all_markets():
        assert registry.get_spec(sport, market) is registry.REGISTRY[(sport, market)]


def test_validate_catches_benchmark_marked_ok_without_artifact():
    bad_registry = copy.deepcopy(registry.REGISTRY)
    bad_key = ("mlb", "total_runs")
    bad_registry[bad_key]["challengers"][0]["benchmark"] = (
        "scripts/platformkit/benchmarks/crps_market/does_not_exist.json"
    )
    bad_registry[bad_key]["challengers"][0]["oos_status"] = "BENCHMARKED"

    saved = registry.REGISTRY
    registry.REGISTRY = bad_registry
    try:
        issues = registry.validate()
    finally:
        registry.REGISTRY = saved

    assert any("missing on disk" in i for i in issues)


def test_validate_catches_duplicate_model_id():
    bad_registry = copy.deepcopy(registry.REGISTRY)
    bad_registry[("nba", "ml")]["challengers"][0]["model_id"] = (
        bad_registry[("nba", "ml")]["champion"]["model_id"]
    )

    saved = registry.REGISTRY
    registry.REGISTRY = bad_registry
    try:
        issues = registry.validate()
    finally:
        registry.REGISTRY = saved

    assert any("duplicate model_id" in i for i in issues)
