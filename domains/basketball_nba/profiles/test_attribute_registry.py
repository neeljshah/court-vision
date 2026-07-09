"""Per-file test: registry integrity -- every ingredient whose `source`
string names a concrete parquet path resolves to a real file on disk for
EVERY season the attribute declares (or the attribute must not declare that
season). Non-file ingredient sources (JSON-column caveats, lineup_key
membership notes) are skipped -- only genuine ".parquet" paths are checked.

Run: python -m pytest domains/basketball_nba/profiles/test_attribute_registry.py -q
"""
from __future__ import annotations

import re

from domains.basketball_nba.profiles.attribute_registry import (
    ATTRIBUTES, CONCESSION_COLS, CONCESSION_LOWER_IS_BETTER, LINEUP_ATTRIBUTES,
    PLAYER_ATTRIBUTES, SHOT_DIET_COLS, TEAM_ATTRIBUTES,
)
from domains.basketball_nba.profiles.profile_compute import REPO_ROOT

_VALID_STATUS = {"VALIDATED_MECHANISM", "VALIDATED_CLAIM", "DESCRIPTIVE"}
_VALID_ENTITY = {"player", "team", "lineup"}


def _resolve_source(source: str, season: str) -> list[str]:
    """Every whitespace-separated token containing '.parquet' -> a real repo-
    relative path. Registry sources are written shorthand (relative to
    data/cache/, e.g. 'team_system/lineups/x.parquet') UNLESS already
    data-rooted (e.g. 'data/domains/basketball_nba/player_boxscores.parquet')."""
    tokens = re.findall(r"\S*\.parquet", source)
    resolved = []
    for t in tokens:
        t = t.replace("<season>", season)
        resolved.append(t if t.startswith("data/") else f"data/cache/{t}")
    return resolved


def test_every_attribute_has_required_fields():
    for name, spec in ATTRIBUTES.items():
        for key in ("description", "entity", "ingredients", "formula", "status", "floor", "seasons"):
            assert key in spec, f"{name} missing {key!r}"
        assert spec["entity"] in _VALID_ENTITY, f"{name} bad entity {spec['entity']!r}"
        assert spec["status"] in _VALID_STATUS, f"{name} bad status {spec['status']!r}"
        assert isinstance(spec["floor"], dict) and spec["floor"], f"{name} floor must be a non-empty dict"
        assert isinstance(spec["seasons"], list) and spec["seasons"], f"{name} seasons must be non-empty"
        assert "verifiable_by_design" in spec, f"{name} missing verifiable_by_design"


def test_ingredient_sources_resolve_on_disk_for_every_declared_season():
    missing: list[str] = []
    for name, spec in ATTRIBUTES.items():
        for season in spec["seasons"]:
            for ingredient in spec["ingredients"]:
                for path_str in _resolve_source(ingredient["source"], season):
                    if not (REPO_ROOT / path_str).exists():
                        missing.append(f"{name}/{season}: {path_str}")
    assert not missing, f"ingredient sources not on disk (registry drifted from real artifacts): {missing}"


def test_no_disallowed_edge_language():
    banned = ("edge", "roi", "profit", "$")
    for name, spec in ATTRIBUTES.items():
        text = (spec["description"] + spec["formula"]).lower()
        for word in banned:
            assert word not in text, f"{name} formula/description contains {word!r}"


def test_shot_diet_and_concession_col_lists_are_disjoint_and_covered():
    # every registry entry that references these column lists must stay
    # in sync -- a silent column-name typo here breaks team_attributes.py
    # at runtime, not at import time, so pin it here.
    assert set(SHOT_DIET_COLS).isdisjoint(CONCESSION_COLS)
    assert CONCESSION_LOWER_IS_BETTER <= set(CONCESSION_COLS)
    assert "share_assisted_allowed" not in CONCESSION_LOWER_IS_BETTER


def test_registry_partition_matches_combined_dict():
    assert set(ATTRIBUTES) == set(PLAYER_ATTRIBUTES) | set(TEAM_ATTRIBUTES) | set(LINEUP_ATTRIBUTES)
    assert len(ATTRIBUTES) == len(PLAYER_ATTRIBUTES) + len(TEAM_ATTRIBUTES) + len(LINEUP_ATTRIBUTES)
