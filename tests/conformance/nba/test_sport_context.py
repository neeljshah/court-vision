"""Conformance tests for NBA_SPORT_CONTEXT / SPORT_CONTEXT (P0-D-017).

Verified properties
-------------------
1. Import works with NO network (socket is poisoned at module level).
2. NBA_SPORT_CONTEXT and SPORT_CONTEXT are the same object.
3. register_sport is idempotent — calling it twice never raises.
4. load_sport("basketball_nba") returns NBA_SPORT_CONTEXT (identity or equal).
5. All protocol fields pass isinstance against their kernel protocols.
6. Atlas has exactly 28 player sections and 16 team sections.
7. sport_id property returns "basketball_nba".

Python 3.9 floor.  Offline only.
"""
from __future__ import annotations

import socket
import sys
import importlib
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Poison socket BEFORE any domain/kernel import so that any accidental
# network call during import raises a clear error rather than hanging.
# ---------------------------------------------------------------------------

_original_socket_connect = socket.socket.connect


def _no_network(self: Any, address: Any) -> None:
    raise RuntimeError(
        f"Network call attempted during offline test: connect({address!r}). "
        "All domain imports must be offline-safe."
    )


socket.socket.connect = _no_network  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Imports under the poisoned socket (must be offline-safe)
# ---------------------------------------------------------------------------

from domains.basketball_nba.config import NBA_SPORT_CONTEXT, SPORT_CONTEXT  # noqa: E402

from kernel.config.context import SportContext  # noqa: E402
from kernel.config.entities import EntityRegistry  # noqa: E402
from kernel.config.pbp import LeagueClient, PBPEventMapper  # noqa: E402
from kernel.config.registry import (  # noqa: E402
    load_sport,
    register_sport,
    unregister_sport,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_import_offline_no_network() -> None:
    """Importing the NBA config module must not trigger any network calls.

    The socket poison above ensures any connect() call during import raises
    RuntimeError.  If we reach this assertion, no network call happened.
    """
    assert NBA_SPORT_CONTEXT is not None, "NBA_SPORT_CONTEXT must not be None after import"


def test_sport_context_and_alias_are_same_object() -> None:
    """SPORT_CONTEXT must be the identical object as NBA_SPORT_CONTEXT."""
    assert SPORT_CONTEXT is NBA_SPORT_CONTEXT, (
        "SPORT_CONTEXT must be the same object as NBA_SPORT_CONTEXT "
        "(not just equal — they are the single injected instance)"
    )


def test_sport_context_is_instance_of_sport_context() -> None:
    """NBA_SPORT_CONTEXT must be a SportContext dataclass instance."""
    assert isinstance(NBA_SPORT_CONTEXT, SportContext), (
        f"Expected SportContext, got {type(NBA_SPORT_CONTEXT)!r}"
    )


def test_register_sport_is_idempotent() -> None:
    """Calling register_sport twice must not raise.

    The registry uses setdefault, so repeated registrations are no-ops.
    This test simulates a module re-import scenario.
    """
    # Should already be registered from import; calling again must not error.
    register_sport(NBA_SPORT_CONTEXT)
    register_sport(NBA_SPORT_CONTEXT)  # second call — still no error


def test_load_sport_returns_nba_sport_context() -> None:
    """load_sport("basketball_nba") must return NBA_SPORT_CONTEXT.

    The registry was populated at import time via register_sport; load_sport
    should return the cached module's SPORT_CONTEXT without re-importing.
    """
    loaded = load_sport("basketball_nba")
    assert loaded is NBA_SPORT_CONTEXT, (
        "load_sport('basketball_nba') must return the same NBA_SPORT_CONTEXT "
        "that was registered at import time"
    )


def test_entities_protocol() -> None:
    """ctx.entities must satisfy the EntityRegistry protocol."""
    assert isinstance(NBA_SPORT_CONTEXT.entities, EntityRegistry), (
        f"entities field does not satisfy EntityRegistry protocol; "
        f"got {type(NBA_SPORT_CONTEXT.entities)!r}"
    )


def test_pbp_mapper_protocol() -> None:
    """ctx.pbp_mapper must satisfy the PBPEventMapper protocol."""
    assert isinstance(NBA_SPORT_CONTEXT.pbp_mapper, PBPEventMapper), (
        f"pbp_mapper field does not satisfy PBPEventMapper protocol; "
        f"got {type(NBA_SPORT_CONTEXT.pbp_mapper)!r}"
    )


def test_league_client_protocol() -> None:
    """ctx.league_client must satisfy the LeagueClient protocol."""
    assert isinstance(NBA_SPORT_CONTEXT.league_client, LeagueClient), (
        f"league_client field does not satisfy LeagueClient protocol; "
        f"got {type(NBA_SPORT_CONTEXT.league_client)!r}"
    )


def test_sport_id_property() -> None:
    """ctx.sport_id must return 'basketball_nba'."""
    assert NBA_SPORT_CONTEXT.sport_id == "basketball_nba", (
        f"sport_id expected 'basketball_nba', got {NBA_SPORT_CONTEXT.sport_id!r}"
    )


def test_atlas_player_section_count() -> None:
    """Atlas must have exactly 28 player sections."""
    count = NBA_SPORT_CONTEXT.atlas_schema.player_section_count
    assert count == 28, (
        f"Expected 28 player atlas sections, got {count}. "
        f"Sections: {NBA_SPORT_CONTEXT.atlas_schema.player_sections}"
    )


def test_atlas_team_section_count() -> None:
    """Atlas must have exactly 16 team sections."""
    count = NBA_SPORT_CONTEXT.atlas_schema.team_section_count
    assert count == 16, (
        f"Expected 16 team atlas sections, got {count}. "
        f"Sections: {NBA_SPORT_CONTEXT.atlas_schema.team_sections}"
    )


def test_atlas_sport_id() -> None:
    """Atlas sport_id must match the context sport_id."""
    assert NBA_SPORT_CONTEXT.atlas_schema.sport_id == "basketball_nba"


def test_atlas_dim_to_section_representative() -> None:
    """dim_to_section must contain the representative mappings."""
    schema = NBA_SPORT_CONTEXT.atlas_schema
    assert schema.resolve_section("game_state:clutch") == "clutch_scoring"
    assert schema.resolve_section("shot:zone") == "shot_profile"
    assert schema.resolve_section("__unmapped__") is None


def test_source_tiers_structure() -> None:
    """source_tiers must map source names to integers with cdn_livedata highest."""
    tiers = NBA_SPORT_CONTEXT.source_tiers
    assert "cdn_livedata" in tiers
    assert "stats_api" in tiers
    assert "bbref" in tiers
    assert tiers["cdn_livedata"] > tiers["stats_api"] > tiers["bbref"]


def test_court_and_speed_present() -> None:
    """NBA context must supply CourtConfig and SpeedConfig (not None)."""
    assert NBA_SPORT_CONTEXT.has_court(), "court must not be None for NBA"
    assert NBA_SPORT_CONTEXT.has_speed(), "speed must not be None for NBA"


def test_artifact_dir_contains_sport_id() -> None:
    """artifact_dir must include 'basketball_nba' as a path component."""
    art_dir = NBA_SPORT_CONTEXT.artifact_dir
    assert "basketball_nba" in str(art_dir), (
        f"artifact_dir {art_dir!r} must contain 'basketball_nba'"
    )
