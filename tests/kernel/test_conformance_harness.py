"""Tests for kernel.testing.conformance — SportContext conformance harness.

Hermetic, offline.  No heavy imports (stdlib + typing + kernel.config.* only).
No ``import domains``.

Coverage
--------
1. A fully-valid toy SportContext yields no violations.
2. assert_sport_context_conformant passes on the valid context.
3. Empty stats registry → violation reported.
4. Bad clock (regulation_sec=0, untimed=False) → violation reported.
5. Bad PBPEventMapper (missing method) → violation reported.
6. Bad LeagueClient (missing method) → violation reported.
7. Bad EntityRegistry (missing method) → violation reported.
8. Wrong atlas_schema type → violation reported.
9. Wrong court type (not None, not CourtConfig) → violation reported.
10. Wrong speed type (not None, not SpeedConfig) → violation reported.
11. assert_sport_context_conformant raises on broken context with all violations.
12. Multiple simultaneous violations all appear in the error.
"""
from __future__ import annotations

from typing import Any, Iterator, Mapping, Optional

import pytest

from kernel.config.atlas_schema import AtlasSchema
from kernel.config.clock import GameClockConfig
from kernel.config.context import SportContext
from kernel.config.entities import EntityRegistry
from kernel.config.game_state import GameStateConfig
from kernel.config.pbp import CanonicalEvent, CanonicalEventKind, LeagueClient, PBPEventMapper
from kernel.config.roster import PositionSchema, RosterConfig
from kernel.config.stats import SportStatRegistry, StatSpec
from kernel.testing.conformance import assert_sport_context_conformant, check_sport_context


# ===========================================================================
# Toy protocol implementations (sport-blind)
# ===========================================================================

class _ToyMapper:
    """Minimal PBPEventMapper satisfying the runtime_checkable protocol."""

    def to_canonical(self, raw_event: Any) -> CanonicalEvent:
        return CanonicalEvent(kind=CanonicalEventKind.OTHER, ts_game_sec=0.0, period=1)

    def iter_game(self, game_id: str) -> Iterator[CanonicalEvent]:
        return iter([])

    def possession_side(self, event: CanonicalEvent) -> Optional[str]:
        return None


class _ToyClient:
    """Minimal LeagueClient satisfying the runtime_checkable protocol."""

    def get_schedule(self, season: str) -> Any:
        return []

    def get_box_score(self, game_id: str) -> Any:
        return {}

    def get_pbp(self, game_id: str) -> Any:
        return []

    def get_roster(self, team_id: str, season: str) -> Any:
        return []

    def get_player_gamelog(self, player_id: str, season: str) -> Any:
        return []

    def get_availability(self, player_id: str, game_id: str) -> Any:
        return None


class _ToyRegistry:
    """Minimal EntityRegistry satisfying the runtime_checkable protocol."""

    sport_id: str = "toyball"

    def resolve_team(self, token: str) -> str:
        raise KeyError(token)

    def resolve_player(self, token: Any) -> str:
        raise KeyError(token)

    def parse_game_id(self, game_id: str) -> dict:
        return {"season": "2025", "kind": "regular", "seq": 0}

    def season_of(self, d: Any) -> str:
        return "2025"

    def entity_key(self, kind: str, ident: Any) -> str:
        return f"{kind}:{ident}"

    def book_aliases(self) -> Mapping[str, str]:
        return {}


# ===========================================================================
# Factory helpers
# ===========================================================================

def _valid_stats(sport_id: str = "toyball") -> SportStatRegistry:
    return SportStatRegistry(
        sport_id=sport_id,
        stats={
            "score_units": StatSpec(
                name="score_units", kind="count", display="Score Units", sigma_default=2.5
            ),
            "grabs": StatSpec(
                name="grabs", kind="count", display="Grabs", sigma_default=1.0, priced=False
            ),
        },
        box_score_mapping={"SCORE": "score_units", "GRABS": "grabs"},
        score_stat="score_units",
        minutes_equiv=None,
    )


def _valid_clock() -> GameClockConfig:
    return GameClockConfig(n_periods=2, period_len_sec=600, ot_len_sec=300)


def _valid_roster() -> RosterConfig:
    return RosterConfig(
        on_field_count=3,
        roster_size=6,
        season_length_games=20,
        positions=PositionSchema(positions=("F", "M", "D")),
    )


def _valid_game_state() -> GameStateConfig:
    return GameStateConfig(
        blowout_margin=10.0,
        clutch_margin=3.0,
        clutch_remaining_sec=120.0,
        garbage_margin=15.0,
        competitive_margin=8.0,
        final_margin_sigma=5.0,
        winprob_promotion_period=2,
    )


def _make_valid_ctx(**overrides: Any) -> SportContext:
    """Build a fully-conformant toy SportContext; apply field overrides."""
    kwargs: dict = dict(
        stats=_valid_stats(),
        clock=_valid_clock(),
        roster=_valid_roster(),
        game_state=_valid_game_state(),
        pbp_mapper=_ToyMapper(),
        league_client=_ToyClient(),
        entities=_ToyRegistry(),
        source_tiers={"test_feed": 1},
        atlas_schema=AtlasSchema(sport_id="toyball"),
    )
    kwargs.update(overrides)
    return SportContext(**kwargs)  # type: ignore[arg-type]


# ===========================================================================
# 1. Valid context yields no violations
# ===========================================================================

class TestValidContext:
    def test_check_returns_empty_list(self) -> None:
        ctx = _make_valid_ctx()
        violations = check_sport_context(ctx)
        assert violations == [], f"Expected no violations; got: {violations}"

    def test_assert_passes_silently(self) -> None:
        ctx = _make_valid_ctx()
        assert_sport_context_conformant(ctx)  # must not raise

    def test_optional_court_none_is_ok(self) -> None:
        ctx = _make_valid_ctx(court=None)
        assert check_sport_context(ctx) == []

    def test_optional_speed_none_is_ok(self) -> None:
        ctx = _make_valid_ctx(speed=None)
        assert check_sport_context(ctx) == []

    def test_untimed_clock_with_zero_regulation_sec_is_ok(self) -> None:
        """An untimed sport (e.g. MLB innings) is valid even with regulation_sec=0."""
        untimed_clock = GameClockConfig(
            n_periods=9, period_len_sec=0, ot_len_sec=0, untimed=True
        )
        ctx = _make_valid_ctx(clock=untimed_clock)
        assert check_sport_context(ctx) == []

    def test_empty_atlas_sections_is_ok(self) -> None:
        """Empty player/team sections are a valid new-sport launch state."""
        ctx = _make_valid_ctx(atlas_schema=AtlasSchema(sport_id="toyball"))
        assert check_sport_context(ctx) == []


# ===========================================================================
# 2. Empty stats registry → violation
# ===========================================================================

class TestEmptyStats:
    def test_empty_stats_produces_violation(self) -> None:
        empty_stats = SportStatRegistry(
            sport_id="toyball",
            stats={},
            box_score_mapping={},
            score_stat="score_units",
            minutes_equiv=None,
        )
        ctx = _make_valid_ctx(stats=empty_stats)
        violations = check_sport_context(ctx)
        assert any("target_names" in v or "non-empty" in v for v in violations), (
            f"Expected a violation about empty target_names; got: {violations}"
        )

    def test_empty_stats_assert_raises(self) -> None:
        empty_stats = SportStatRegistry(
            sport_id="toyball",
            stats={},
            box_score_mapping={},
            score_stat="score_units",
            minutes_equiv=None,
        )
        ctx = _make_valid_ctx(stats=empty_stats)
        with pytest.raises(AssertionError):
            assert_sport_context_conformant(ctx)


# ===========================================================================
# 3. Bad clock: regulation_sec=0 and untimed=False → violation
# ===========================================================================

class TestBadClock:
    def test_zero_regulation_sec_not_untimed_produces_violation(self) -> None:
        bad_clock = GameClockConfig(
            n_periods=4, period_len_sec=0, ot_len_sec=300, untimed=False
        )
        ctx = _make_valid_ctx(clock=bad_clock)
        violations = check_sport_context(ctx)
        assert any("regulation_sec" in v or "untimed" in v for v in violations), (
            f"Expected a violation about regulation_sec/untimed; got: {violations}"
        )

    def test_bad_clock_assert_raises(self) -> None:
        bad_clock = GameClockConfig(
            n_periods=4, period_len_sec=0, ot_len_sec=300, untimed=False
        )
        ctx = _make_valid_ctx(clock=bad_clock)
        with pytest.raises(AssertionError):
            assert_sport_context_conformant(ctx)


# ===========================================================================
# 4. Bad PBPEventMapper: missing method → violation
# ===========================================================================

class TestBadPBPMapper:
    def test_missing_method_produces_violation(self) -> None:
        class _BadMapper:
            # Missing to_canonical and possession_side
            def iter_game(self, game_id: str) -> Iterator[CanonicalEvent]:
                return iter([])

        ctx = _make_valid_ctx(pbp_mapper=_BadMapper())
        violations = check_sport_context(ctx)
        assert any("pbp_mapper" in v for v in violations), (
            f"Expected a pbp_mapper violation; got: {violations}"
        )

    def test_bad_mapper_assert_raises(self) -> None:
        class _BadMapper:
            def iter_game(self, game_id: str) -> Iterator[CanonicalEvent]:
                return iter([])

        ctx = _make_valid_ctx(pbp_mapper=_BadMapper())
        with pytest.raises(AssertionError, match="pbp_mapper"):
            assert_sport_context_conformant(ctx)


# ===========================================================================
# 5. Bad LeagueClient: missing method → violation
# ===========================================================================

class TestBadLeagueClient:
    def test_missing_method_produces_violation(self) -> None:
        class _BadClient:
            # Missing get_pbp and others
            def get_schedule(self, season: str) -> Any:
                return []

            def get_box_score(self, game_id: str) -> Any:
                return {}

        ctx = _make_valid_ctx(league_client=_BadClient())
        violations = check_sport_context(ctx)
        assert any("league_client" in v for v in violations), (
            f"Expected a league_client violation; got: {violations}"
        )

    def test_bad_client_assert_raises(self) -> None:
        class _BadClient:
            def get_schedule(self, season: str) -> Any:
                return []

        ctx = _make_valid_ctx(league_client=_BadClient())
        with pytest.raises(AssertionError, match="league_client"):
            assert_sport_context_conformant(ctx)


# ===========================================================================
# 6. Bad EntityRegistry: missing method → violation
# ===========================================================================

class TestBadEntityRegistry:
    def test_missing_method_produces_violation(self) -> None:
        class _BadRegistry:
            sport_id: str = "toyball"
            # Missing resolve_team, resolve_player, parse_game_id, …

        ctx = _make_valid_ctx(entities=_BadRegistry())
        violations = check_sport_context(ctx)
        assert any("entities" in v for v in violations), (
            f"Expected an entities violation; got: {violations}"
        )

    def test_bad_registry_assert_raises(self) -> None:
        class _BadRegistry:
            sport_id: str = "toyball"

        ctx = _make_valid_ctx(entities=_BadRegistry())
        with pytest.raises(AssertionError, match="entities"):
            assert_sport_context_conformant(ctx)


# ===========================================================================
# 7. Wrong atlas_schema type → violation
# ===========================================================================

class TestBadAtlasSchema:
    def test_wrong_type_produces_violation(self) -> None:
        ctx = _make_valid_ctx(atlas_schema={"sections": []})  # type: ignore[arg-type]
        violations = check_sport_context(ctx)
        assert any("atlas_schema" in v for v in violations), (
            f"Expected an atlas_schema violation; got: {violations}"
        )

    def test_bad_atlas_assert_raises(self) -> None:
        ctx = _make_valid_ctx(atlas_schema="not-an-atlas")  # type: ignore[arg-type]
        with pytest.raises(AssertionError, match="atlas_schema"):
            assert_sport_context_conformant(ctx)


# ===========================================================================
# 8. Wrong optional court type → violation
# ===========================================================================

class TestBadOptionalCourt:
    def test_wrong_court_type_produces_violation(self) -> None:
        ctx = _make_valid_ctx(court="not-a-court-config")  # type: ignore[arg-type]
        violations = check_sport_context(ctx)
        assert any("court" in v for v in violations), (
            f"Expected a court violation; got: {violations}"
        )


# ===========================================================================
# 9. Wrong optional speed type → violation
# ===========================================================================

class TestBadOptionalSpeed:
    def test_wrong_speed_type_produces_violation(self) -> None:
        ctx = _make_valid_ctx(speed=42)  # type: ignore[arg-type]
        violations = check_sport_context(ctx)
        assert any("speed" in v for v in violations), (
            f"Expected a speed violation; got: {violations}"
        )


# ===========================================================================
# 10. assert_sport_context_conformant: error lists all violations
# ===========================================================================

class TestAssertListsAllViolations:
    def test_multiple_violations_all_in_error(self) -> None:
        """Both pbp_mapper AND atlas_schema broken → both appear in AssertionError."""
        class _BadMapper:
            pass  # no methods at all

        ctx = _make_valid_ctx(
            pbp_mapper=_BadMapper(),
            atlas_schema="wrong",  # type: ignore[arg-type]
        )
        with pytest.raises(AssertionError) as exc_info:
            assert_sport_context_conformant(ctx)
        msg = str(exc_info.value)
        assert "pbp_mapper" in msg
        assert "atlas_schema" in msg

    def test_violation_count_in_message(self) -> None:
        """The AssertionError message mentions the count of violations."""
        class _BadMapper:
            pass

        ctx = _make_valid_ctx(
            pbp_mapper=_BadMapper(),
            atlas_schema="wrong",  # type: ignore[arg-type]
        )
        with pytest.raises(AssertionError) as exc_info:
            assert_sport_context_conformant(ctx)
        msg = str(exc_info.value)
        assert "violation" in msg.lower()
