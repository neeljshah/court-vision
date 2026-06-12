"""kernel.testing.domain_conformance_kit — DomainConformanceKit.

Bundles the kernel's conformance + invariant checks into ONE runnable kit
that any domain adapter can execute against its SportContext.

Import rules (R10 compliance)
------------------------------
This module imports ONLY from ``kernel.config.*``, ``kernel.testing.*``,
and the stdlib.  It NEVER contains a literal ``import domains`` or
``from domains`` statement.

Usage
-----
::

    from kernel.testing.domain_conformance_kit import DomainConformanceKit
    from kernel.testing.fixtures import make_toyball_context

    kit = DomainConformanceKit(make_toyball_context())
    results = kit.run_all()
    print(kit.summary(results))
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Dict

from kernel.config.context import SportContext
from kernel.config.entities import EntityRegistry
from kernel.config.pbp import LeagueClient, PBPEventMapper
from kernel.config.stats import SportStatRegistry
from kernel.testing.conformance import check_sport_context


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

class CheckStatus(str, enum.Enum):
    PASS = "PASS"
    SKIP = "SKIP"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Result:
    """Outcome of a single kit check.

    Parameters
    ----------
    status:
        One of PASS, SKIP, or FAIL.
    message:
        Human-readable explanation.  For PASS: brief confirmation.
        For SKIP: *reason* the check is deferred (never fakes a PASS).
        For FAIL: description of the violation(s).
    """

    status: CheckStatus
    message: str

    def __str__(self) -> str:
        return f"[{self.status.value}] {self.message}"


# ---------------------------------------------------------------------------
# DomainConformanceKit
# ---------------------------------------------------------------------------

class DomainConformanceKit:
    """Kernel conformance + invariant checks bundled into a single runnable kit.

    Any domain adapter constructs this with its ``SportContext`` and calls
    ``run_all()`` to get a full diagnostic picture.

    The kit is **sport-blind**: it imports only ``kernel.config.*`` and
    ``kernel.testing.*``; no ``domains.*`` or ``src.*`` imports ever appear here.

    Checks
    ------
    check_context()
        Runs ``check_sport_context`` — validates all mandatory fields,
        loop_target tail, priced_order subset, clock/roster/game_state invariants.

    check_protocols()
        Verifies ``ctx.entities``, ``ctx.pbp_mapper``, and ``ctx.league_client``
        satisfy their respective ``runtime_checkable`` protocols via
        ``isinstance``.

    check_stat_ordering()
        Confirms that ``priced_order()`` is a subset of ``target_names()`` and
        that ``score_stat`` is registered in the stat registry.

    check_clock()
        Confirms timed sports have ``regulation_sec() > 0``; confirms untimed
        sports have ``clock.untimed=True`` with ``regulation_sec() == 0``.

    check_atlas()
        Confirms ``ctx.atlas_schema`` is present and its ``sport_id`` matches
        ``ctx.sport_id``.

    check_gate_wiring()
        Requires the P0-B baseline + a live honest gate corpus — returns SKIP
        with an honest reason rather than faking a PASS.

    Parameters
    ----------
    ctx:
        The ``SportContext`` instance to validate.
    """

    def __init__(self, ctx: SportContext) -> None:
        self._ctx = ctx

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_context(self) -> Result:
        """Run ``check_sport_context`` and surface any violations.

        Returns PASS when the list is empty, FAIL otherwise.
        """
        violations = check_sport_context(self._ctx)
        if violations:
            joined = "; ".join(violations)
            return Result(CheckStatus.FAIL, f"check_sport_context found {len(violations)} violation(s): {joined}")
        return Result(CheckStatus.PASS, "SportContext passes all field invariants")

    def check_protocols(self) -> Result:
        """Verify runtime_checkable protocol isinstance for all three adapters.

        Checks: EntityRegistry, PBPEventMapper, LeagueClient.
        """
        failures = []
        if not isinstance(self._ctx.entities, EntityRegistry):
            failures.append(
                f"ctx.entities ({type(self._ctx.entities).__name__}) does not satisfy EntityRegistry"
            )
        if not isinstance(self._ctx.pbp_mapper, PBPEventMapper):
            failures.append(
                f"ctx.pbp_mapper ({type(self._ctx.pbp_mapper).__name__}) does not satisfy PBPEventMapper"
            )
        if not isinstance(self._ctx.league_client, LeagueClient):
            failures.append(
                f"ctx.league_client ({type(self._ctx.league_client).__name__}) does not satisfy LeagueClient"
            )
        if failures:
            return Result(CheckStatus.FAIL, "; ".join(failures))
        return Result(CheckStatus.PASS, "EntityRegistry, PBPEventMapper, LeagueClient all satisfy their protocols")

    def check_stat_ordering(self) -> Result:
        """Confirm stat-registry ordering invariants.

        Verifies:
        - ``priced_order()`` ⊆ ``target_names()``
        - ``score_stat`` is in ``target_names()``
        - ``SportStatRegistry`` is non-empty
        """
        if not isinstance(self._ctx.stats, SportStatRegistry):
            return Result(
                CheckStatus.FAIL,
                f"ctx.stats is not a SportStatRegistry; got {type(self._ctx.stats).__name__}",
            )
        target_names = set(self._ctx.stats.target_names())
        if not target_names:
            return Result(CheckStatus.FAIL, "ctx.stats.target_names() is empty")

        priced = set(self._ctx.stats.priced_order())
        extra = priced - target_names
        if extra:
            return Result(
                CheckStatus.FAIL,
                f"priced_order() contains names absent from target_names(): {sorted(extra)}",
            )
        if self._ctx.stats.score_stat not in target_names:
            return Result(
                CheckStatus.FAIL,
                f"score_stat={self._ctx.stats.score_stat!r} is not in target_names() {sorted(target_names)}",
            )
        return Result(
            CheckStatus.PASS,
            f"Stat ordering valid: {len(target_names)} target(s), "
            f"{len(priced)} priced, score_stat={self._ctx.stats.score_stat!r}",
        )

    def check_clock(self) -> Result:
        """Confirm clock invariants for timed and untimed sports.

        Timed: ``regulation_sec() > 0``.
        Untimed: ``clock.untimed=True`` and ``regulation_sec() == 0``.
        """
        clock = self._ctx.clock
        reg = clock.regulation_sec()
        if clock.untimed:
            if reg != 0:
                return Result(
                    CheckStatus.FAIL,
                    f"Untimed sport but regulation_sec()={reg} (expected 0)",
                )
            return Result(
                CheckStatus.PASS,
                f"Untimed clock valid: n_periods={clock.n_periods}, period_len_sec=0",
            )
        else:
            if reg <= 0:
                return Result(
                    CheckStatus.FAIL,
                    f"Timed sport but regulation_sec()={reg} (expected > 0)",
                )
            return Result(
                CheckStatus.PASS,
                f"Timed clock valid: regulation_sec()={reg}s, n_periods={clock.n_periods}",
            )

    def check_atlas(self) -> Result:
        """Confirm atlas_schema is present and sport_id matches ctx.sport_id.

        An empty AtlasSchema is a valid launch state for new sports.
        """
        from kernel.config.atlas_schema import AtlasSchema  # local to avoid circular at module level

        schema = self._ctx.atlas_schema
        if not isinstance(schema, AtlasSchema):
            return Result(
                CheckStatus.FAIL,
                f"ctx.atlas_schema is not an AtlasSchema; got {type(schema).__name__}",
            )
        if schema.sport_id != self._ctx.sport_id:
            return Result(
                CheckStatus.FAIL,
                f"atlas_schema.sport_id={schema.sport_id!r} does not match ctx.sport_id={self._ctx.sport_id!r}",
            )
        return Result(
            CheckStatus.PASS,
            f"AtlasSchema valid: sport_id={schema.sport_id!r}, "
            f"{schema.player_section_count} player section(s), "
            f"{schema.team_section_count} team section(s)",
        )

    def check_gate_wiring(self) -> Result:
        """Requires a live honest gate corpus (P0-B baseline).

        This check CANNOT be run hermetically — it needs an honest gate corpus
        built from the domain's ``DatasetBuilder`` and a P0-B baseline golden
        snapshot.  Returning SKIP (not PASS) is the honest outcome; faking a
        PASS would violate the accuracy≠edge discipline.

        Returns
        -------
        Result
            Always SKIP with an explanatory reason.
        """
        return Result(
            CheckStatus.SKIP,
            "requires P0-B baseline / live gate: "
            "gate_wiring needs a DatasetBuilder corpus + golden snapshot; "
            "run tests/conformance/<sport>/ after Phase K1+ is complete",
        )

    # ------------------------------------------------------------------
    # Aggregate runner
    # ------------------------------------------------------------------

    def run_all(self) -> Dict[str, Result]:
        """Run all checks and return a mapping of check-name → Result.

        Checks that cannot run hermetically report SKIP (never PASS).

        Returns
        -------
        Dict[str, Result]
            Keys: ``"check_context"``, ``"check_protocols"``,
            ``"check_stat_ordering"``, ``"check_clock"``, ``"check_atlas"``,
            ``"check_gate_wiring"``.
        """
        return {
            "check_context": self.check_context(),
            "check_protocols": self.check_protocols(),
            "check_stat_ordering": self.check_stat_ordering(),
            "check_clock": self.check_clock(),
            "check_atlas": self.check_atlas(),
            "check_gate_wiring": self.check_gate_wiring(),
        }

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self, results: Dict[str, Result]) -> str:
        """Return a printable scorecard for *results*.

        Parameters
        ----------
        results:
            Mapping returned by ``run_all()``.

        Returns
        -------
        str
            Multi-line scorecard with per-check status and a footer tally.
        """
        lines = [f"DomainConformanceKit — sport_id={self._ctx.sport_id!r}"]
        lines.append("-" * 60)
        pass_n = skip_n = fail_n = 0
        for name, result in results.items():
            lines.append(f"  {name:<28} {result}")
            if result.status == CheckStatus.PASS:
                pass_n += 1
            elif result.status == CheckStatus.SKIP:
                skip_n += 1
            else:
                fail_n += 1
        lines.append("-" * 60)
        lines.append(f"  PASS={pass_n}  SKIP={skip_n}  FAIL={fail_n}")
        return "\n".join(lines)
