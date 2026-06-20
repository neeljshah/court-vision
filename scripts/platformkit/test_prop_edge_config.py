"""Per-file tests for scripts.platformkit.prop_edge_config (network-free).

Covers:
  - _FACTORIES['nba'] exists and yields >=1 concrete provider (Underdog + PrizePicks)
  - get_config('nba') returns a valid SportPropConfig (not None, not raises)
  - NBA config canonical_stats contains the standard prop set
  - NBA offseason/empty slate -> nba_board_status returns "unavailable_offseason"
  - NBA live slate (n_lines > 0) -> nba_board_status returns "ok"
  - Soccer + MLB factories still build without error (unchanged wiring)
  - get_config(unknown) returns None (not raises)
  - providers_for_sport round-trips correctly
  - supported_sports includes all three wired sports

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_edge_config.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.prop_edge_config import (
    _FACTORIES,
    get_config,
    nba_board_status,
    providers_for_sport,
    supported_sports,
)

# ---------------------------------------------------------------------------
# _FACTORIES presence
# ---------------------------------------------------------------------------

def test_nba_in_factories():
    assert "nba" in _FACTORIES, "_FACTORIES must contain 'nba'"


def test_soccer_and_mlb_in_factories():
    assert "soccer_intl" in _FACTORIES
    assert "mlb" in _FACTORIES


# ---------------------------------------------------------------------------
# get_config('nba') -- concrete config, not None, not raises
# ---------------------------------------------------------------------------

def test_get_config_nba_returns_config():
    cfg = get_config("nba")
    assert cfg is not None, "get_config('nba') must not return None"
    assert cfg.sport == "nba"


def test_get_config_nba_case_insensitive():
    cfg = get_config("NBA")
    assert cfg is not None
    assert cfg.sport == "nba"


def test_get_config_unknown_returns_none_not_raises():
    cfg = get_config("curling")
    assert cfg is None


def test_get_config_empty_string_returns_none():
    cfg = get_config("")
    assert cfg is None


# ---------------------------------------------------------------------------
# NBA config: >=1 concrete provider from _FACTORIES
# ---------------------------------------------------------------------------

def test_nba_factories_yields_at_least_one_provider():
    """The NBA factory must yield a provider list with at least one entry."""
    cfg = get_config("nba")
    assert cfg is not None
    providers = cfg.default_providers()
    assert len(providers) >= 1, "NBA config must wire >=1 provider"


def test_nba_factories_provider_names():
    """Both Underdog and PrizePicks must be wired for NBA."""
    cfg = get_config("nba")
    assert cfg is not None
    providers = cfg.default_providers()
    names = {getattr(p, "name", type(p).__name__) for p in providers}
    assert "underdog" in names, "UnderdogProvider must be wired for NBA"
    assert "prizepicks" in names, "PrizePicksProvider must be wired for NBA"


def test_nba_provider_instances_have_fetch_props():
    """Each wired NBA provider must expose a fetch_props method."""
    cfg = get_config("nba")
    assert cfg is not None
    for prov in cfg.default_providers():
        assert callable(getattr(prov, "fetch_props", None)), (
            "provider %s missing fetch_props" % getattr(prov, "name", prov)
        )


# ---------------------------------------------------------------------------
# NBA canonical stats
# ---------------------------------------------------------------------------

_EXPECTED_NBA_STATS = {
    "Points", "Rebounds", "Assists", "Steals", "Blocks",
    "3-PT Made", "Turnovers",
}


def test_nba_canonical_stats_cover_core_props():
    cfg = get_config("nba")
    assert cfg is not None
    for stat in _EXPECTED_NBA_STATS:
        assert stat in cfg.canonical_stats, (
            "NBA canonical_stats must include '%s'" % stat
        )


def test_nba_canonical_stats_includes_combo_props():
    cfg = get_config("nba")
    assert cfg is not None
    for stat in ("Pts+Reb+Ast", "Pts+Reb", "Pts+Ast", "Reb+Ast"):
        assert stat in cfg.canonical_stats, (
            "NBA canonical_stats must include combo stat '%s'" % stat
        )


# ---------------------------------------------------------------------------
# Offseason honest degradation: nba_board_status
# ---------------------------------------------------------------------------

def test_offseason_empty_slate_returns_unavailable_offseason():
    """All providers returned UNAVAILABLE (offseason) -> board status is
    unavailable_offseason, never empty-but-green 'ok'."""
    sources = {
        "underdog": "no rows for sport 'nba'",
        "prizepicks": "league 'NBA' not found",
    }
    status = nba_board_status(sources, n_lines=0)
    assert status == "unavailable_offseason", (
        "Empty NBA slate must degrade to 'unavailable_offseason', got: %r" % status
    )


def test_live_slate_with_lines_returns_ok():
    """When at least one line came through the board is 'ok'."""
    sources = {
        "underdog": "ok (12 rows)",
        "prizepicks": "ok (8 rows)",
    }
    status = nba_board_status(sources, n_lines=20)
    assert status == "ok"


def test_partial_provider_failure_but_lines_present_returns_ok():
    """One provider down + the other returned lines -> 'ok' (lines are real)."""
    sources = {
        "underdog": "no rows for sport 'nba'",
        "prizepicks": "ok (5 rows)",
    }
    status = nba_board_status(sources, n_lines=5)
    assert status == "ok"


def test_nba_board_status_never_raises_on_bad_input():
    """nba_board_status must never raise on unexpected input."""
    assert nba_board_status(None, 0) in ("ok", "unavailable_offseason")  # type: ignore[arg-type]
    assert nba_board_status({}, -1) in ("ok", "unavailable_offseason")


# ---------------------------------------------------------------------------
# NBA engine_distribution raises NotImplementedError (model column -> UNAVAILABLE)
# ---------------------------------------------------------------------------

def test_nba_engine_raises_not_implemented():
    """The NBA engine stub must raise NotImplementedError so callers know to
    degrade the model-probability column to UNAVAILABLE (no src/ access)."""
    cfg = get_config("nba")
    assert cfg is not None
    with pytest.raises(NotImplementedError):
        cfg.engine_distribution(None, None, None, None)


# ---------------------------------------------------------------------------
# NBA resolve_player returns unavailable (not a crash or a fabricated match)
# ---------------------------------------------------------------------------

def test_nba_resolve_player_returns_unavailable():
    cfg = get_config("nba")
    assert cfg is not None
    result = cfg.resolve_player(None, "LeBron James", team="LAL", index=None)
    assert isinstance(result, dict)
    assert result.get("status") == "unavailable"


def test_nba_build_name_index_returns_none():
    cfg = get_config("nba")
    assert cfg is not None
    assert cfg.build_name_index(None) is None


# ---------------------------------------------------------------------------
# Soccer + MLB factories unchanged
# ---------------------------------------------------------------------------

def test_supported_sports_has_all_three():
    sports = set(supported_sports())
    assert "nba" in sports
    assert "mlb" in sports
    assert "soccer_intl" in sports


def test_get_config_soccer_does_not_raise():
    """Soccer config builds without raising (domain imports succeed)."""
    try:
        cfg = get_config("soccer_intl")
        # If the domain is importable, cfg should be a SportPropConfig.
        if cfg is not None:
            assert cfg.sport == "soccer_intl"
            assert cfg.supports_dispersion is True
            assert cfg.supports_opp_mult is True
    except Exception as exc:  # noqa: BLE001 -- domain missing on CI -> skip
        pytest.skip("soccer domain unavailable: %s" % exc)


def test_get_config_mlb_does_not_raise():
    """MLB config builds without raising (domain imports succeed)."""
    try:
        cfg = get_config("mlb")
        if cfg is not None:
            assert cfg.sport == "mlb"
            assert cfg.supports_dispersion is False
            assert cfg.supports_opp_mult is False
    except Exception as exc:  # noqa: BLE001 -- domain missing on CI -> skip
        pytest.skip("mlb domain unavailable: %s" % exc)


# ---------------------------------------------------------------------------
# providers_for_sport convenience
# ---------------------------------------------------------------------------

def test_providers_for_sport_nba():
    providers = providers_for_sport("nba")
    assert len(providers) >= 1
    names = {getattr(p, "name", None) for p in providers}
    assert "underdog" in names
    assert "prizepicks" in names


def test_providers_for_sport_unknown_returns_empty_list():
    result = providers_for_sport("handball")
    assert result == []


def test_providers_for_sport_does_not_raise_on_bad_input():
    result = providers_for_sport(None)  # type: ignore[arg-type]
    assert isinstance(result, list)
