"""kernel.testing.fixtures — Reusable toy SportContext factories.

Provides two minimal, protocol-satisfying SportContext instances for use
in kernel tests so that individual tests do not have to re-invent boilerplate.

Both contexts are SPORT-BLIND — they import only from ``kernel.config.*``
and the stdlib.  No ``domains`` import, no ``src`` import, nothing heavy.

Factories
---------
make_toyball_context()
    A minimal VALID timed toy sport (sport_id="toyball").  2 stats, 2 periods,
    5-on-field.  Passes ``check_sport_context`` with zero violations.

make_toyball_untimed_context()
    An untimed inning-style toy sport (sport_id="toyball_untimed").  Satisfies
    the untimed path: clock.untimed=True, regulation_sec()==0.
    Passes ``check_sport_context`` with zero violations.
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, Mapping, Optional

from kernel.config.atlas_schema import AtlasSchema
from kernel.config.clock import GameClockConfig
from kernel.config.context import SportContext
from kernel.config.entities import EntityRegistry
from kernel.config.game_state import GameStateConfig
from kernel.config.pbp import CanonicalEvent, CanonicalEventKind, LeagueClient, PBPEventMapper
from kernel.config.roster import PositionSchema, RosterConfig
from kernel.config.stats import SportStatRegistry, StatSpec


# ---------------------------------------------------------------------------
# Toy protocol implementations
# ---------------------------------------------------------------------------


class _ToyEntityRegistry:
    """Minimal EntityRegistry implementation for toy sports.

    Raises ``KeyError`` on any unrecognised token as the contract requires.
    """

    sport_id: str = "toyball"

    _TEAMS: Dict[str, str] = {"HOME": "HOME", "AWAY": "AWAY"}
    _PLAYERS: Dict[str, str] = {"p1": "p1", "p2": "p2"}

    def resolve_team(self, token: str) -> str:
        """Resolve a team token; raises KeyError if unknown."""
        if token not in self._TEAMS:
            raise KeyError(f"Unknown team token: {token!r}")
        return self._TEAMS[token]

    def resolve_player(self, token: Any) -> str:
        """Resolve a player token; raises KeyError if unknown."""
        key = str(token)
        if key not in self._PLAYERS:
            raise KeyError(f"Unknown player token: {token!r}")
        return self._PLAYERS[key]

    def parse_game_id(self, game_id: str) -> dict:
        """Parse a toy game ID; raises ValueError if malformed."""
        if not game_id.startswith("TOY-"):
            raise ValueError(f"Not a toy game ID: {game_id!r}")
        return {"season": "2025-26", "kind": "regular", "seq": 1}

    def season_of(self, d: Any) -> str:
        """Return a fixed season label."""
        return "2025-26"

    def entity_key(self, kind: str, ident: Any) -> str:
        """Build a stable entity key string."""
        return f"{kind}:{ident}"

    def book_aliases(self) -> Mapping[str, str]:
        """Return a minimal sportsbook alias map."""
        return {"toy_book": "toy_book"}


class _ToyPBPEventMapper:
    """Minimal PBPEventMapper implementation for toy sports."""

    def to_canonical(self, raw_event: Any) -> CanonicalEvent:
        """Convert any raw event to a canonical SCORE event."""
        return CanonicalEvent(
            kind=CanonicalEventKind.SCORE,
            ts_game_sec=0.0,
            period=1,
        )

    def iter_game(self, game_id: str) -> Iterator[CanonicalEvent]:
        """Yield zero events (empty toy game)."""
        return iter([])

    def possession_side(self, event: CanonicalEvent) -> Optional[str]:
        """Return None (possession indeterminate in toy sport)."""
        return None


class _ToyLeagueClient:
    """Minimal LeagueClient implementation for toy sports."""

    def get_schedule(self, season: str) -> Any:
        """Return an empty schedule."""
        return []

    def get_box_score(self, game_id: str) -> Any:
        """Return an empty box score."""
        return {}

    def get_pbp(self, game_id: str) -> Any:
        """Return empty play-by-play data."""
        return []

    def get_roster(self, team_id: str, season: str) -> Any:
        """Return an empty roster."""
        return []

    def get_player_gamelog(self, player_id: str, season: str) -> Any:
        """Return an empty game log."""
        return []

    def get_availability(self, player_id: str, game_id: str) -> Any:
        """Return a fixed available status."""
        return "active"


# ---------------------------------------------------------------------------
# Shared sub-object builders
# ---------------------------------------------------------------------------


def _make_toy_stats(sport_id: str) -> SportStatRegistry:
    """Build a minimal 2-stat SportStatRegistry for the given sport_id."""
    stats = {
        "score": StatSpec(
            name="score",
            kind="count",
            display="Score",
            sigma_default=5.0,
            priced=True,
            higher_is_better=True,
        ),
        "assists": StatSpec(
            name="assists",
            kind="count",
            display="Assists",
            sigma_default=2.0,
            priced=True,
            higher_is_better=True,
        ),
    }
    return SportStatRegistry(
        sport_id=sport_id,
        stats=stats,
        box_score_mapping={"SCR": "score", "AST": "assists"},
        score_stat="score",
        minutes_equiv="minutes",
    )


def _make_toy_game_state() -> GameStateConfig:
    """Build a minimal GameStateConfig suitable for toy sports."""
    return GameStateConfig(
        blowout_margin=10.0,
        clutch_margin=3.0,
        clutch_remaining_sec=120.0,
        garbage_margin=15.0,
        competitive_margin=8.0,
        final_margin_sigma=5.0,
        winprob_promotion_period=2,
        legacy_overrides={},
    )


def _make_toy_roster() -> RosterConfig:
    """Build a minimal RosterConfig for a 5-on-field toy sport."""
    return RosterConfig(
        on_field_count=5,
        roster_size=10,
        season_length_games=20,
        positions=PositionSchema(positions=("F", "M", "D", "G", "U")),
        substitution_model="free",
        foul_out_limit=5,
        reach_ft=4.0,
    )


def _make_toy_atlas(sport_id: str) -> AtlasSchema:
    """Build a minimal AtlasSchema for the given sport_id."""
    return AtlasSchema(
        sport_id=sport_id,
        player_sections=("scoring",),
        team_sections=("defense",),
    )


# ---------------------------------------------------------------------------
# Public factories
# ---------------------------------------------------------------------------


def make_toyball_context() -> SportContext:
    """Return a minimal VALID timed toy SportContext (sport_id='toyball').

    The context has:
    - 2 stats (score, assists), both priced.
    - 2 periods of 600 seconds each (timed sport, regulation_sec()=1200).
    - 5 players on field.
    - Tiny inline toy implementations of EntityRegistry, PBPEventMapper,
      and LeagueClient that pass isinstance checks.
    - A minimal AtlasSchema.

    Passes ``check_sport_context`` with zero violations.

    Returns
    -------
    SportContext
    """
    return SportContext(
        stats=_make_toy_stats("toyball"),
        clock=GameClockConfig(
            n_periods=2,
            period_len_sec=600,
            ot_len_sec=300,
            untimed=False,
            play_clock_sec=30,
            penalty_threshold=5,
        ),
        roster=_make_toy_roster(),
        game_state=_make_toy_game_state(),
        pbp_mapper=_ToyPBPEventMapper(),
        league_client=_ToyLeagueClient(),
        entities=_ToyEntityRegistry(),
        source_tiers={"toy_feed": 1},
        atlas_schema=_make_toy_atlas("toyball"),
    )


def make_toyball_untimed_context() -> SportContext:
    """Return a minimal VALID untimed toy SportContext (sport_id='toyball_untimed').

    The context has:
    - 2 stats (score, assists), both priced.
    - 9 periods, period_len_sec=0 (untimed inning-style sport),
      clock.untimed=True, regulation_sec()==0.
    - 5 players on field.
    - Same tiny inline toy protocol implementations as the timed variant.

    Passes ``check_sport_context`` with zero violations.  The conformance
    checker accepts untimed contexts where clock.untimed=True (even though
    regulation_sec()==0).

    Returns
    -------
    SportContext
    """
    return SportContext(
        stats=_make_toy_stats("toyball_untimed"),
        clock=GameClockConfig(
            n_periods=9,
            period_len_sec=0,
            ot_len_sec=0,
            untimed=True,
            play_clock_sec=None,
            penalty_threshold=None,
        ),
        roster=_make_toy_roster(),
        game_state=_make_toy_game_state(),
        pbp_mapper=_ToyPBPEventMapper(),
        league_client=_ToyLeagueClient(),
        entities=_ToyEntityRegistry(),
        source_tiers={"toy_feed": 1},
        atlas_schema=_make_toy_atlas("toyball_untimed"),
    )
