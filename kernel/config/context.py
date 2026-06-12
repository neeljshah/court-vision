"""kernel.config.context — SportContext: the single injected aggregate.

``SportContext`` is the ONE object constructed by a domain adapter at
process start and passed explicitly (constructor injection) to every
kernel module that needs sport-specific configuration.

**No global mutable singleton. No import-time side effects.**

All nine sub-objects are typed against the kernel protocols and dataclasses
defined in ``kernel/config/``.  Optional fields ARE the capability-subset
mechanism: a sport that ships without CV support sets ``court=None`` and
``speed=None``; a sport without a PBP layer can supply a stub for
``pbp_mapper`` (the protocol is structurally typed, so any object exposing
the right methods satisfies it).

Dependency rule (R10)
---------------------
This module imports ONLY from ``kernel.config.*``.  It NEVER contains a
literal ``import domains`` or ``from domains`` statement.  Domain discovery
is the responsibility of ``kernel.config.registry.load_sport``, which uses
``importlib.import_module`` with a string sport-id — keeping this file
domain-agnostic.

RECONCILIATION NOTE (for orchestrator — do NOT resolve here)
-------------------------------------------------------------
The registry mechanism in ``kernel/config/registry.py`` discovers a domain
package via ``importlib.import_module(f"domains.{sport_id}.config")``.  For
``load_sport("basketball_nba")`` to succeed the package must be at
``domains/basketball_nba/``.  However, the skeleton task that scaffolded the
NBA domain created ``domains/nba/`` — the sport_id used in that package may
be ``"nba"`` rather than ``"basketball_nba"``.

P0-D-017 (NBA registration) settles whether to:

  (a) rename the package ``domains/nba/`` → ``domains/basketball_nba/``, or
  (b) alias the sport_id so ``register_sport`` accepts both, or
  (c) add an importlib alias in ``domains/basketball_nba/__init__.py``.

P0-D-010 only provides the generic mechanism.  Tests use a toy domain whose
package name and sport_id are deliberately kept in sync to avoid touching the
real nba/ directory before P0-D-017 decides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from kernel.config.atlas_schema import AtlasSchema
from kernel.config.clock import GameClockConfig
from kernel.config.court import CourtConfig
from kernel.config.entities import EntityRegistry
from kernel.config.game_state import GameStateConfig
from kernel.config.pbp import LeagueClient, PBPEventMapper
from kernel.config.roster import RosterConfig
from kernel.config.speed import SpeedConfig
from kernel.config.stats import SportStatRegistry


@dataclass(frozen=True)
class SportContext:
    """Immutable aggregate of all sport-specific kernel configuration.

    One instance is constructed per sport at process start and injected
    explicitly into every kernel module.  The kernel never reads global state
    or imports ``domains.*`` at the module level — all sport-specific
    behaviour is routed through this object.

    Mandatory fields
    ----------------
    stats:
        Ordered stat registry (``SportStatRegistry``).  Drives the loop's
        target set, the gate's feature-bundle routing, and the decision
        engine's stat-sigma defaults.
    clock:
        Game-clock specification (``GameClockConfig``).  Drives period
        lengths, remaining-fraction math, snapshot labels, and time-bucket
        breakpoints.
    roster:
        Roster specification (``RosterConfig``).  Drives on-field counts,
        foul-out limits, position taxonomy, and season-shrinkage denominators.
    game_state:
        Game-state threshold specification (``GameStateConfig``).  Drives
        blowout/clutch/garbage detection and the universal win-probability
        model's sigma parameter.
    pbp_mapper:
        Play-by-play mapper protocol (``PBPEventMapper``).  Maps raw league
        events to the kernel's canonical event set.  Required for any sport
        that supplies PBP data; for market-only sports a lightweight stub is
        acceptable.
    league_client:
        League data client protocol (``LeagueClient``).  Provides schedules,
        box scores, PBP, rosters, gamelogs, and injury feeds.
    entities:
        Entity-resolution registry protocol (``EntityRegistry``).  Resolves
        team tokens, player tokens, game IDs, and sportsbook aliases.  Raises
        on unrecognised tokens — no guessing.
    source_tiers:
        Fusion-layer tier labels.  ``{source_name: priority_int}`` where a
        HIGHER integer means HIGHER priority (the stat reconciler picks the
        highest-tier observed value when sources disagree).
        Example (NBA)::

            {"cdn_livedata": 4, "stats_api": 3, "bbref": 2, "broadcast_cv": 1}

    atlas_schema:
        Intelligence-vault section catalog (``AtlasSchema``).  Used by
        ``kernel/loop/error_miner.py`` to propose atlas sections for
        systematic residuals.  An empty ``AtlasSchema`` is the valid
        launch state for new sports.

    Optional / capability-subset fields
    ------------------------------------
    court:
        Playing-surface geometry (``CourtConfig``).  Required for CV/spatial
        modules.  ``None`` for market-only sports or sports without broadcast
        video tracking.
    speed:
        Movement-speed thresholds (``SpeedConfig``).  Required for
        ``kernel/spatial/pressure.py`` and ``kernel/spatial/space_control.py``.
        ``None`` for market-only sports and sports without positional tracking.
    dataset_builder:
        Domain-injected callable that builds the leak-safe full-model
        ``FeatureBundle`` for the honest gate.  NBA implementation wraps
        ``build_pergame_dataset()`` + ``feature_columns`` (101,770 rows).
        ``None`` causes the gate to DEFER (never false-SHIP) on any hypothesis
        that needs a bundle.
    trainer_hook:
        Domain-injected callable that triggers model retraining.  Used by
        ``kernel/loop/wiring.py`` when a hypothesis ships.  ``None`` disables
        auto-retrain (the loop still records verdicts; retraining is manual).
    artifact_root:
        Root path for all model/cache writes.  All kernel writes go under
        ``artifact_root / sport_id /`` — no kernel module embeds absolute
        sport-specific paths.  Defaults to ``Path("data")``.

    Parameters
    ----------
    stats : SportStatRegistry
    court : Optional[CourtConfig]
    clock : GameClockConfig
    roster : RosterConfig
    game_state : GameStateConfig
    speed : Optional[SpeedConfig]
    pbp_mapper : PBPEventMapper
    league_client : LeagueClient
    entities : EntityRegistry
    source_tiers : Mapping[str, int]
    atlas_schema : AtlasSchema
    dataset_builder : Optional[Any]
    trainer_hook : Optional[Any]
    artifact_root : Path
    """

    # ------------------------------------------------------------------
    # Mandatory fields
    # ------------------------------------------------------------------

    stats: SportStatRegistry
    clock: GameClockConfig
    roster: RosterConfig
    game_state: GameStateConfig
    pbp_mapper: PBPEventMapper
    league_client: LeagueClient
    entities: EntityRegistry
    source_tiers: Mapping[str, int]
    atlas_schema: AtlasSchema

    # ------------------------------------------------------------------
    # Optional capability-subset fields
    # ------------------------------------------------------------------

    court: Optional[CourtConfig] = None
    speed: Optional[SpeedConfig] = None
    dataset_builder: Optional[Any] = None
    trainer_hook: Optional[Any] = None
    artifact_root: Path = field(default_factory=lambda: Path("data"))

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def sport_id(self) -> str:
        """Canonical sport identifier, derived from the stat registry.

        Convenience shortcut for ``ctx.stats.sport_id`` — avoids callers
        needing to know that sport identity lives on the stat registry.

        Returns
        -------
        str
            E.g. ``"basketball_nba"``, ``"nfl"``, ``"soccer_epl"``.
        """
        return self.stats.sport_id

    @property
    def artifact_dir(self) -> Path:
        """Per-sport artifact directory: ``artifact_root / sport_id``.

        All model and cache writes from kernel modules MUST go under this
        path so that multi-sport installs do not collide.

        Returns
        -------
        Path
        """
        return self.artifact_root / self.sport_id

    def has_court(self) -> bool:
        """Return ``True`` if a ``CourtConfig`` is present.

        Use this guard before accessing ``ctx.court`` in kernel modules
        so that market-only sports raise a clear error instead of an
        ``AttributeError`` on ``None``.

        Returns
        -------
        bool
        """
        return self.court is not None

    def has_speed(self) -> bool:
        """Return ``True`` if a ``SpeedConfig`` is present.

        Returns
        -------
        bool
        """
        return self.speed is not None

    def has_dataset_builder(self) -> bool:
        """Return ``True`` if a dataset builder has been injected.

        When ``False``, the honest gate will DEFER (never SHIP or REJECT)
        for any hypothesis that requires a feature bundle.

        Returns
        -------
        bool
        """
        return self.dataset_builder is not None

    def has_trainer_hook(self) -> bool:
        """Return ``True`` if a trainer hook has been injected.

        When ``False``, the loop records verdicts but does not trigger
        automatic model retraining.

        Returns
        -------
        bool
        """
        return self.trainer_hook is not None
