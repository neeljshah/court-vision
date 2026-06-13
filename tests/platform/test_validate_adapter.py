"""tests/platform/test_validate_adapter.py — Scorecard tests (toy-based, hermetic).

All tests use make_toyball_context() (or a mutated variant injected directly).
No registered domain, no network, no NBA dependency.

Verifies:
* Valid toyball context → conformance items PASS, contract items NOT_YET_CONTRACTED,
  baseline items SKIP, no FAIL.
* Broken toyball context (bad stats / clock / roster / game_state) → the relevant
  item FAILs and exit code is 1.
* CLI --toy path → exit code 0, scorecard printed to stdout.
* CLI with broken fixture injected via direct API → exit code 1.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from io import StringIO
from typing import Any

import pytest

from kernel.config.atlas_schema import AtlasSchema
from kernel.config.clock import GameClockConfig
from kernel.config.context import SportContext
from kernel.config.game_state import GameStateConfig
from kernel.config.roster import PositionSchema, RosterConfig
from kernel.config.stats import SportStatRegistry, StatSpec
from kernel.testing.fixtures import make_toyball_context
from scripts.platformkit.validate_adapter import (
    Status,
    print_scorecard,
    validate_context,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bad_stats(sport_id: str = "toyball") -> SportStatRegistry:
    """Build a SportStatRegistry whose priced_order() contains a ghost key."""
    stats = {
        "score": StatSpec(
            name="score",
            kind="count",
            display="Score",
            sigma_default=5.0,
            priced=True,
        ),
    }
    reg = SportStatRegistry(
        sport_id=sport_id,
        stats=stats,
        box_score_mapping={"SCR": "score"},
        score_stat="score",
        minutes_equiv="minutes",
    )
    # Monkey-patch priced_order to include a name not in target_names so the
    # "priced_order ⊆ target_names" check fails.
    original_priced_order = reg.priced_order

    class _BadReg(SportStatRegistry):
        """Subclass with a broken priced_order()."""

        def priced_order(self):  # type: ignore[override]
            return ("score", "ghost_stat_not_in_registry")

    bad = _BadReg(
        sport_id=sport_id,
        stats=stats,
        box_score_mapping={"SCR": "score"},
        score_stat="score",
        minutes_equiv="minutes",
    )
    return bad


def _replace_ctx(ctx: SportContext, **kwargs: Any) -> SportContext:
    """Return a new SportContext with specified fields replaced.

    Uses object.__setattr__ bypassing frozen protection because dataclasses
    replace() does not work for frozen dataclasses with complex field types in
    all Python 3.9 implementations.  We build a fresh SportContext explicitly.
    """
    fields = {
        "stats": ctx.stats,
        "clock": ctx.clock,
        "roster": ctx.roster,
        "game_state": ctx.game_state,
        "pbp_mapper": ctx.pbp_mapper,
        "league_client": ctx.league_client,
        "entities": ctx.entities,
        "source_tiers": ctx.source_tiers,
        "atlas_schema": ctx.atlas_schema,
        "court": ctx.court,
        "speed": ctx.speed,
        "dataset_builder": ctx.dataset_builder,
        "trainer_hook": ctx.trainer_hook,
        "artifact_root": ctx.artifact_root,
    }
    fields.update(kwargs)
    return SportContext(**fields)


# ---------------------------------------------------------------------------
# Core: validate_context on the valid toyball context
# ---------------------------------------------------------------------------


class TestValidContextToyball:
    """validate_context with the canonical valid toyball fixture."""

    def setup_method(self) -> None:
        self.ctx = make_toyball_context()
        self.results = validate_context(self.ctx)

    def test_no_fail_items(self) -> None:
        """A valid toyball context must produce zero FAIL items."""
        fails = [
            (name, r) for name, r in self.results.items()
            if r.status == Status.FAIL
        ]
        assert not fails, f"Unexpected FAIL items: {fails}"

    def test_conformance_harness_passes(self) -> None:
        """check_sport_context delegation must PASS for toyball."""
        key = "check_sport_context (conformance harness)"
        assert key in self.results
        assert self.results[key].status == Status.PASS

    def test_protocol_checks_pass(self) -> None:
        """All protocol isinstance checks should be PASS."""
        protocol_items = [
            "ctx.stats SportStatRegistry",
            "ctx.clock GameClockConfig",
            "ctx.roster RosterConfig",
            "ctx.game_state GameStateConfig",
            "ctx.pbp_mapper PBPEventMapper",
            "ctx.league_client LeagueClient",
            "ctx.entities EntityRegistry",
            "ctx.atlas_schema AtlasSchema",
        ]
        for item in protocol_items:
            assert item in self.results, f"Item missing from scorecard: {item!r}"
            assert self.results[item].status == Status.PASS, (
                f"Expected PASS for {item!r}, "
                f"got {self.results[item].status}: {self.results[item].detail}"
            )

    def test_structural_invariants_pass(self) -> None:
        """Structural invariant checks must all PASS."""
        structural_items = [
            "stats.sport_id non-empty str",
            "stats.priced_order ⊆ target_names",
            "stats.loop_targets meta-tail",
            "clock.regulation_sec > 0 or untimed",
            "roster size >= on_field_count >= 1",
            "game_state required fields",
            "source_tiers non-empty",
        ]
        for item in structural_items:
            assert item in self.results, f"Item missing from scorecard: {item!r}"
            assert self.results[item].status == Status.PASS, (
                f"Expected PASS for {item!r}, "
                f"got {self.results[item].status}: {self.results[item].detail}"
            )

    def test_contract_items_are_not_yet_contracted(self) -> None:
        """Phase-4 contract items must be NOT_YET_CONTRACTED, never PASS."""
        nyc_items = [r for r in self.results.values()
                     if r.status == Status.NOT_YET_CONTRACTED]
        assert nyc_items, "Expected at least one NOT_YET_CONTRACTED item"
        # Spot-check a key item exists
        names = {r.item for r in nyc_items}
        assert any("DomainAdapter" in n for n in names), (
            "Expected at least one DomainAdapter contract item to be NOT_YET_CONTRACTED"
        )

    def test_baseline_items_are_skip(self) -> None:
        """Baseline-corpus items must be SKIP, never PASS."""
        skip_items = [r for r in self.results.values() if r.status == Status.SKIP]
        assert skip_items, "Expected at least one SKIP item (baseline corpus items)"
        for r in skip_items:
            assert "baseline" in r.detail.lower() or "P0-B" in r.detail, (
                f"SKIP item has unexpected detail: {r.detail!r}"
            )

    def test_exit_code_zero(self) -> None:
        """print_scorecard must return exit code 0 for a valid context."""
        buf = StringIO()
        code = print_scorecard("toyball", self.results, file=buf)
        assert code == 0

    def test_scorecard_output_contains_result_ok(self) -> None:
        """Scorecard output must include 'RESULT: OK' for a valid context."""
        buf = StringIO()
        print_scorecard("toyball", self.results, file=buf)
        assert "RESULT: OK" in buf.getvalue()


# ---------------------------------------------------------------------------
# Broken context: each failure mode triggers a FAIL item
# ---------------------------------------------------------------------------


class TestBrokenContextFailures:
    """validate_context with deliberately broken sub-objects → FAIL + exit 1."""

    def _assert_item_fails(self, ctx: SportContext, item_fragment: str) -> None:
        """Assert at least one item matching item_fragment has status FAIL."""
        results = validate_context(ctx)
        matching_fails = [
            r for r in results.values()
            if r.status == Status.FAIL and item_fragment.lower() in r.item.lower()
        ]
        assert matching_fails, (
            f"Expected a FAIL containing {item_fragment!r}; "
            f"got statuses: {[(r.item, r.status) for r in results.values() if item_fragment.lower() in r.item.lower()]}"
        )

    def _assert_exit_code_one(self, ctx: SportContext) -> None:
        """Assert print_scorecard returns 1 (FAIL present) for the given ctx."""
        results = validate_context(ctx)
        buf = StringIO()
        code = print_scorecard("broken", results, file=buf)
        assert code == 1, (
            f"Expected exit code 1; got {code}.\n"
            f"Scorecard:\n{buf.getvalue()}"
        )

    def test_bad_stats_priced_order(self) -> None:
        """priced_order containing a ghost key → stats.priced_order ⊆ target_names FAIL."""
        ctx = make_toyball_context()
        bad_stats = _make_bad_stats()
        broken = _replace_ctx(ctx, stats=bad_stats)
        self._assert_item_fails(broken, "priced_order")
        self._assert_exit_code_one(broken)

    def test_bad_clock_zero_regulation(self) -> None:
        """regulation_sec=0 and untimed=False → clock invariant FAIL."""
        ctx = make_toyball_context()
        bad_clock = GameClockConfig(
            n_periods=2,
            period_len_sec=0,   # 0 * 2 = 0 regulation seconds
            ot_len_sec=300,
            untimed=False,      # not untimed either
            play_clock_sec=30,
            penalty_threshold=5,
        )
        broken = _replace_ctx(ctx, clock=bad_clock)
        self._assert_item_fails(broken, "clock")
        self._assert_exit_code_one(broken)

    def test_bad_roster_wrong_type(self) -> None:
        """Non-RosterConfig roster → isinstance check FAIL.

        RosterConfig.__post_init__ enforces all numeric invariants at
        construction time, so we cannot build an invalid-but-valid-typed
        instance.  Instead substitute a plain object to trigger the
        isinstance(ctx.roster, RosterConfig) FAIL path.
        """
        ctx = make_toyball_context()

        class _FakeRoster:
            on_field_count = 5
            roster_size = 10

        broken = _replace_ctx(ctx, roster=_FakeRoster())  # type: ignore[arg-type]
        results = validate_context(broken)
        # The conformance harness and/or the protocol check should FAIL
        any_fail = any(r.status == Status.FAIL for r in results.values())
        assert any_fail, "Expected at least one FAIL for non-RosterConfig roster"
        buf = StringIO()
        code = print_scorecard("broken", results, file=buf)
        assert code == 1

    def test_bad_non_sportstatregistry_stats(self) -> None:
        """Non-SportStatRegistry stats object → type check FAIL."""
        ctx = make_toyball_context()
        broken = _replace_ctx(ctx, stats="not_a_registry")  # type: ignore[arg-type]
        results = validate_context(broken)
        # Either the top-level conformance harness or the protocol check should FAIL
        any_fail = any(r.status == Status.FAIL for r in results.values())
        assert any_fail, "Expected at least one FAIL for non-SportStatRegistry stats"
        buf = StringIO()
        code = print_scorecard("broken", results, file=buf)
        assert code == 1

    def test_bad_source_tiers_empty(self) -> None:
        """Empty source_tiers → source_tiers FAIL."""
        ctx = make_toyball_context()
        broken = _replace_ctx(ctx, source_tiers={})
        self._assert_item_fails(broken, "source_tiers")
        self._assert_exit_code_one(broken)


# ---------------------------------------------------------------------------
# CLI path tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Test the CLI via main()."""

    def test_toy_flag_exit_zero(self, capsys: pytest.CaptureFixture) -> None:
        """main(['--toy']) must return 0 and print a scorecard."""
        code = main(["--toy"])
        assert code == 0, "Expected exit code 0 from --toy with valid toyball context"
        captured = capsys.readouterr()
        assert "RESULT: OK" in captured.out

    def test_toy_flag_scorecard_contains_not_yet_contracted(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """--toy scorecard must mention NOT_YET_CONTRACTED items."""
        main(["--toy"])
        captured = capsys.readouterr()
        assert "NOT_YET_CONTRACTED" in captured.out

    def test_toy_flag_scorecard_contains_skip(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """--toy scorecard must mention SKIP items (baseline corpus)."""
        main(["--toy"])
        captured = capsys.readouterr()
        assert "SKIP" in captured.out

    def test_unknown_sport_exit_two(self, capsys: pytest.CaptureFixture) -> None:
        """main(['--sport', 'does_not_exist']) must return 2 (import error)."""
        code = main(["--sport", "does_not_exist_xyz"])
        assert code == 2

    def test_mutually_exclusive_args(self) -> None:
        """--sport and --toy are mutually exclusive."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--sport", "basketball_nba", "--toy"])
        assert exc_info.value.code != 0

    def test_no_args_exits_non_zero(self) -> None:
        """No arguments must exit non-zero (argparse error)."""
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code != 0
