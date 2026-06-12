"""kernel.testing.conformance — Reusable SportContext conformance harness.

Any domain adapter runs ``check_sport_context(ctx)`` to get a list of
human-readable violation strings.  An empty list means the context is fully
conformant.  ``assert_sport_context_conformant(ctx)`` raises ``AssertionError``
with all violations joined if any exist.

Import rules (R10 compliance)
-----------------------------
This module imports ONLY from ``kernel.config.*`` and the stdlib.  It NEVER
contains a literal ``import domains`` or ``from domains`` statement.
"""
from __future__ import annotations

from typing import List

from kernel.config.atlas_schema import AtlasSchema
from kernel.config.clock import GameClockConfig
from kernel.config.context import SportContext
from kernel.config.court import CourtConfig
from kernel.config.entities import EntityRegistry
from kernel.config.game_state import GameStateConfig
from kernel.config.pbp import LeagueClient, PBPEventMapper
from kernel.config.roster import RosterConfig
from kernel.config.speed import SpeedConfig
from kernel.config.stats import SportStatRegistry

# ---------------------------------------------------------------------------
# Required suffix of loop_targets
# ---------------------------------------------------------------------------

_REQUIRED_LOOP_TAIL: tuple = ("minutes", "total", "winprob", "usage", "sigma")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_sport_context(ctx: SportContext) -> List[str]:
    """Return a list of human-readable violation strings for *ctx*.

    An empty list means the context is fully conformant.  Each violation is a
    single sentence describing the failing invariant.

    Parameters
    ----------
    ctx:
        The ``SportContext`` instance to validate.

    Returns
    -------
    List[str]
        Violation strings; empty iff fully conformant.
    """
    violations: List[str] = []

    # ------------------------------------------------------------------
    # 1. stats — SportStatRegistry
    # ------------------------------------------------------------------
    if not isinstance(ctx.stats, SportStatRegistry):
        violations.append(
            f"ctx.stats must be a SportStatRegistry; got {type(ctx.stats).__name__}"
        )
    else:
        # 1a. non-empty target_names
        if not ctx.stats.target_names():
            violations.append(
                "ctx.stats.target_names() must be non-empty (no stats registered)"
            )

        # 1b. loop_targets ends with the required meta-tail
        lt = ctx.stats.loop_targets
        tail = lt[-len(_REQUIRED_LOOP_TAIL):]
        if tail != _REQUIRED_LOOP_TAIL:
            violations.append(
                f"ctx.stats.loop_targets must end with {_REQUIRED_LOOP_TAIL!r}; "
                f"got tail {tail!r}"
            )

        # 1c. priced_order() ⊆ target_names()
        target_set = set(ctx.stats.target_names())
        extra_priced = set(ctx.stats.priced_order()) - target_set
        if extra_priced:
            violations.append(
                f"ctx.stats.priced_order() contains names not in target_names(): "
                f"{sorted(extra_priced)}"
            )

        # 1d. sport_id is a non-empty str
        sid = ctx.stats.sport_id
        if not isinstance(sid, str) or not sid.strip():
            violations.append(
                f"ctx.stats.sport_id must be a non-empty str; got {sid!r}"
            )

    # ------------------------------------------------------------------
    # 2. clock — GameClockConfig
    # ------------------------------------------------------------------
    if not isinstance(ctx.clock, GameClockConfig):
        violations.append(
            f"ctx.clock must be a GameClockConfig; got {type(ctx.clock).__name__}"
        )
    else:
        if ctx.clock.regulation_sec() <= 0 and not ctx.clock.untimed:
            violations.append(
                "ctx.clock.regulation_sec() must be > 0, or ctx.clock.untimed must be True"
            )

    # ------------------------------------------------------------------
    # 3. roster — RosterConfig
    # ------------------------------------------------------------------
    if not isinstance(ctx.roster, RosterConfig):
        violations.append(
            f"ctx.roster must be a RosterConfig; got {type(ctx.roster).__name__}"
        )
    else:
        if ctx.roster.on_field_count < 1:
            violations.append(
                f"ctx.roster.on_field_count must be >= 1; got {ctx.roster.on_field_count}"
            )
        if ctx.roster.roster_size < ctx.roster.on_field_count:
            violations.append(
                f"ctx.roster.roster_size ({ctx.roster.roster_size}) must be >= "
                f"on_field_count ({ctx.roster.on_field_count})"
            )

    # ------------------------------------------------------------------
    # 4. game_state — GameStateConfig (primary fields present)
    # ------------------------------------------------------------------
    if not isinstance(ctx.game_state, GameStateConfig):
        violations.append(
            f"ctx.game_state must be a GameStateConfig; got {type(ctx.game_state).__name__}"
        )
    else:
        _required_gs_fields = (
            "blowout_margin", "clutch_margin", "clutch_remaining_sec",
            "garbage_margin", "competitive_margin", "final_margin_sigma",
            "winprob_promotion_period",
        )
        for fname in _required_gs_fields:
            if not hasattr(ctx.game_state, fname):
                violations.append(
                    f"ctx.game_state is missing required field '{fname}'"
                )

    # ------------------------------------------------------------------
    # 5. entities — EntityRegistry (runtime_checkable protocol)
    # ------------------------------------------------------------------
    if not isinstance(ctx.entities, EntityRegistry):
        violations.append(
            f"ctx.entities must satisfy EntityRegistry protocol; "
            f"got {type(ctx.entities).__name__} (missing required methods)"
        )

    # ------------------------------------------------------------------
    # 6. pbp_mapper — PBPEventMapper (runtime_checkable protocol)
    # ------------------------------------------------------------------
    if not isinstance(ctx.pbp_mapper, PBPEventMapper):
        violations.append(
            f"ctx.pbp_mapper must satisfy PBPEventMapper protocol; "
            f"got {type(ctx.pbp_mapper).__name__} (missing required methods)"
        )

    # ------------------------------------------------------------------
    # 7. league_client — LeagueClient (runtime_checkable protocol)
    # ------------------------------------------------------------------
    if not isinstance(ctx.league_client, LeagueClient):
        violations.append(
            f"ctx.league_client must satisfy LeagueClient protocol; "
            f"got {type(ctx.league_client).__name__} (missing required methods)"
        )

    # ------------------------------------------------------------------
    # 8. atlas_schema — AtlasSchema (empty sections are allowed)
    # ------------------------------------------------------------------
    if not isinstance(ctx.atlas_schema, AtlasSchema):
        violations.append(
            f"ctx.atlas_schema must be an AtlasSchema; "
            f"got {type(ctx.atlas_schema).__name__}"
        )

    # ------------------------------------------------------------------
    # 9. Optional: court — None or CourtConfig
    # ------------------------------------------------------------------
    if ctx.court is not None and not isinstance(ctx.court, CourtConfig):
        violations.append(
            f"ctx.court must be None or a CourtConfig; got {type(ctx.court).__name__}"
        )

    # ------------------------------------------------------------------
    # 10. Optional: speed — None or SpeedConfig
    # ------------------------------------------------------------------
    if ctx.speed is not None and not isinstance(ctx.speed, SpeedConfig):
        violations.append(
            f"ctx.speed must be None or a SpeedConfig; got {type(ctx.speed).__name__}"
        )

    return violations


def assert_sport_context_conformant(ctx: SportContext) -> None:
    """Assert that *ctx* is fully conformant; raise ``AssertionError`` if not.

    Parameters
    ----------
    ctx:
        The ``SportContext`` instance to validate.

    Raises
    ------
    AssertionError
        If any violations are found.  The error message lists every violation.
    """
    violations = check_sport_context(ctx)
    if violations:
        bullet_list = "\n".join(f"  • {v}" for v in violations)
        raise AssertionError(
            f"SportContext conformance failed ({len(violations)} violation(s)):\n"
            + bullet_list
        )
