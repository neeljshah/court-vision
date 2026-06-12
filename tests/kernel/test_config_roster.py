"""Tests for kernel.config.roster — PositionSchema + RosterConfig.

Hermetic, offline.  No heavy imports (stdlib + typing + dataclasses only).
Covers:
  1. NBA RosterConfig instantiates with exact expected values.
  2. RosterConfig is frozen (FrozenInstanceError on attribute set).
  3. PositionSchema is frozen (FrozenInstanceError on attribute set).
  4. NBA positions tuple has the 5 positions in the canonical order.
  5. PositionSchema membership test (__contains__).
  6. PositionSchema.index() returns the correct 0-based index.
  7. RosterConfig.__post_init__ rejects invalid substitution_model.
  8. RosterConfig.__post_init__ rejects degenerate numeric values.
"""
from __future__ import annotations

import dataclasses

import pytest

from kernel.config.roster import PositionSchema, RosterConfig

# ---------------------------------------------------------------------------
# Canonical NBA position taxonomy — used throughout the test suite
# ---------------------------------------------------------------------------

_NBA_POSITIONS: tuple[str, ...] = ("PG", "SG", "SF", "PF", "C")

_NBA_POSITION_SCHEMA = PositionSchema(positions=_NBA_POSITIONS)

# ---------------------------------------------------------------------------
# Factory: the canonical NBA RosterConfig instance (from spec literals)
# ---------------------------------------------------------------------------

def _make_nba_roster() -> RosterConfig:
    """Build the NBA-shaped RosterConfig from spec literals (P0-D-004)."""
    return RosterConfig(
        on_field_count=5,
        roster_size=15,
        season_length_games=82,
        positions=_NBA_POSITION_SCHEMA,
        substitution_model="free",
        foul_out_limit=6,
        reach_ft=6.0,
    )


# ===========================================================================
# 1. NBA instance — exact field values
# ===========================================================================

class TestNBARosterConfigValues:
    """Verify the canonical NBA instance carries each spec-mandated value."""

    def test_on_field_count(self) -> None:
        assert _make_nba_roster().on_field_count == 5

    def test_roster_size(self) -> None:
        assert _make_nba_roster().roster_size == 15

    def test_season_length_games(self) -> None:
        assert _make_nba_roster().season_length_games == 82

    def test_substitution_model(self) -> None:
        assert _make_nba_roster().substitution_model == "free"

    def test_foul_out_limit(self) -> None:
        assert _make_nba_roster().foul_out_limit == 6

    def test_reach_ft(self) -> None:
        assert _make_nba_roster().reach_ft == 6.0

    def test_positions_is_position_schema(self) -> None:
        """The positions field must be a PositionSchema instance."""
        cfg = _make_nba_roster()
        assert isinstance(cfg.positions, PositionSchema)

    def test_positions_tuple_identity(self) -> None:
        """The PositionSchema's positions tuple must equal the NBA 5-tuple."""
        cfg = _make_nba_roster()
        assert cfg.positions.positions == _NBA_POSITIONS


# ===========================================================================
# 2. RosterConfig — frozen (FrozenInstanceError on attribute set)
# ===========================================================================

class TestRosterConfigFrozen:
    def test_frozen_on_field_count(self) -> None:
        cfg = _make_nba_roster()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.on_field_count = 6  # type: ignore[misc]

    def test_frozen_roster_size(self) -> None:
        cfg = _make_nba_roster()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.roster_size = 16  # type: ignore[misc]

    def test_frozen_season_length_games(self) -> None:
        cfg = _make_nba_roster()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.season_length_games = 17  # type: ignore[misc]

    def test_frozen_substitution_model(self) -> None:
        cfg = _make_nba_roster()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.substitution_model = "platoon"  # type: ignore[misc]

    def test_frozen_foul_out_limit(self) -> None:
        cfg = _make_nba_roster()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.foul_out_limit = 5  # type: ignore[misc]

    def test_frozen_reach_ft(self) -> None:
        cfg = _make_nba_roster()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.reach_ft = 7.0  # type: ignore[misc]

    def test_frozen_positions(self) -> None:
        cfg = _make_nba_roster()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.positions = PositionSchema(positions=("GK",))  # type: ignore[misc]

    def test_frozen_new_attr(self) -> None:
        """Assigning a brand-new attribute must also raise."""
        cfg = _make_nba_roster()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            cfg.custom = "x"  # type: ignore[attr-defined]


# ===========================================================================
# 3. PositionSchema — frozen (FrozenInstanceError on attribute set)
# ===========================================================================

class TestPositionSchemaFrozen:
    def test_frozen_positions_tuple(self) -> None:
        schema = PositionSchema(positions=_NBA_POSITIONS)
        with pytest.raises(dataclasses.FrozenInstanceError):
            schema.positions = ("GK", "FWD")  # type: ignore[misc]

    def test_frozen_archetypes(self) -> None:
        schema = PositionSchema(
            positions=_NBA_POSITIONS,
            archetypes={"guard": ("PG", "SG"), "big": ("PF", "C")},
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            schema.archetypes = {}  # type: ignore[misc]

    def test_frozen_new_attr(self) -> None:
        schema = PositionSchema(positions=_NBA_POSITIONS)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            schema.extra = "x"  # type: ignore[attr-defined]


# ===========================================================================
# 4. Positions taxonomy — 5 NBA positions in canonical order
# ===========================================================================

class TestNBAPositionsTaxonomy:
    def test_positions_count(self) -> None:
        """NBA position schema must have exactly 5 positions."""
        assert len(_NBA_POSITION_SCHEMA.positions) == 5

    def test_positions_type(self) -> None:
        """positions must be a tuple (not a list or other sequence)."""
        assert isinstance(_NBA_POSITION_SCHEMA.positions, tuple)

    def test_positions_canonical_order(self) -> None:
        """Full tuple must equal the canonical NBA 5-tuple in order."""
        assert _NBA_POSITION_SCHEMA.positions == ("PG", "SG", "SF", "PF", "C")

    @pytest.mark.parametrize(
        "idx, code",
        [(0, "PG"), (1, "SG"), (2, "SF"), (3, "PF"), (4, "C")],
    )
    def test_positions_element_by_element(self, idx: int, code: str) -> None:
        """Each position code must be at the correct index."""
        assert _NBA_POSITION_SCHEMA.positions[idx] == code, (
            f"positions[{idx}]: expected {code!r}, "
            f"got {_NBA_POSITION_SCHEMA.positions[idx]!r}"
        )

    def test_positions_immutable_tuple(self) -> None:
        """The positions tuple itself must be immutable (tuple assignment raises)."""
        with pytest.raises(TypeError):
            _NBA_POSITION_SCHEMA.positions[0] = "X"  # type: ignore[index]


# ===========================================================================
# 5. PositionSchema membership test (__contains__)
# ===========================================================================

class TestPositionSchemaMembership:
    @pytest.mark.parametrize("pos", ["PG", "SG", "SF", "PF", "C"])
    def test_valid_positions_are_members(self, pos: str) -> None:
        assert pos in _NBA_POSITION_SCHEMA

    @pytest.mark.parametrize("pos", ["GK", "QB", "LF", "SS", "TE", ""])
    def test_invalid_positions_not_members(self, pos: str) -> None:
        assert pos not in _NBA_POSITION_SCHEMA

    def test_membership_is_case_sensitive(self) -> None:
        """Lowercase variants must not match uppercase position codes."""
        assert "pg" not in _NBA_POSITION_SCHEMA
        assert "PG" in _NBA_POSITION_SCHEMA


# ===========================================================================
# 6. PositionSchema.index()
# ===========================================================================

class TestPositionSchemaIndex:
    @pytest.mark.parametrize(
        "pos, expected_idx",
        [("PG", 0), ("SG", 1), ("SF", 2), ("PF", 3), ("C", 4)],
    )
    def test_index_correct(self, pos: str, expected_idx: int) -> None:
        assert _NBA_POSITION_SCHEMA.index(pos) == expected_idx

    def test_index_unknown_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            _NBA_POSITION_SCHEMA.index("QB")


# ===========================================================================
# 7. RosterConfig — substitution_model validation
# ===========================================================================

class TestRosterConfigSubstitutionModel:
    @pytest.mark.parametrize(
        "model", ["free", "platoon", "limited", "none"]
    )
    def test_valid_substitution_models_accepted(self, model: str) -> None:
        cfg = RosterConfig(
            on_field_count=5,
            roster_size=15,
            season_length_games=82,
            positions=_NBA_POSITION_SCHEMA,
            substitution_model=model,  # type: ignore[arg-type]
        )
        assert cfg.substitution_model == model

    @pytest.mark.parametrize(
        "bad_model", ["unlimited", "Free", "PLATOON", "", "hybrid"]
    )
    def test_invalid_substitution_model_raises(self, bad_model: str) -> None:
        with pytest.raises(ValueError, match="substitution_model"):
            RosterConfig(
                on_field_count=5,
                roster_size=15,
                season_length_games=82,
                positions=_NBA_POSITION_SCHEMA,
                substitution_model=bad_model,  # type: ignore[arg-type]
            )


# ===========================================================================
# 8. RosterConfig — degenerate numeric value validation
# ===========================================================================

class TestRosterConfigNumericValidation:
    def test_on_field_count_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="on_field_count"):
            RosterConfig(
                on_field_count=0,
                roster_size=15,
                season_length_games=82,
                positions=_NBA_POSITION_SCHEMA,
            )

    def test_roster_size_less_than_on_field_raises(self) -> None:
        with pytest.raises(ValueError, match="roster_size"):
            RosterConfig(
                on_field_count=5,
                roster_size=4,
                season_length_games=82,
                positions=_NBA_POSITION_SCHEMA,
            )

    def test_season_length_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="season_length_games"):
            RosterConfig(
                on_field_count=5,
                roster_size=15,
                season_length_games=0,
                positions=_NBA_POSITION_SCHEMA,
            )

    def test_reach_ft_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="reach_ft"):
            RosterConfig(
                on_field_count=5,
                roster_size=15,
                season_length_games=82,
                positions=_NBA_POSITION_SCHEMA,
                reach_ft=0.0,
            )

    def test_reach_ft_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="reach_ft"):
            RosterConfig(
                on_field_count=5,
                roster_size=15,
                season_length_games=82,
                positions=_NBA_POSITION_SCHEMA,
                reach_ft=-1.0,
            )

    def test_roster_size_equals_on_field_allowed(self) -> None:
        """Edge case: roster_size == on_field_count is valid (single-unit sport)."""
        cfg = RosterConfig(
            on_field_count=1,
            roster_size=1,
            season_length_games=10,
            positions=PositionSchema(positions=("SINGLES",)),
        )
        assert cfg.on_field_count == cfg.roster_size == 1
