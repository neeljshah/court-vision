"""kernel.config.pbp — CanonicalEvent, PBPEventMapper, LeagueClient.

Play-by-play (PBP) abstraction layer for the sport-agnostic kernel.

Design choices
--------------
* ``CanonicalEventKind`` is an ``enum.Enum`` (not a validated str) so that
  mypy can exhaustively check branches over event kinds and IDE auto-complete
  works without any magic string literals in kernel code.

* ``CanonicalEvent.detail`` is an **opaque** ``dict`` payload provided by the
  adapter.  KERNEL CODE MUST NOT read, inspect, or branch on ``detail`` — it
  exists solely so adapters can carry raw league-specific data through the
  canonical layer without losing fidelity.  Any derived meaning must be
  extracted by the *adapter* before constructing the ``CanonicalEvent``.

* ``PBPEventMapper`` and ``LeagueClient`` are ``typing.Protocol`` classes
  decorated with ``@runtime_checkable``.  This means adapter classes are
  checked *structurally* (duck-typed): any class that implements all required
  methods passes ``isinstance(obj, PBPEventMapper)`` without inheritance.

Zero heavy imports: stdlib + typing + dataclasses + enum only.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# CanonicalEventKind — event taxonomy
# ---------------------------------------------------------------------------

class CanonicalEventKind(enum.Enum):
    """Exhaustive taxonomy of events the kernel reasons over.

    Adapters must map every league-specific event to one of these values.
    Unmapped events SHOULD be reported as ``OTHER`` rather than silently
    dropped so that downstream consumers can decide to ignore them.

    Members
    -------
    SCORE
        A scoring play (field goal, converted free throw, try, goal, …).
    MISS
        A missed scoring attempt (missed shot, blocked attempt, …).
    TURNOVER
        Ball/possession surrendered without a scoring attempt.
    PENALTY
        A foul, technical, or rule violation.  Includes flagrant fouls,
        intentional fouls, and sport-specific infractions.
    SUBSTITUTION
        A player enters or leaves the active playing unit.
    PERIOD_START
        The start of a regulation period or overtime period.
    PERIOD_END
        The end of a regulation period or overtime period.
    STOPPAGE
        A clock-stop that does not fall into any other category (timeout,
        injury stoppage, challenge review, …).
    POSSESSION_CHANGE
        Explicit possession transfer not triggered by a scoring play or
        turnover (e.g. jump-ball resolution, kick-ball violation recovery).
    OTHER
        Any event the adapter cannot classify into the above categories.
        Kernel code must never branch on ``OTHER`` for game-state logic —
        it should be used only for passthrough / logging.
    """

    SCORE = "SCORE"
    MISS = "MISS"
    TURNOVER = "TURNOVER"
    PENALTY = "PENALTY"
    SUBSTITUTION = "SUBSTITUTION"
    PERIOD_START = "PERIOD_START"
    PERIOD_END = "PERIOD_END"
    STOPPAGE = "STOPPAGE"
    POSSESSION_CHANGE = "POSSESSION_CHANGE"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# CanonicalEvent — immutable, sport-agnostic event record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CanonicalEvent:
    """Immutable, sport-agnostic representation of a single game event.

    All numeric and categorical fields are *kernel-visible* — the kernel may
    freely read and branch on them.

    The ``detail`` field is the ONLY exception: it carries raw
    league-specific data opaquely.  **Kernel code MUST NOT inspect
    ``detail``** — it is reserved for adapters and adapter-level tests.

    Parameters
    ----------
    kind:
        The event's canonical classification (a ``CanonicalEventKind``
        member).  Required.
    ts_game_sec:
        Elapsed game time in seconds from the start of the game at the
        moment this event occurred.  Monotonically non-decreasing within a
        game.  0.0 = tip-off / first play.
    period:
        1-indexed period number in which the event occurred.  OT periods
        count beyond ``n_periods`` (e.g. NBA OT1 = period 5).
    side:
        Optional identifier for the team associated with the event
        (e.g. the scoring team, the fouling team).  Domain-defined string
        (could be a team abbreviation, NBA team ID as str, or "home"/"away").
        ``None`` for events that are not team-specific (jump-balls, period
        starts, …).
    points:
        Points (or equivalent score units) awarded by this event.  Zero for
        non-scoring events.  Free-throw adapters should emit one event per
        made free throw with ``points=1``.
    actor_id:
        Optional domain-specific identifier of the primary actor (player who
        scored, turned the ball over, was substituted, etc.).  ``None`` for
        team-level events.
    detail:
        **OPAQUE** raw-event payload from the adapter.  The kernel MUST NOT
        read or branch on this dict.  Adapters use it to preserve league-
        specific fields (play_type, clock_string, qualifier codes, …) that
        do not fit the canonical schema.  Consumers downstream of the kernel
        (adapter-level analytics) may inspect ``detail`` freely.

        The field defaults to an empty dict so callers can omit it.
    """

    kind: CanonicalEventKind
    ts_game_sec: float
    period: int
    side: Optional[str] = None
    points: int = 0
    actor_id: Optional[str] = None
    # ``field(default_factory=dict)`` is required because mutable defaults are
    # not allowed as dataclass field defaults, even on frozen dataclasses.
    detail: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PBPEventMapper — adapter protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class PBPEventMapper(Protocol):
    """Structural protocol for a play-by-play event mapper.

    Any class that implements these three methods (with compatible signatures)
    satisfies the protocol — no inheritance required.  The kernel uses
    ``isinstance(obj, PBPEventMapper)`` at adapter registration time
    (enabled by ``@runtime_checkable``).

    Implementors live in ``domains/<sport>/pbp.py`` and must NOT be imported
    by kernel modules at module load time (to keep kernel import clean).

    Methods
    -------
    to_canonical(raw_event)
        Convert a single raw league-specific event dict/object to a
        ``CanonicalEvent``.  Raises ``ValueError`` if the event cannot be
        mapped.  Must never return ``None`` — use ``CanonicalEventKind.OTHER``
        for unmappable events.

    iter_game(game_id)
        Yield ``CanonicalEvent`` instances for all events in a game in
        chronological order (ascending ``ts_game_sec``).  ``game_id`` is a
        domain-specific identifier (NBA game ID string, NFL game key, …).

    possession_side(event)
        Return the ``side`` string for the team that has possession *after*
        this event resolves, or ``None`` if possession is indeterminate (jump
        ball, period start before tip-off, …).
    """

    def to_canonical(self, raw_event: Any) -> CanonicalEvent:
        """Convert a raw league event to a ``CanonicalEvent``."""
        ...

    def iter_game(self, game_id: str) -> Iterator[CanonicalEvent]:
        """Yield canonical events for *game_id* in chronological order."""
        ...

    def possession_side(self, event: CanonicalEvent) -> Optional[str]:
        """Return the possessing team's side identifier after *event*, or None."""
        ...


# ---------------------------------------------------------------------------
# LeagueClient — adapter protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class LeagueClient(Protocol):
    """Structural protocol for a league data client.

    Defines the minimum API surface the kernel expects from any league
    data source (REST API wrapper, local cache reader, mock, …).

    All methods accept and return domain-specific types — the kernel does
    not inspect return values, it only routes them through to adapters.
    Type annotations use ``Any`` deliberately so that adapters are free to
    return rich domain-specific objects without breaking the structural check.

    Methods
    -------
    get_schedule(season)
        Return the schedule for a season identifier (e.g. ``"2025-26"``).

    get_box_score(game_id)
        Return the box score for a completed or in-progress game.

    get_pbp(game_id)
        Return play-by-play data for a game.  May be a list of raw event
        dicts, a domain-specific container, or a file path — the adapter
        interprets it.

    get_roster(team_id, season)
        Return the roster for a team in a given season.

    get_player_gamelog(player_id, season)
        Return the per-game log for a player in a given season.

    get_availability(player_id, game_id)
        Return the availability status of a player for a given game
        (e.g. active, inactive, injured, out).
    """

    def get_schedule(self, season: str) -> Any:
        """Return the schedule for *season*."""
        ...

    def get_box_score(self, game_id: str) -> Any:
        """Return the box score for *game_id*."""
        ...

    def get_pbp(self, game_id: str) -> Any:
        """Return play-by-play data for *game_id*."""
        ...

    def get_roster(self, team_id: str, season: str) -> Any:
        """Return the roster for *team_id* in *season*."""
        ...

    def get_player_gamelog(self, player_id: str, season: str) -> Any:
        """Return the per-game log for *player_id* in *season*."""
        ...

    def get_availability(self, player_id: str, game_id: str) -> Any:
        """Return the availability status of *player_id* for *game_id*."""
        ...
