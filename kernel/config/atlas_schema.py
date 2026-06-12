"""kernel.config.atlas_schema — AtlasSchema: per-sport intelligence section catalog.

Replaces the module-level ``_DIM_TO_ATLAS`` dict in ``src/loop/error_miner.py``
(AUDIT gap #10) so the kernel can route error-miner suggestions to the correct
intelligence-vault section without hardcoding NBA section names.

An EMPTY instance (``player_sections=()``, ``team_sections=()``) is the valid
launch state for a new sport — the error-miner gracefully skips section lookups
when the catalog is empty.

Zero heavy imports: stdlib + typing + dataclasses only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Tuple


# ---------------------------------------------------------------------------
# AtlasSchema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AtlasSchema:
    """Immutable catalog of intelligence-vault sections for a single sport.

    Used by ``kernel/loop/error_miner.py`` (formerly ``_DIM_TO_ATLAS``) to
    map a residual-bucket context dimension to the atlas section that best
    explains the systematic error.  The kernel sees only section-name strings;
    the NBA adapter declares the concrete catalog in ``domains/nba/config.py``.

    Parameters
    ----------
    sport_id:
        Canonical sport identifier (e.g. ``"nba"``, ``"nfl"``).
    player_sections:
        Ordered tuple of all player-level atlas section names for this sport.
        Example NBA names: ``"shot_profile"``, ``"clutch_scoring"``, etc.
        An empty tuple is a valid new-sport launch state.
    team_sections:
        Ordered tuple of all team-level atlas section names for this sport.
        Example NBA names: ``"offensive_scheme"``, ``"defensive_scheme"``, etc.
        An empty tuple is a valid new-sport launch state.
    entity_frontmatter:
        Mapping (or tuple-of-pairs) describing the frontmatter fields written
        into every entity vault note.  Keys are field names; values are
        descriptive strings (e.g. ``"str"`` or ``"float"``).  May be empty.
    dim_to_section:
        Mapping from an error-miner context-dimension key (e.g.
        ``"game_state:clutch"`` or ``"quarter:Q4"``) to the atlas section name
        that should be proposed when that dimension shows systematic bias.
        Replaces ``_DIM_TO_ATLAS`` in ``src/loop/error_miner.py``.
        May be empty for a new sport.

    Notes
    -----
    All fields are immutable by design (``frozen=True``).  The Mapping fields
    are accepted as any ``Mapping`` at construction time; callers should pass
    plain ``dict`` instances.  The kernel never mutates these mappings.
    """

    sport_id: str
    player_sections: Tuple[str, ...] = ()
    team_sections: Tuple[str, ...] = ()
    entity_frontmatter: Mapping[str, str] = field(default_factory=dict)
    dim_to_section: Mapping[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def player_section_count(self) -> int:
        """Number of registered player-level atlas sections."""
        return len(self.player_sections)

    @property
    def team_section_count(self) -> int:
        """Number of registered team-level atlas sections."""
        return len(self.team_sections)

    def resolve_section(self, dim_key: str) -> str | None:
        """Return the atlas section for *dim_key*, or ``None`` if unmapped.

        Parameters
        ----------
        dim_key:
            Colon-joined dimension+value string used by the error-miner,
            e.g. ``"game_state:clutch"`` or ``"quarter:Q4"``.

        Returns
        -------
        str | None
            The section name to propose, or ``None`` if no mapping exists.
        """
        return self.dim_to_section.get(dim_key)

    def all_sections(self) -> Tuple[str, ...]:
        """Combined ordered tuple of player + team sections.

        Useful for ``atlas.py`` to enumerate the full section universe when
        checking whether an entity carries a specific section.
        """
        return self.player_sections + self.team_sections
