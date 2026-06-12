"""kernel.config.roster — PositionSchema + RosterConfig.

Replaces all hardcoded roster/position literals scattered across the engine
(AUDIT gap #6): NBA on-field count (5), roster_size (15), season length (82),
foul-out limit (6), space-control reach (6 ft), position taxonomy.

Adding a sport = declaring a new RosterConfig instance in
``domains/<sport>/config.py``.  The kernel never contains NBA literals —
those live in ``domains/nba/config.py``.

Zero heavy imports: stdlib + typing + dataclasses only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional, Tuple


# ---------------------------------------------------------------------------
# PositionSchema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PositionSchema:
    """Immutable taxonomy of player positions for a sport.

    The ``positions`` tuple is the authoritative ordered list of position
    codes.  Ordering is load-bearing for any array-positional code that maps
    position indices to model features.

    Parameters
    ----------
    positions:
        Ordered tuple of canonical position codes.
        NBA: ``("PG", "SG", "SF", "PF", "C")``.
        NFL includes 22+ specialist codes; soccer uses ``("GK", "DEF", "MID", "FWD")``.
    archetypes:
        Optional grouping of positions into named archetypes, e.g.
        ``{"guard": ("PG", "SG"), "forward": ("SF", "PF"), "center": ("C",)}``.
        Used by the space-control and playstyle-correlation modules.
        Defaults to an empty dict (no archetype grouping required).
    """

    positions: Tuple[str, ...]
    archetypes: Dict[str, Tuple[str, ...]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def __contains__(self, position: object) -> bool:
        """Support ``"PG" in schema`` membership test.

        Parameters
        ----------
        position:
            The position code to check.

        Returns
        -------
        bool
            ``True`` if *position* is in ``self.positions``.
        """
        return position in self.positions

    def index(self, position: str) -> int:
        """Return the 0-based index of *position* in ``self.positions``.

        Parameters
        ----------
        position:
            The position code to look up.

        Returns
        -------
        int
            0-based index.

        Raises
        ------
        ValueError
            If *position* is not found in ``self.positions``.
        """
        return self.positions.index(position)


# ---------------------------------------------------------------------------
# RosterConfig
# ---------------------------------------------------------------------------

#: Valid substitution-model identifiers.
_SubstitutionModel = Literal["free", "platoon", "limited", "none"]

_VALID_SUBSTITUTION_MODELS: frozenset[str] = frozenset(
    {"free", "platoon", "limited", "none"}
)


@dataclass(frozen=True)
class RosterConfig:
    """Immutable roster specification for any sport.

    Replaces hardcoded constants dispersed across the engine:
    - ``on_field_count`` (NBA 5) used by possession MC + space-control grid.
    - ``season_length_games`` (NBA 82) used by ``season_shrinkage.py`` and
      ``injury_risk`` cumulative-load normalisation (``cum_load / 82.0``).
    - ``foul_out_limit`` (NBA 6) used by foul-out projector + in-game shrinkage.
    - ``reach_ft`` (NBA 6 ft) used by ``space_control.py`` (BASE_REACH 6 ft).

    Parameters
    ----------
    on_field_count:
        Number of players per side on the playing surface simultaneously.
        NBA 5; NFL 11; MLB 9 (batting) / 10 (DH); soccer 11; NHL 6.
    roster_size:
        Total roster size including bench.
        NBA 15; NFL 53; MLB 26 (active) / 40 (40-man); soccer 25.
    season_length_games:
        Number of regular-season games per team.
        NBA 82; NFL 17; MLB 162; NHL 82; soccer 38.
        Replaces the ``/ 82.0`` literal in season-shrinkage and injury-load code.
    positions:
        ``PositionSchema`` instance holding the ordered position taxonomy.
    substitution_model:
        How substitutions work: ``"free"`` (NBA/NHL — unlimited re-entry),
        ``"platoon"`` (MLB — no re-entry once substituted),
        ``"limited"`` (soccer — capped substitution count), or
        ``"none"`` (no substitution concept).
    foul_out_limit:
        Personal fouls / infractions that disqualify a player.
        NBA personal fouls = 6; ``None`` where the concept is absent (soccer,
        baseball, NFL).
    reach_ft:
        Radial reach used by ``kernel/spatial/space_control.py`` for the
        defensive pressure grid.  Was the module-level constant
        ``BASE_REACH = 6`` in ``space_control.py``.
        NBA 6.0 ft; adapt per sport / analysis preference.
    """

    on_field_count: int
    roster_size: int
    season_length_games: int
    positions: PositionSchema
    substitution_model: _SubstitutionModel = "free"
    foul_out_limit: Optional[int] = 6
    reach_ft: float = 6.0

    def __post_init__(self) -> None:
        if self.substitution_model not in _VALID_SUBSTITUTION_MODELS:
            raise ValueError(
                f"RosterConfig.substitution_model must be one of "
                f"{sorted(_VALID_SUBSTITUTION_MODELS)!r}; "
                f"got {self.substitution_model!r}"
            )
        if self.on_field_count < 1:
            raise ValueError(
                f"RosterConfig.on_field_count must be >= 1; "
                f"got {self.on_field_count}"
            )
        if self.roster_size < self.on_field_count:
            raise ValueError(
                f"RosterConfig.roster_size ({self.roster_size}) must be >= "
                f"on_field_count ({self.on_field_count})"
            )
        if self.season_length_games < 1:
            raise ValueError(
                f"RosterConfig.season_length_games must be >= 1; "
                f"got {self.season_length_games}"
            )
        if self.reach_ft <= 0.0:
            raise ValueError(
                f"RosterConfig.reach_ft must be > 0; got {self.reach_ft}"
            )
