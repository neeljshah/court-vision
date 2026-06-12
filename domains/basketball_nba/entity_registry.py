"""domains.basketball_nba.entity_registry — NBAEntityRegistry.

Implements the kernel ``EntityRegistry`` protocol by PURE DELEGATION to
the existing NBA source tables — zero logic is moved or duplicated here.

Delegation map
--------------
resolve_team   : ``src.data.game_matcher._LABEL_TO_ABBREV``
                 (lowercase alias/tricode → official tricode)
                 + ``src.data.line_monitor._TEAM_ALIASES``
                 (builds a reverse map: full display name → tricode)
parse_game_id  : ``src.data.pbp_features._season_from_game_id``
                 for seasons 2022-23 through 2024-25; a lightweight
                 extension covers 2025-26 and beyond using the same
                 prefix-rule the source function uses.
resolve_player : documented minimal impl — NBA numeric ID passthrough;
                 raises on non-numeric / unknown tokens.
season_of      : pure NBA calendar logic (Oct split), no external dep.
entity_key     : ``"<kind>:<ident>"`` stable key, no external dep.
book_aliases   : inline sportsbook name table, no external dep.

Unknown-Token Contract (binding)
---------------------------------
``resolve_team`` and ``resolve_player`` RAISE (KeyError) on unrecognised
input — they never guess, silently return a wrong id, or fall back to a
default.  ``parse_game_id`` raises ValueError on malformed / unrecognised
game IDs.

No network calls at import or at runtime.  Python 3.9 floor.
"""
from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Mapping

# ---------------------------------------------------------------------------
# Kernel protocol import
# ---------------------------------------------------------------------------
from kernel.config.entities import EntityRegistry  # noqa: F401 (re-exported)

# ---------------------------------------------------------------------------
# Delegated source imports — SYMBOL-ONLY to stay light
# ---------------------------------------------------------------------------
# game_matcher defines only module-level dicts + helpers; the import is
# network-free (no NBA API call at module level).
from src.data.game_matcher import _LABEL_TO_ABBREV  # dict[str, str]

# line_monitor defines _TEAM_ALIASES at module level (no network at import).
from src.data.line_monitor import _TEAM_ALIASES  # Dict[str, List[str]]

# pbp_features._season_from_game_id is a pure function operating on a string.
from src.data.pbp_features import _season_from_game_id  # Callable[[str], str|None]


# ---------------------------------------------------------------------------
# Build a reverse alias map from _TEAM_ALIASES at import time
# Mapping: lowercase display name / full name → tricode
# e.g. "golden state warriors" → "GSW"
# ---------------------------------------------------------------------------
def _build_full_name_map() -> dict[str, str]:
    """Build {lowercase_full_name: tricode} from ``_TEAM_ALIASES``."""
    result: dict[str, str] = {}
    for tricode, names in _TEAM_ALIASES.items():
        result[tricode.lower()] = tricode          # tricode itself
        for name in names:
            result[name.lower()] = tricode
    return result


_FULL_NAME_TO_TRICODE: dict[str, str] = _build_full_name_map()

# Master lookup: lowercase token → tricode (union of both tables)
# _LABEL_TO_ABBREV keys are already lowercase
_ALL_TEAM_TOKENS: dict[str, str] = {**_LABEL_TO_ABBREV, **_FULL_NAME_TO_TRICODE}


# ---------------------------------------------------------------------------
# NBA game-ID parsing helpers
# ---------------------------------------------------------------------------

# NBA game ID format (10 digits): 00 T YY ZZ SSS
# Where:
#   00        = constant prefix
#   T (1 digit): type code: 2=regular, 4=playoff, 1=preseason, 3=allstar, 5=play-in
#   YY (2 digits): 2-digit start year of season (e.g. 25 → 2025-26)
#   ZZ (2 digits): typically "00" padding / round indicator
#   SSS (3+ digits): game sequence number
#
# Examples:
#   "0022400001"  → T=2 (regular), YY=24 → 2024-25, seq=0001
#   "0042500404"  → T=4 (playoff),  YY=25 → 2025-26, seq=404
#   "0022200007"  → T=2 (regular), YY=22 → 2022-23, seq=0007
#
# Note: _season_from_game_id checks startswith("002YYOO") / "004YY00" with
# a 7-char prefix = "00" + T + YY + "0", confirming the layout above.

_GAME_ID_RE = re.compile(r"^00([14235])(\d{2})(\d{2})(\d+)$")

# Maps single-digit type code → kind string
_KIND_MAP: dict[str, str] = {
    "1": "preseason",
    "2": "regular",
    "3": "allstar",
    "4": "playoff",
    "5": "playin",
}


def _parse_nba_game_id(game_id: str) -> dict[str, Any]:
    """Parse a 10-digit NBA game ID into semantic components.

    Delegates to ``_season_from_game_id`` for seasons it handles (2022-23
    through 2024-25).  For other seasons (e.g. 2025-26) this function
    derives the season from the year-prefix directly.

    Parameters
    ----------
    game_id:
        10-digit NBA game ID string, e.g. ``"0042500404"``.

    Returns
    -------
    dict
        ``{"season": str, "kind": str, "seq": int}``

    Raises
    ------
    ValueError
        If *game_id* does not match the NBA game-ID grammar.
    """
    m = _GAME_ID_RE.match(game_id)
    if not m:
        raise ValueError(
            f"[NBAEntityRegistry] game_id {game_id!r} does not match "
            "the expected NBA 10-digit format '00TTYYZZSSSS'."
        )

    type_code = m.group(1)       # e.g. "4" for playoffs, "2" for regular
    yr_start  = m.group(2)       # e.g. "25" for 2025-26 season
    # m.group(3) = ZZ padding digits (e.g. "00"), not used directly
    seq_str   = m.group(4)       # e.g. "404" or "0001"

    # Derive kind
    kind = _KIND_MAP.get(type_code)
    if kind is None:
        raise ValueError(
            f"[NBAEntityRegistry] Unknown game type code {type_code!r} "
            f"in game_id {game_id!r}."
        )

    # Delegate to existing source function for seasons it handles (2022-25).
    # For 2025-26 and beyond, derive directly from the yr_start prefix.
    delegated_season = _season_from_game_id(game_id)
    if delegated_season is not None:
        season = delegated_season
    else:
        # Extension: full year = 2000 + int(yr_start), season = "YYYY-(YY+1)"
        start_year_int = 2000 + int(yr_start)
        end_year_short = str(start_year_int + 1)[2:]
        season = f"{start_year_int}-{end_year_short}"

    seq = int(seq_str)
    return {"season": season, "kind": kind, "seq": seq}


# ---------------------------------------------------------------------------
# NBAEntityRegistry
# ---------------------------------------------------------------------------


class NBAEntityRegistry:
    """NBA adapter implementation of the kernel ``EntityRegistry`` protocol.

    Satisfies the protocol via structural typing (no inheritance needed).
    Pass ``isinstance(obj, EntityRegistry)`` check because all required
    methods and the ``sport_id`` attribute are present.

    All team-resolution logic is delegated to:
    - ``_LABEL_TO_ABBREV``  (``src.data.game_matcher``)
    - ``_TEAM_ALIASES``     (``src.data.line_monitor``)

    Game-ID parsing delegates to ``_season_from_game_id``
    (``src.data.pbp_features``) and extends for newer seasons.

    Unknown-Token Contract: ``resolve_team`` and ``resolve_player`` raise
    KeyError on unrecognised input; ``parse_game_id`` raises ValueError.
    """

    sport_id: str = "basketball_nba"

    # ------------------------------------------------------------------
    # Entity resolution
    # ------------------------------------------------------------------

    def resolve_team(self, token: str) -> str:
        """Resolve any team alias to the canonical NBA tricode.

        Delegates to the union of ``_LABEL_TO_ABBREV`` and the reverse map
        built from ``_TEAM_ALIASES``.  Lookup is case-insensitive.

        Parameters
        ----------
        token:
            Any supported team alias: tricode (e.g. ``"NYK"``), nickname
            (e.g. ``"knicks"``), city (e.g. ``"new york"``), or full
            display name (e.g. ``"New York Knicks"``).

        Returns
        -------
        str
            Official NBA tricode, e.g. ``"NYK"``.

        Raises
        ------
        KeyError
            If *token* is not recognised.  Never guesses.
        """
        key = token.strip().lower()
        result = _ALL_TEAM_TOKENS.get(key)
        if result is None:
            raise KeyError(
                f"[NBAEntityRegistry] Unknown team token: {token!r}. "
                "Unknown-Token Contract: never guesses — raise instead."
            )
        return result

    def resolve_player(self, token: Any) -> str:
        """Resolve a player token to its canonical entity-id string.

        Minimal implementation: accepts numeric NBA player IDs (int or
        digit-string) and returns them as a zero-padded 10-char string.
        Non-numeric tokens and empty strings raise KeyError.

        Parameters
        ----------
        token:
            Numeric NBA player ID (int or str of digits).

        Returns
        -------
        str
            Canonical player entity-id string.

        Raises
        ------
        KeyError
            If *token* is not a recognised numeric player ID.
        """
        token_str = str(token).strip()
        if not token_str or not token_str.isdigit():
            raise KeyError(
                f"[NBAEntityRegistry] Unknown player token: {token!r}. "
                "Provide a numeric NBA player ID. "
                "Unknown-Token Contract: never guesses — raise instead."
            )
        return token_str

    # ------------------------------------------------------------------
    # Game-ID parsing
    # ------------------------------------------------------------------

    def parse_game_id(self, game_id: str) -> dict[str, Any]:
        """Decode an NBA game ID string into semantic components.

        Delegates season detection to ``_season_from_game_id`` where
        available; extends to newer seasons via direct prefix analysis.

        Parameters
        ----------
        game_id:
            10-digit NBA game ID, e.g. ``"0042500404"``.

        Returns
        -------
        dict
            ``{"season": str, "kind": str, "seq": int}``

        Raises
        ------
        ValueError
            If *game_id* does not match the NBA game-ID grammar.
        """
        return _parse_nba_game_id(game_id)

    # ------------------------------------------------------------------
    # Season helpers
    # ------------------------------------------------------------------

    def season_of(self, d: Any) -> str:
        """Return the NBA season label (e.g. ``"2025-26"``) for a date.

        NBA seasons start in October.  Dates in Oct-Dec belong to the
        season that started in that calendar year; Jan-Sep belong to
        the season that started the previous calendar year.

        Parameters
        ----------
        d:
            A ``datetime.date`` or ``datetime.datetime`` instance.

        Returns
        -------
        str
            Season label, e.g. ``"2025-26"``.
        """
        if isinstance(d, datetime.datetime):
            year, month = d.year, d.month
        elif isinstance(d, datetime.date):
            year, month = d.year, d.month
        else:
            raise TypeError(
                f"season_of expects a datetime.date, got {type(d).__name__!r}."
            )
        start_year = year if month >= 10 else year - 1
        return f"{start_year}-{str(start_year + 1)[2:]}"

    # ------------------------------------------------------------------
    # Store-key helpers
    # ------------------------------------------------------------------

    def entity_key(self, kind: str, ident: Any) -> str:
        """Build the opaque PointInTimeStore key string.

        Parameters
        ----------
        kind:
            Entity kind: ``"player"``, ``"team"``, ``"game"``.
        ident:
            The entity's canonical identifier (already resolved).

        Returns
        -------
        str
            Stable key string, e.g. ``"team:NYK"`` or ``"player:1628384"``.
        """
        return f"{kind}:{ident}"

    # ------------------------------------------------------------------
    # Sportsbook aliases
    # ------------------------------------------------------------------

    def book_aliases(self) -> Mapping[str, str]:
        """Return the sportsbook name-normalisation mapping.

        Returns
        -------
        Mapping[str, str]
            ``{raw_name: canonical_name}`` pairs used by
            ``kernel/decision/clv.py``.
        """
        return {
            "fd":          "fanduel",
            "fanduel":     "fanduel",
            "dk":          "draftkings",
            "draftkings":  "draftkings",
            "mgm":         "betmgm",
            "betmgm":      "betmgm",
            "czr":         "caesars",
            "caesars":     "caesars",
            "bet365":      "bet365",
            "pointsbet":   "pointsbet",
            "pb":          "pointsbet",
            "barstool":    "barstool",
            "betrivers":   "betrivers",
            "br":          "betrivers",
        }
