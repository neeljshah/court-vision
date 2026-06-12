"""kernel.config.entities — EntityRegistry Protocol.

Replaces the NBA-specific entity-resolution logic scattered across
30+ modules (AUDIT gap #9) with a sport-agnostic structural protocol.

The kernel treats all team tokens, player tokens, and game IDs as
**opaque strings** resolved exclusively through an `EntityRegistry`
implementation supplied by the domain adapter.  The kernel itself
never embeds NBA tricodes, player IDs, or game-ID prefix rules.

Unknown-Token Contract
----------------------
Any implementation of `EntityRegistry` MUST raise on unrecognised
input tokens — it must **never silently return a wrong id, guess,
or fall back to a default**.  This is a binding behavioural contract
for all adapters, not merely a recommendation.

  - ``resolve_team("UNKNOWN")``  → raises (e.g. ``KeyError``,
    ``ValueError``, or a domain-specific exception).
  - ``resolve_player("Ghost Player")`` → raises.
  - ``parse_game_id("9999999999")`` → raises if the ID does not
    match the domain's game-ID grammar.

Rationale: silent wrong-ID propagation is the most dangerous failure
mode in a system that stakes decisions on entity identity.  A loud
error surfaces misconfigured adapters immediately; a silent wrong id
would corrupt signal attribution, walk-forward folds, and CLV records
before anyone noticed.

Zero heavy imports: stdlib + typing only.  Python 3.9 floor.
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# EntityRegistry
# ---------------------------------------------------------------------------


@runtime_checkable
class EntityRegistry(Protocol):
    """Sport-agnostic entity-resolution protocol.

    Kernel modules that need to look up teams, players, or decode a
    game ID depend *only* on this interface.  Domain adapters provide a
    concrete implementation (e.g. ``domains/nba/entities.py``).

    Structural typing via ``@runtime_checkable`` means
    ``isinstance(obj, EntityRegistry)`` succeeds for any object that
    exposes the required methods — no explicit inheritance required.

    Unknown-Token Contract (binding for all implementations)
    --------------------------------------------------------
    ``resolve_team``, ``resolve_player``, and ``parse_game_id`` MUST
    RAISE when given an unrecognised token.  Implementations must never
    guess, silently return a wrong id, or fall back to a default value.
    Acceptable exception types: ``KeyError``, ``ValueError``, or a
    domain-specific subclass thereof.

    This contract is tested in ``tests/kernel/test_config_entities.py``
    and enforced by the kernel's conformance kit (``kernel/testing/``).

    Attributes
    ----------
    sport_id:
        Canonical sport identifier, e.g. ``"nba"``, ``"nfl"``, ``"mlb"``.
        Read-only attribute on every concrete implementation.
    """

    sport_id: str

    # ------------------------------------------------------------------
    # Entity resolution
    # ------------------------------------------------------------------

    def resolve_team(self, token: str) -> str:
        """Resolve any alias or abbreviation to the canonical team key.

        Parameters
        ----------
        token:
            Any form of team identifier the domain supports: tricode,
            full name, city name, numeric id string, etc.

        Returns
        -------
        str
            The domain's canonical opaque team key.  For NBA this is
            the tricode (e.g. ``"NYK"``); for other sports it may be
            any stable string the adapter chooses.

        Raises
        ------
        KeyError | ValueError
            If *token* is not recognised.  Implementations MUST NOT
            silently return a wrong id or guess.

        Examples
        --------
        >>> reg.resolve_team("New York Knicks")  # NBA adapter
        'NYK'
        >>> reg.resolve_team("UNKNOWN_TEAM")
        # raises KeyError or ValueError
        """
        ...

    def resolve_player(self, token: Any) -> str:
        """Resolve a player name or id to the canonical entity_id string.

        Parameters
        ----------
        token:
            Any form of player identifier: display name, numeric id,
            slug, etc.

        Returns
        -------
        str
            The domain's canonical opaque player entity_id.

        Raises
        ------
        KeyError | ValueError
            If *token* is not recognised.  Implementations MUST NOT
            guess or fall back to a default.

        Examples
        --------
        >>> reg.resolve_player("Jalen Brunson")
        '1628384'
        >>> reg.resolve_player("Ghost Player")
        # raises KeyError or ValueError
        """
        ...

    # ------------------------------------------------------------------
    # Game-ID parsing
    # ------------------------------------------------------------------

    def parse_game_id(self, game_id: str) -> dict[str, Any]:
        """Decode a domain game ID into its semantic components.

        The returned dict MUST contain exactly the three keys
        ``"season"``, ``"kind"``, and ``"seq"``.  Additional keys
        are permitted but the kernel depends only on these three.

        Parameters
        ----------
        game_id:
            Domain-specific game identifier string.
            NBA example: ``"0022400001"`` (prefix ``0022`` encodes
            2024-25 regular season; ``400001`` is the sequence).

        Returns
        -------
        dict
            A dict with at least::

                {
                    "season": str,   # e.g. "2024-25"
                    "kind":   str,   # "regular" | "playoff" | domain-specific
                    "seq":    int,   # sequential game number within (season, kind)
                }

        Raises
        ------
        KeyError | ValueError
            If *game_id* does not conform to the domain's game-ID
            grammar.  Implementations MUST raise on unrecognised IDs.
        """
        ...

    # ------------------------------------------------------------------
    # Season helpers
    # ------------------------------------------------------------------

    def season_of(self, d: Any) -> str:
        """Return the canonical season label for a given date.

        Parameters
        ----------
        d:
            A ``datetime.date`` (or equivalent) representing the game
            or event date.

        Returns
        -------
        str
            Season label, e.g. ``"2024-25"`` (NBA) or ``"2024"``
            (single-year seasons like NFL/MLB).
        """
        ...

    # ------------------------------------------------------------------
    # Store-key helpers
    # ------------------------------------------------------------------

    def entity_key(self, kind: str, ident: Any) -> str:
        """Build the opaque string key used by ``PointInTimeStore``.

        Parameters
        ----------
        kind:
            Entity kind: ``"player"``, ``"team"``, ``"game"``, or any
            domain-defined category.
        ident:
            The entity's canonical identifier (already resolved).

        Returns
        -------
        str
            A stable, collision-free key string.  NBA example:
            ``"player:1628384"`` or ``"team:NYK"``.
        """
        ...

    # ------------------------------------------------------------------
    # Sportsbook aliases
    # ------------------------------------------------------------------

    def book_aliases(self) -> Mapping[str, str]:
        """Return the sportsbook name-normalisation mapping.

        Returns
        -------
        Mapping[str, str]
            ``{raw_name: canonical_name}`` pairs.  Used by
            ``kernel/decision/clv.py`` to normalise book names across
            data sources.

            Example (NBA adapter)::

                {
                    "fd":          "fanduel",
                    "fanduel":     "fanduel",
                    "dk":          "draftkings",
                    "draftkings":  "draftkings",
                }
        """
        ...
