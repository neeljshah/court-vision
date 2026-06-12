"""tests.kernel.test_fixtures — Conformance tests for toy SportContext factories.

Verifies that both factories in ``kernel.testing.fixtures`` produce contexts
that pass ``check_sport_context`` with zero violations, and that protocol
isinstance checks pass for all three adapter protocols.

Hermetic and offline — no network, no domains import, no heavy dependencies.
"""
from __future__ import annotations

import pytest

from kernel.config.context import SportContext
from kernel.config.entities import EntityRegistry
from kernel.config.pbp import LeagueClient, PBPEventMapper
from kernel.testing.conformance import check_sport_context
from kernel.testing.fixtures import make_toyball_context, make_toyball_untimed_context


# ---------------------------------------------------------------------------
# Timed toyball context
# ---------------------------------------------------------------------------


class TestMakeToyballContext:
    """Tests for the timed toyball SportContext factory."""

    def test_returns_sport_context(self) -> None:
        """Factory must return a SportContext instance."""
        ctx = make_toyball_context()
        assert isinstance(ctx, SportContext)

    def test_sport_id(self) -> None:
        """sport_id must be 'toyball'."""
        ctx = make_toyball_context()
        assert ctx.sport_id == "toyball"

    def test_conformant_zero_violations(self) -> None:
        """check_sport_context must return an empty violations list."""
        ctx = make_toyball_context()
        violations = check_sport_context(ctx)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_clock_is_timed(self) -> None:
        """Timed context must have clock.untimed == False."""
        ctx = make_toyball_context()
        assert ctx.clock.untimed is False

    def test_clock_regulation_sec_positive(self) -> None:
        """Timed context must have regulation_sec() > 0."""
        ctx = make_toyball_context()
        assert ctx.clock.regulation_sec() > 0

    def test_entities_isinstance(self) -> None:
        """ctx.entities must satisfy EntityRegistry protocol."""
        ctx = make_toyball_context()
        assert isinstance(ctx.entities, EntityRegistry)

    def test_pbp_mapper_isinstance(self) -> None:
        """ctx.pbp_mapper must satisfy PBPEventMapper protocol."""
        ctx = make_toyball_context()
        assert isinstance(ctx.pbp_mapper, PBPEventMapper)

    def test_league_client_isinstance(self) -> None:
        """ctx.league_client must satisfy LeagueClient protocol."""
        ctx = make_toyball_context()
        assert isinstance(ctx.league_client, LeagueClient)

    def test_stats_has_two_targets(self) -> None:
        """Stats registry must have exactly 2 stat targets."""
        ctx = make_toyball_context()
        assert len(ctx.stats.target_names()) == 2

    def test_roster_on_field_count(self) -> None:
        """on_field_count must be 5."""
        ctx = make_toyball_context()
        assert ctx.roster.on_field_count == 5


# ---------------------------------------------------------------------------
# Untimed toyball context
# ---------------------------------------------------------------------------


class TestMakeToyballUntimedContext:
    """Tests for the untimed toyball SportContext factory."""

    def test_returns_sport_context(self) -> None:
        """Factory must return a SportContext instance."""
        ctx = make_toyball_untimed_context()
        assert isinstance(ctx, SportContext)

    def test_sport_id(self) -> None:
        """sport_id must be 'toyball_untimed'."""
        ctx = make_toyball_untimed_context()
        assert ctx.sport_id == "toyball_untimed"

    def test_conformant_zero_violations(self) -> None:
        """check_sport_context must return an empty violations list."""
        ctx = make_toyball_untimed_context()
        violations = check_sport_context(ctx)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_clock_untimed_true(self) -> None:
        """Untimed context must have clock.untimed == True."""
        ctx = make_toyball_untimed_context()
        assert ctx.clock.untimed is True

    def test_clock_regulation_sec_zero(self) -> None:
        """Untimed context must have regulation_sec() == 0."""
        ctx = make_toyball_untimed_context()
        assert ctx.clock.regulation_sec() == 0

    def test_entities_isinstance(self) -> None:
        """ctx.entities must satisfy EntityRegistry protocol."""
        ctx = make_toyball_untimed_context()
        assert isinstance(ctx.entities, EntityRegistry)

    def test_pbp_mapper_isinstance(self) -> None:
        """ctx.pbp_mapper must satisfy PBPEventMapper protocol."""
        ctx = make_toyball_untimed_context()
        assert isinstance(ctx.pbp_mapper, PBPEventMapper)

    def test_league_client_isinstance(self) -> None:
        """ctx.league_client must satisfy LeagueClient protocol."""
        ctx = make_toyball_untimed_context()
        assert isinstance(ctx.league_client, LeagueClient)

    def test_stats_has_two_targets(self) -> None:
        """Stats registry must have exactly 2 stat targets."""
        ctx = make_toyball_untimed_context()
        assert len(ctx.stats.target_names()) == 2

    def test_roster_on_field_count(self) -> None:
        """on_field_count must be 5."""
        ctx = make_toyball_untimed_context()
        assert ctx.roster.on_field_count == 5


# ---------------------------------------------------------------------------
# Cross-context isolation
# ---------------------------------------------------------------------------


class TestContextIsolation:
    """Verify that the two factory calls return independent objects."""

    def test_independent_instances(self) -> None:
        """The two factories must return different SportContext objects."""
        ctx_timed = make_toyball_context()
        ctx_untimed = make_toyball_untimed_context()
        assert ctx_timed is not ctx_untimed

    def test_different_sport_ids(self) -> None:
        """The two contexts must have distinct sport_ids."""
        ctx_timed = make_toyball_context()
        ctx_untimed = make_toyball_untimed_context()
        assert ctx_timed.sport_id != ctx_untimed.sport_id

    def test_repeated_calls_same_sport_id(self) -> None:
        """Repeated calls to the same factory must return consistent sport_ids."""
        assert make_toyball_context().sport_id == make_toyball_context().sport_id
        assert (
            make_toyball_untimed_context().sport_id
            == make_toyball_untimed_context().sport_id
        )
