"""Per-file test for domains.basketball_wnba.profiles.attribute_registry:
registry shape/integrity only -- no parquet reads.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/profiles/test_attribute_registry.py -q
"""
from __future__ import annotations

import pytest

from domains.basketball_wnba.profiles.attribute_registry import (
    ATTRIBUTES, ENTITIES, STATUSES, attributes_for, rating_2k,
)
from domains.basketball_wnba.profiles.ingredients_defzone import BUILDERS as DEFZONE_BUILDERS
from domains.basketball_wnba.profiles.ingredients_home_away import BUILDERS as HOME_AWAY_BUILDERS
from domains.basketball_wnba.profiles.ingredients_last10 import BUILDERS as LAST10_BUILDERS
from domains.basketball_wnba.profiles.ingredients_lineup import BUILDERS as LINEUP_BUILDERS
from domains.basketball_wnba.profiles.ingredients_player import BUILDERS as PLAYER_BUILDERS
from domains.basketball_wnba.profiles.ingredients_schedule_rest import BUILDERS as SCHEDULE_REST_BUILDERS
from domains.basketball_wnba.profiles.ingredients_team_form import BUILDERS as TEAM_FORM_BUILDERS
from domains.basketball_wnba.profiles.ingredients_zone import BUILDERS as ZONE_BUILDERS


def test_registry_builder_parity():
    all_builders = {
        **PLAYER_BUILDERS, **LINEUP_BUILDERS, **ZONE_BUILDERS, **DEFZONE_BUILDERS, **LAST10_BUILDERS,
        **HOME_AWAY_BUILDERS, **SCHEDULE_REST_BUILDERS, **TEAM_FORM_BUILDERS,
    }
    assert set(ATTRIBUTES) == set(all_builders)


@pytest.mark.parametrize("attr,spec", list(ATTRIBUTES.items()))
def test_registry_entry_shape(attr, spec):
    for key in ("description", "entity", "ingredients", "formula", "status",
                "floor", "weight_ledger_family", "source_files"):
        assert key in spec, f"{attr} missing {key!r}"
    assert spec["entity"] in ENTITIES
    assert spec["status"] in STATUSES
    assert isinstance(spec["floor"], int) and spec["floor"] > 0
    assert isinstance(spec["ingredients"], list) and len(spec["ingredients"]) >= 2
    assert isinstance(spec["source_files"], list) and len(spec["source_files"]) >= 1


def test_attributes_for_entity_split():
    players = attributes_for("player")
    lineups = attributes_for("lineup")
    teams = attributes_for("team")
    # 28 (8 original + 07-08 expansion: 10 zone + 1 assisted_share + 4 defzone + 5 last10)
    # + 07-18 build spec: 2 rest_split + 6 home_away = 36
    assert len(players) == 36
    assert len(lineups) == 3
    # 07-18 build spec: 3 schedule-rest team attrs + 10 team_form attrs = 13
    assert len(teams) == 13
    assert set(players) | set(lineups) | set(teams) == set(ATTRIBUTES)


def test_status_family_consistency():
    """VALIDATED_CLAIM attributes must carry a real (non-'descriptive')
    weight_ledger_family; DESCRIPTIVE ones are always 'descriptive' -- the
    two fields must never disagree."""
    for attr, spec in ATTRIBUTES.items():
        if spec["status"] == "VALIDATED_CLAIM":
            assert spec["weight_ledger_family"] != "descriptive", attr
        else:
            assert spec["weight_ledger_family"] == "descriptive", attr


def test_rating_2k_bounds_and_monotonic():
    assert rating_2k(0.0) == 25.0
    assert rating_2k(100.0) == pytest.approx(99.0)
    assert rating_2k(50.0) < rating_2k(75.0)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
