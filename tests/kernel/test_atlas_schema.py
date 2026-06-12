"""Tests for kernel.config.atlas_schema — AtlasSchema.

Hermetic, offline.  No heavy imports (stdlib + typing + dataclasses only).
Covers:
  1. An EMPTY AtlasSchema (sport_id only, empty sections) instantiates without error.
  2. An NBA-shaped instance with 28 player_sections + 16 team_sections instantiates
     and reports the correct counts.
  3. Frozen-ness: attribute assignment raises FrozenInstanceError.
  4. dim_to_section maps a sample dimension key to the correct section.
  5. resolve_section() returns None for an unmapped key.
  6. all_sections() returns player + team concatenated in order.
  7. player_section_count / team_section_count properties.
"""
from __future__ import annotations

import dataclasses

import pytest

from kernel.config.atlas_schema import AtlasSchema

# ---------------------------------------------------------------------------
# NBA-shaped literals
# ---------------------------------------------------------------------------
# 28 player-level atlas section names (representative; order is stable)
_NBA_PLAYER_SECTIONS: tuple[str, ...] = (
    "shot_profile",
    "clutch_scoring",
    "rebounding_profile",
    "usage_role",
    "defensive_profile",
    "scoring_creation",
    "playmaking_network",
    "isolation_profile",
    "pick_and_roll_profile",
    "post_up_profile",
    "transition_scoring",
    "catch_shoot_vs_pullup",
    "shot_clock_scoring",
    "foul_drawing",
    "foul_tendency",
    "ft_profile",
    "matchup_splits",
    "rest_b2b_splits",
    "monthly_form",
    "form_streak_dynamics",
    "durability_load",
    "quarter_shape_fatigue",
    "pace_fit",
    "spacing_gravity",
    "score_margin_splits",
    "situational_splits",
    "turnover_profile",
    "vs_scheme_splits",
)

# 16 team-level atlas section names (representative)
_NBA_TEAM_SECTIONS: tuple[str, ...] = (
    "offensive_scheme",
    "defensive_scheme",
    "pace_identity",
    "halfcourt_offense",
    "transition_halfcourt_splits",
    "transition_defense",
    "paint_defense",
    "three_pt_defense",
    "rebounding_scheme",
    "clutch_team",
    "bench_production",
    "lineup_synergy",
    "rotation_patterns",
    "matchup_adjustments",
    "ft_foul_environment",
    "turnover_forcing",
)

# Sample dim_to_section mapping (mirrors _DIM_TO_ATLAS in src/loop/error_miner.py)
_NBA_DIM_TO_SECTION: dict[str, str] = {
    "game_state:blowout": "score_margin_splits",
    "game_state:clutch":  "clutch_scoring",
    "quarter:Q4":         "quarter_shape_fatigue",
    "quarter:Q1":         "quarter_shape_fatigue",
}

# Sample entity frontmatter descriptor
_NBA_FRONTMATTER: dict[str, str] = {
    "player_id": "str",
    "name":      "str",
    "team":      "str",
    "position":  "str",
    "season":    "str",
}


def _make_nba_schema() -> AtlasSchema:
    """Build a full NBA-shaped AtlasSchema from literals."""
    return AtlasSchema(
        sport_id="nba",
        player_sections=_NBA_PLAYER_SECTIONS,
        team_sections=_NBA_TEAM_SECTIONS,
        entity_frontmatter=_NBA_FRONTMATTER,
        dim_to_section=_NBA_DIM_TO_SECTION,
    )


# ===========================================================================
# 1. Empty AtlasSchema — valid new-sport launch state
# ===========================================================================

class TestEmptyAtlasSchema:
    def test_instantiates_with_sport_id_only(self) -> None:
        """An empty AtlasSchema must construct without error."""
        schema = AtlasSchema(sport_id="new_sport")
        assert schema.sport_id == "new_sport"

    def test_empty_player_sections(self) -> None:
        schema = AtlasSchema(sport_id="new_sport")
        assert schema.player_sections == ()

    def test_empty_team_sections(self) -> None:
        schema = AtlasSchema(sport_id="new_sport")
        assert schema.team_sections == ()

    def test_empty_dim_to_section(self) -> None:
        schema = AtlasSchema(sport_id="new_sport")
        assert len(schema.dim_to_section) == 0

    def test_empty_entity_frontmatter(self) -> None:
        schema = AtlasSchema(sport_id="new_sport")
        assert len(schema.entity_frontmatter) == 0

    def test_empty_counts_are_zero(self) -> None:
        schema = AtlasSchema(sport_id="new_sport")
        assert schema.player_section_count == 0
        assert schema.team_section_count == 0

    def test_all_sections_empty(self) -> None:
        schema = AtlasSchema(sport_id="new_sport")
        assert schema.all_sections() == ()

    def test_resolve_section_returns_none_when_empty(self) -> None:
        schema = AtlasSchema(sport_id="new_sport")
        assert schema.resolve_section("game_state:clutch") is None


# ===========================================================================
# 2. NBA-shaped instance — 28 player + 16 team sections
# ===========================================================================

class TestNBAShapedAtlasSchema:
    def test_instantiates(self) -> None:
        """NBA-shaped AtlasSchema must construct without error."""
        schema = _make_nba_schema()
        assert schema.sport_id == "nba"

    def test_player_section_count(self) -> None:
        schema = _make_nba_schema()
        assert schema.player_section_count == 28, (
            f"Expected 28 player sections, got {schema.player_section_count}"
        )

    def test_team_section_count(self) -> None:
        schema = _make_nba_schema()
        assert schema.team_section_count == 16, (
            f"Expected 16 team sections, got {schema.team_section_count}"
        )

    def test_player_sections_length(self) -> None:
        schema = _make_nba_schema()
        assert len(schema.player_sections) == 28

    def test_team_sections_length(self) -> None:
        schema = _make_nba_schema()
        assert len(schema.team_sections) == 16

    def test_player_sections_are_tuple(self) -> None:
        schema = _make_nba_schema()
        assert isinstance(schema.player_sections, tuple)

    def test_team_sections_are_tuple(self) -> None:
        schema = _make_nba_schema()
        assert isinstance(schema.team_sections, tuple)

    def test_player_sections_distinct(self) -> None:
        """All 28 player section names must be distinct."""
        schema = _make_nba_schema()
        assert len(set(schema.player_sections)) == len(schema.player_sections)

    def test_team_sections_distinct(self) -> None:
        """All 16 team section names must be distinct."""
        schema = _make_nba_schema()
        assert len(set(schema.team_sections)) == len(schema.team_sections)

    def test_sample_player_section_present(self) -> None:
        schema = _make_nba_schema()
        assert "shot_profile" in schema.player_sections
        assert "clutch_scoring" in schema.player_sections
        assert "defensive_profile" in schema.player_sections

    def test_sample_team_section_present(self) -> None:
        schema = _make_nba_schema()
        assert "offensive_scheme" in schema.team_sections
        assert "defensive_scheme" in schema.team_sections
        assert "pace_identity" in schema.team_sections


# ===========================================================================
# 3. Frozen-ness
# ===========================================================================

class TestAtlasSchemaFrozen:
    def test_frozen_sport_id(self) -> None:
        """Assigning sport_id must raise FrozenInstanceError."""
        schema = _make_nba_schema()
        with pytest.raises(dataclasses.FrozenInstanceError):
            schema.sport_id = "nfl"  # type: ignore[misc]

    def test_frozen_player_sections(self) -> None:
        schema = _make_nba_schema()
        with pytest.raises(dataclasses.FrozenInstanceError):
            schema.player_sections = ()  # type: ignore[misc]

    def test_frozen_team_sections(self) -> None:
        schema = _make_nba_schema()
        with pytest.raises(dataclasses.FrozenInstanceError):
            schema.team_sections = ()  # type: ignore[misc]

    def test_frozen_dim_to_section(self) -> None:
        schema = _make_nba_schema()
        with pytest.raises(dataclasses.FrozenInstanceError):
            schema.dim_to_section = {}  # type: ignore[misc]

    def test_frozen_empty_schema(self) -> None:
        """Empty schema must also be frozen."""
        schema = AtlasSchema(sport_id="test")
        with pytest.raises(dataclasses.FrozenInstanceError):
            schema.sport_id = "other"  # type: ignore[misc]

    def test_player_sections_tuple_is_immutable(self) -> None:
        """player_sections is a tuple — element assignment must raise TypeError."""
        schema = _make_nba_schema()
        with pytest.raises(TypeError):
            schema.player_sections[0] = "other"  # type: ignore[index]


# ===========================================================================
# 4. dim_to_section — maps sample dimensions to correct sections
# ===========================================================================

class TestDimToSection:
    def test_clutch_maps_to_clutch_scoring(self) -> None:
        schema = _make_nba_schema()
        assert schema.dim_to_section["game_state:clutch"] == "clutch_scoring"

    def test_blowout_maps_to_score_margin_splits(self) -> None:
        schema = _make_nba_schema()
        assert schema.dim_to_section["game_state:blowout"] == "score_margin_splits"

    def test_quarter_maps_to_quarter_shape_fatigue(self) -> None:
        schema = _make_nba_schema()
        assert schema.dim_to_section["quarter:Q4"] == "quarter_shape_fatigue"

    def test_resolve_section_clutch(self) -> None:
        """resolve_section() must return the same result as direct dict lookup."""
        schema = _make_nba_schema()
        assert schema.resolve_section("game_state:clutch") == "clutch_scoring"

    def test_resolve_section_unmapped_returns_none(self) -> None:
        """An unknown dim_key must return None, not raise."""
        schema = _make_nba_schema()
        result = schema.resolve_section("nonexistent:dim")
        assert result is None

    def test_resolve_section_returns_string(self) -> None:
        schema = _make_nba_schema()
        result = schema.resolve_section("game_state:blowout")
        assert isinstance(result, str)


# ===========================================================================
# 5. all_sections() — player + team concatenated
# ===========================================================================

class TestAllSections:
    def test_all_sections_length(self) -> None:
        """all_sections() must return player + team (28 + 16 = 44)."""
        schema = _make_nba_schema()
        assert len(schema.all_sections()) == 44

    def test_all_sections_returns_tuple(self) -> None:
        schema = _make_nba_schema()
        assert isinstance(schema.all_sections(), tuple)

    def test_all_sections_player_prefix(self) -> None:
        """First 28 elements of all_sections() must equal player_sections."""
        schema = _make_nba_schema()
        assert schema.all_sections()[:28] == schema.player_sections

    def test_all_sections_team_suffix(self) -> None:
        """Last 16 elements of all_sections() must equal team_sections."""
        schema = _make_nba_schema()
        assert schema.all_sections()[28:] == schema.team_sections

    def test_all_sections_empty_schema(self) -> None:
        schema = AtlasSchema(sport_id="test")
        assert schema.all_sections() == ()
