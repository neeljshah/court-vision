"""Conformance tests for NBAEntityRegistry (P0-D-014).

Verifies that ``NBAEntityRegistry`` satisfies the kernel ``EntityRegistry``
protocol and behaves correctly on real NBA data.

Offline (no network).  Run scoped:
    pytest tests/conformance/nba/test_nba_entity_registry.py -q --timeout=120

Covers
------
1. isinstance(NBAEntityRegistry(), EntityRegistry) is True (structural).
2. 30 NBA tricodes resolve via round-trip (tricode → resolve_team → same tricode).
3. Spot-check ~10 common aliases ("warriors" → "GSW", "lakers" → "LAL", etc.).
4. parse_game_id("0042500404") → season "2025-26", kind "playoff", seq present.
5. parse_game_id round-trips on multiple sample IDs.
6. Unknown team token raises KeyError.
7. Unknown player token raises KeyError.
8. parse_game_id on malformed ID raises ValueError.
9. sport_id is "basketball_nba".
10. Helper methods (season_of, entity_key, book_aliases) satisfy the protocol shape.
"""
from __future__ import annotations

import datetime
from typing import Any

import pytest

from kernel.config.entities import EntityRegistry
from domains.basketball_nba.entity_registry import NBAEntityRegistry


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def reg() -> NBAEntityRegistry:
    """NBAEntityRegistry instance, constructed once for the module."""
    return NBAEntityRegistry()


# ---------------------------------------------------------------------------
# 1. Protocol conformance via isinstance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """NBAEntityRegistry must satisfy the EntityRegistry structural protocol."""

    def test_isinstance_entity_registry(self, reg: NBAEntityRegistry) -> None:
        """isinstance check must pass — all required methods are present."""
        assert isinstance(reg, EntityRegistry), (
            "NBAEntityRegistry does not satisfy the EntityRegistry protocol. "
            "Ensure all required methods (resolve_team, resolve_player, "
            "parse_game_id, season_of, entity_key, book_aliases) are present."
        )

    def test_sport_id_is_basketball_nba(self, reg: NBAEntityRegistry) -> None:
        """sport_id must be the canonical 'basketball_nba' identifier."""
        assert reg.sport_id == "basketball_nba"


# ---------------------------------------------------------------------------
# 2. Tricode round-trips for all 30 NBA teams
# ---------------------------------------------------------------------------

_ALL_30_TRICODES = [
    "ATL", "BOS", "BKN", "CHA", "CHI",
    "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM",
    "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR",
    "SAC", "SAS", "TOR", "UTA", "WAS",
]


class TestTricodeRoundTrips:
    """All 30 official NBA tricodes must resolve to themselves."""

    @pytest.mark.parametrize("tricode", _ALL_30_TRICODES)
    def test_tricode_resolves_to_itself(
        self, reg: NBAEntityRegistry, tricode: str
    ) -> None:
        """resolve_team(tricode) must return the same tricode (case-insensitive input)."""
        result = reg.resolve_team(tricode.lower())
        assert result == tricode, (
            f"Expected resolve_team({tricode.lower()!r}) == {tricode!r}, got {result!r}."
        )


# ---------------------------------------------------------------------------
# 3. Alias spot-checks
# ---------------------------------------------------------------------------

_ALIAS_SPOT_CHECKS = [
    # nickname aliases
    ("warriors",     "GSW"),
    ("lakers",       "LAL"),
    ("celtics",      "BOS"),
    ("spurs",        "SAS"),
    ("knicks",       "NYK"),
    ("heat",         "MIA"),
    ("nets",         "BKN"),
    ("bulls",        "CHI"),
    ("nuggets",      "DEN"),
    ("suns",         "PHX"),
    # city aliases
    ("brooklyn",     "BKN"),
    ("houston",      "HOU"),
    ("portland",     "POR"),
    ("orlando",      "ORL"),
    ("detroit",      "DET"),
    ("charlotte",    "CHA"),
    # full display name (from _TEAM_ALIASES)
    ("golden state warriors", "GSW"),
    ("los angeles lakers",    "LAL"),
    ("new york knicks",       "NYK"),
    ("boston celtics",        "BOS"),
    ("san antonio spurs",     "SAS"),
    ("miami heat",            "MIA"),
    # caps/mixed-case normalisation
    ("WARRIORS",  "GSW"),
    ("Lakers",    "LAL"),
]


class TestAliasSpotChecks:
    """Common aliases (nicknames, cities, full names) resolve correctly."""

    @pytest.mark.parametrize("token,expected", _ALIAS_SPOT_CHECKS)
    def test_alias_resolves(
        self, reg: NBAEntityRegistry, token: str, expected: str
    ) -> None:
        result = reg.resolve_team(token)
        assert result == expected, (
            f"resolve_team({token!r}) → {result!r}, expected {expected!r}."
        )


# ---------------------------------------------------------------------------
# 4 & 5. parse_game_id
# ---------------------------------------------------------------------------

class TestParseGameId:
    """parse_game_id returns correct season, kind, and seq."""

    def test_finals_game_2025_26_playoff(self, reg: NBAEntityRegistry) -> None:
        """Canonical test case: '0042500404' → 2025-26 playoff."""
        result = reg.parse_game_id("0042500404")
        assert result["season"] == "2025-26", (
            f"Expected season '2025-26', got {result['season']!r}."
        )
        assert result["kind"] == "playoff", (
            f"Expected kind 'playoff', got {result['kind']!r}."
        )
        assert "seq" in result
        assert isinstance(result["seq"], int)

    def test_returns_three_required_keys(self, reg: NBAEntityRegistry) -> None:
        """Result must contain 'season', 'kind', 'seq'."""
        result = reg.parse_game_id("0042500404")
        assert set(result.keys()) >= {"season", "kind", "seq"}

    # Round-trip samples
    @pytest.mark.parametrize("game_id,expected_season,expected_kind", [
        ("0022400001", "2024-25", "regular"),   # 2024-25 regular season
        ("0042400401", "2024-25", "playoff"),   # 2024-25 playoff
        ("0022300100", "2023-24", "regular"),   # 2023-24 regular season
        ("0042300404", "2023-24", "playoff"),   # 2023-24 playoff
        ("0042500404", "2025-26", "playoff"),   # 2025-26 playoff (Finals G4)
        ("0022500001", "2025-26", "regular"),   # 2025-26 regular season
    ])
    def test_round_trip_sample_ids(
        self,
        reg: NBAEntityRegistry,
        game_id: str,
        expected_season: str,
        expected_kind: str,
    ) -> None:
        result = reg.parse_game_id(game_id)
        assert result["season"] == expected_season, (
            f"{game_id}: expected season {expected_season!r}, got {result['season']!r}."
        )
        assert result["kind"] == expected_kind, (
            f"{game_id}: expected kind {expected_kind!r}, got {result['kind']!r}."
        )
        assert isinstance(result["seq"], int)

    def test_seq_is_nonzero_for_real_game(self, reg: NBAEntityRegistry) -> None:
        """seq for a real game should be a positive integer."""
        result = reg.parse_game_id("0042500404")
        assert result["seq"] > 0

    def test_raises_on_malformed_id(self, reg: NBAEntityRegistry) -> None:
        """parse_game_id must raise ValueError on garbage input."""
        with pytest.raises((ValueError, KeyError)):
            reg.parse_game_id("not_a_game_id")

    def test_raises_on_empty_string(self, reg: NBAEntityRegistry) -> None:
        with pytest.raises((ValueError, KeyError)):
            reg.parse_game_id("")

    def test_raises_on_short_id(self, reg: NBAEntityRegistry) -> None:
        with pytest.raises((ValueError, KeyError)):
            reg.parse_game_id("12345")

    def test_raises_on_wrong_prefix(self, reg: NBAEntityRegistry) -> None:
        """IDs not starting with '00' must raise."""
        with pytest.raises((ValueError, KeyError)):
            reg.parse_game_id("9942500404")


# ---------------------------------------------------------------------------
# 6 & 7. Unknown-Token Contract
# ---------------------------------------------------------------------------


class TestUnknownTokenContract:
    """resolve_team and resolve_player MUST raise on unrecognised tokens."""

    def test_unknown_team_raises(self, reg: NBAEntityRegistry) -> None:
        with pytest.raises((KeyError, ValueError)):
            reg.resolve_team("not_a_team")

    def test_unknown_team_empty_string_raises(self, reg: NBAEntityRegistry) -> None:
        with pytest.raises((KeyError, ValueError)):
            reg.resolve_team("")

    def test_unknown_team_gibberish_raises(self, reg: NBAEntityRegistry) -> None:
        with pytest.raises((KeyError, ValueError)):
            reg.resolve_team("XXXXXXXX_FAKE_FRANCHISE")

    def test_unknown_player_nonnumeric_raises(self, reg: NBAEntityRegistry) -> None:
        """Non-numeric player tokens raise KeyError."""
        with pytest.raises((KeyError, ValueError)):
            reg.resolve_player("Ghost Player Who Does Not Exist")

    def test_unknown_player_empty_raises(self, reg: NBAEntityRegistry) -> None:
        with pytest.raises((KeyError, ValueError)):
            reg.resolve_player("")

    def test_known_numeric_player_id_succeeds(self, reg: NBAEntityRegistry) -> None:
        """Numeric NBA player IDs must not raise."""
        result = reg.resolve_player("1628384")   # Jalen Brunson
        assert isinstance(result, str)
        assert result  # non-empty

    def test_numeric_int_player_id_succeeds(self, reg: NBAEntityRegistry) -> None:
        """Integer player IDs must also succeed."""
        result = reg.resolve_player(1628384)
        assert isinstance(result, str)
        assert result.isdigit()


# ---------------------------------------------------------------------------
# 8. Helper methods
# ---------------------------------------------------------------------------


class TestHelperMethods:
    """season_of, entity_key, book_aliases must satisfy the protocol shape."""

    def test_season_of_oct_in_season(self, reg: NBAEntityRegistry) -> None:
        """October 2025 → '2025-26' season."""
        result = reg.season_of(datetime.date(2025, 10, 22))
        assert result == "2025-26"

    def test_season_of_jan_in_season(self, reg: NBAEntityRegistry) -> None:
        """January 2026 still belongs to the 2025-26 season."""
        result = reg.season_of(datetime.date(2026, 1, 15))
        assert result == "2025-26"

    def test_season_of_sep_in_prev_season(self, reg: NBAEntityRegistry) -> None:
        """September 2025 belongs to the 2024-25 season."""
        result = reg.season_of(datetime.date(2025, 9, 1))
        assert result == "2024-25"

    def test_season_of_returns_string(self, reg: NBAEntityRegistry) -> None:
        result = reg.season_of(datetime.date(2024, 12, 1))
        assert isinstance(result, str)
        assert result  # non-empty

    def test_entity_key_format_team(self, reg: NBAEntityRegistry) -> None:
        assert reg.entity_key("team", "NYK") == "team:NYK"

    def test_entity_key_format_player(self, reg: NBAEntityRegistry) -> None:
        assert reg.entity_key("player", "1628384") == "player:1628384"

    def test_entity_key_returns_nonempty_string(self, reg: NBAEntityRegistry) -> None:
        key = reg.entity_key("game", "0042500404")
        assert isinstance(key, str)
        assert key

    def test_book_aliases_returns_mapping(self, reg: NBAEntityRegistry) -> None:
        aliases = reg.book_aliases()
        assert hasattr(aliases, "__getitem__"), "book_aliases must return a Mapping"
        for k, v in aliases.items():
            assert isinstance(k, str), f"key {k!r} not str"
            assert isinstance(v, str), f"value {v!r} not str"

    def test_book_aliases_fanduel_entry(self, reg: NBAEntityRegistry) -> None:
        aliases = reg.book_aliases()
        assert "fanduel" in aliases.values()

    def test_book_aliases_draftkings_entry(self, reg: NBAEntityRegistry) -> None:
        aliases = reg.book_aliases()
        assert "draftkings" in aliases.values()

    def test_book_aliases_nonempty(self, reg: NBAEntityRegistry) -> None:
        assert len(reg.book_aliases()) > 0
