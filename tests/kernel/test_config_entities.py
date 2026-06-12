"""Tests for kernel.config.entities — EntityRegistry Protocol.

Hermetic, offline.  No heavy imports (stdlib + typing only).

Covers
------
1. ``isinstance(toy, EntityRegistry)`` passes for a class that
   structurally implements all required method signatures
   (runtime_checkable structural check).
2. A class missing a required method does NOT pass isinstance.
3. ``parse_game_id`` on the toy returns a dict containing the three
   required keys: ``"season"``, ``"kind"``, ``"seq"``.
4. ``parse_game_id`` raises on an unrecognised game ID (unknown-token
   contract — documented and tested here to bind all adapter authors).
5. ``resolve_team`` and ``resolve_player`` raise on unknown tokens
   (unknown-token contract).
6. ``book_aliases`` returns a Mapping[str, str].
7. ``entity_key`` returns a non-empty string.
8. ``season_of`` returns a non-empty string.

Unknown-Token Contract (binding for all EntityRegistry implementations)
-----------------------------------------------------------------------
The protocol docstring states: implementations MUST raise on unrecognised
tokens — they must never guess or silently return a wrong id.  Tests 4, 5
below exercise this contract against the toy registry.  Every domain
adapter must pass an equivalent suite in ``kernel/testing/``.
"""
from __future__ import annotations

import datetime
from typing import Any, Mapping

import pytest

from kernel.config.entities import EntityRegistry


# ---------------------------------------------------------------------------
# Toy registry — a minimal concrete class that satisfies the protocol
# ---------------------------------------------------------------------------

class _ToyRegistry:
    """Minimal in-memory registry used only for protocol conformance tests.

    Implements the EntityRegistry structural interface without subclassing it.
    All real resolution logic is trivial; the important invariants are:
      - unknown tokens raise (see Unknown-Token Contract above).
      - parse_game_id returns a dict with "season", "kind", "seq".
    """

    sport_id: str = "toy"

    _TEAMS: dict[str, str] = {
        "HOME": "HOME",
        "AWAY": "AWAY",
    }

    _PLAYERS: dict[str, str] = {
        "Alice": "p001",
        "Bob":   "p002",
    }

    def resolve_team(self, token: str) -> str:
        """Resolve a team alias.  Raises KeyError on unknown tokens.

        Unknown-Token Contract: NEVER guess or return a wrong id.
        """
        if token not in self._TEAMS:
            raise KeyError(
                f"[ToyRegistry] Unknown team token: {token!r}. "
                "Implementations must raise — never guess."
            )
        return self._TEAMS[token]

    def resolve_player(self, token: Any) -> str:
        """Resolve a player name.  Raises KeyError on unknown tokens.

        Unknown-Token Contract: NEVER guess or return a wrong id.
        """
        if token not in self._PLAYERS:
            raise KeyError(
                f"[ToyRegistry] Unknown player token: {token!r}. "
                "Implementations must raise — never guess."
            )
        return self._PLAYERS[token]

    def parse_game_id(self, game_id: str) -> dict[str, Any]:
        """Decode a toy game ID.

        Expected format: ``"TOY-<season>-<kind>-<seq>"``,
        e.g. ``"TOY-2024-25-regular-1"``.

        Returns a dict with keys ``"season"``, ``"kind"``, ``"seq"``.

        Raises ValueError on malformed or unrecognised game IDs.

        Unknown-Token Contract: malformed IDs MUST raise — never guess.
        """
        parts = game_id.split("-", maxsplit=3)
        # Expected: ["TOY", "<yr1>", "<yr2>", "<kind>-<seq>"] or similar
        # We require the prefix "TOY" and at least 4 dash-separated parts.
        if len(parts) < 4 or parts[0] != "TOY":
            raise ValueError(
                f"[ToyRegistry] Unrecognised game_id format: {game_id!r}. "
                "Implementations must raise — never guess."
            )
        # parts[1]-parts[2] form the season, parts[3] = "<kind>-<seq>"
        season = f"{parts[1]}-{parts[2]}"
        tail = parts[3].rsplit("-", maxsplit=1)
        if len(tail) != 2:
            raise ValueError(
                f"[ToyRegistry] Cannot parse kind/seq from: {game_id!r}."
            )
        kind, seq_str = tail
        try:
            seq = int(seq_str)
        except ValueError:
            raise ValueError(
                f"[ToyRegistry] seq must be an integer, got {seq_str!r}."
            )
        return {"season": season, "kind": kind, "seq": seq}

    def season_of(self, d: Any) -> str:
        """Return the season label for a date (toy: year-year+1 format)."""
        if isinstance(d, (datetime.date, datetime.datetime)):
            yr = d.year
        else:
            yr = int(d)
        return f"{yr}-{str(yr + 1)[2:]}"

    def entity_key(self, kind: str, ident: Any) -> str:
        """Build a PointInTimeStore key string."""
        return f"{kind}:{ident}"

    def book_aliases(self) -> Mapping[str, str]:
        """Return sportsbook name aliases."""
        return {"fd": "fanduel", "dk": "draftkings"}


# ---------------------------------------------------------------------------
# A class that is MISSING one required method — must NOT pass isinstance
# ---------------------------------------------------------------------------

class _IncompleteRegistry:
    """Missing parse_game_id and several others — must fail isinstance."""

    sport_id: str = "incomplete"

    def resolve_team(self, token: str) -> str:  # noqa: D102
        return token

    def resolve_player(self, token: Any) -> str:  # noqa: D102
        return str(token)

    # parse_game_id, season_of, entity_key, book_aliases — all absent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEntityRegistryProtocol:
    """Structural isinstance checks via @runtime_checkable."""

    def test_toy_registry_passes_isinstance(self) -> None:
        """A class implementing all required methods must pass isinstance."""
        toy = _ToyRegistry()
        assert isinstance(toy, EntityRegistry), (
            "Expected _ToyRegistry to satisfy EntityRegistry protocol "
            "(all methods present and sport_id attribute set)."
        )

    def test_incomplete_registry_fails_isinstance(self) -> None:
        """A class missing required methods must NOT pass isinstance.

        Note: @runtime_checkable only checks method/attribute *presence*,
        not signatures.  Removing parse_game_id is sufficient to fail.
        """
        incomplete = _IncompleteRegistry()
        assert not isinstance(incomplete, EntityRegistry), (
            "Expected _IncompleteRegistry to fail EntityRegistry isinstance "
            "check because required methods are absent."
        )


class TestParseGameId:
    """parse_game_id returns the required dict shape."""

    def test_returns_dict_with_three_required_keys(self) -> None:
        """parse_game_id must return a dict with 'season', 'kind', 'seq'."""
        toy = _ToyRegistry()
        result = toy.parse_game_id("TOY-2024-25-regular-1")
        assert isinstance(result, dict)
        assert "season" in result, "Missing key 'season'"
        assert "kind" in result,   "Missing key 'kind'"
        assert "seq" in result,    "Missing key 'seq'"

    def test_season_value(self) -> None:
        toy = _ToyRegistry()
        result = toy.parse_game_id("TOY-2024-25-regular-7")
        assert result["season"] == "2024-25"

    def test_kind_value(self) -> None:
        toy = _ToyRegistry()
        result = toy.parse_game_id("TOY-2024-25-playoff-3")
        assert result["kind"] == "playoff"

    def test_seq_value_is_int(self) -> None:
        toy = _ToyRegistry()
        result = toy.parse_game_id("TOY-2024-25-regular-42")
        assert result["seq"] == 42
        assert isinstance(result["seq"], int)

    # Unknown-Token Contract: malformed IDs must raise
    def test_parse_game_id_raises_on_unknown_format(self) -> None:
        """Unknown-Token Contract: unrecognised game_id MUST raise.

        Implementations must never guess or silently return a wrong result.
        """
        toy = _ToyRegistry()
        with pytest.raises((KeyError, ValueError)):
            toy.parse_game_id("9999999999")  # no "TOY" prefix — invalid

    def test_parse_game_id_raises_on_empty_string(self) -> None:
        """Unknown-Token Contract: empty game_id must raise."""
        toy = _ToyRegistry()
        with pytest.raises((KeyError, ValueError)):
            toy.parse_game_id("")


class TestUnknownTokenContract:
    """Unknown-Token Contract: resolve_team and resolve_player must raise.

    This is a binding behavioural contract for ALL EntityRegistry
    adapters, documented in the protocol docstring.  Every domain adapter
    must pass an equivalent test in kernel/testing/.
    """

    def test_resolve_team_raises_on_unknown(self) -> None:
        """resolve_team must raise on an unrecognised token — never guess."""
        toy = _ToyRegistry()
        with pytest.raises((KeyError, ValueError)):
            toy.resolve_team("TOTALLY_UNKNOWN_TEAM_XYZ")

    def test_resolve_player_raises_on_unknown(self) -> None:
        """resolve_player must raise on an unrecognised token — never guess."""
        toy = _ToyRegistry()
        with pytest.raises((KeyError, ValueError)):
            toy.resolve_player("Ghost Player Who Does Not Exist")

    def test_resolve_team_known_token_succeeds(self) -> None:
        """Sanity: known tokens must not raise."""
        toy = _ToyRegistry()
        result = toy.resolve_team("HOME")
        assert isinstance(result, str)
        assert result  # non-empty

    def test_resolve_player_known_token_succeeds(self) -> None:
        toy = _ToyRegistry()
        result = toy.resolve_player("Alice")
        assert isinstance(result, str)
        assert result


class TestHelperMethods:
    """season_of, entity_key, book_aliases."""

    def test_season_of_returns_string(self) -> None:
        toy = _ToyRegistry()
        result = toy.season_of(datetime.date(2024, 12, 1))
        assert isinstance(result, str)
        assert result  # non-empty

    def test_entity_key_returns_nonempty_string(self) -> None:
        toy = _ToyRegistry()
        key = toy.entity_key("player", "p001")
        assert isinstance(key, str)
        assert key

    def test_entity_key_format(self) -> None:
        toy = _ToyRegistry()
        assert toy.entity_key("team", "HOME") == "team:HOME"

    def test_book_aliases_returns_mapping(self) -> None:
        toy = _ToyRegistry()
        aliases = toy.book_aliases()
        # Must be a Mapping[str, str]
        assert hasattr(aliases, "__getitem__"), "book_aliases must return a Mapping"
        for k, v in aliases.items():
            assert isinstance(k, str), f"alias key {k!r} is not str"
            assert isinstance(v, str), f"alias value {v!r} is not str"

    def test_book_aliases_nonempty(self) -> None:
        toy = _ToyRegistry()
        assert len(toy.book_aliases()) > 0
