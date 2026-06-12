"""tests/kernel/test_domain_conformance_kit.py — DomainConformanceKit test suite.

Hermetic, offline.  Uses only kernel.testing.* fixtures — no domains/src import.

Test plan
---------
1. Toyball (timed) context → all implemented checks PASS, gate_wiring = SKIP.
2. Toyball_untimed context → same contract.
3. Deliberately broken contexts → the relevant individual check FAIL; others unaffected.
4. Structural invariant: no Result for a SKIP-worthy check ever has status PASS.
5. run_all() returns all 6 expected check names.
6. summary() contains PASS/SKIP/FAIL counts; never shows PASS for gate_wiring.
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, Mapping, Optional

import pytest

from kernel.config.atlas_schema import AtlasSchema
from kernel.config.clock import GameClockConfig
from kernel.config.context import SportContext
from kernel.config.entities import EntityRegistry
from kernel.config.game_state import GameStateConfig
from kernel.config.pbp import CanonicalEvent, CanonicalEventKind, LeagueClient, PBPEventMapper
from kernel.config.roster import PositionSchema, RosterConfig
from kernel.config.stats import SportStatRegistry, StatSpec
from kernel.testing.domain_conformance_kit import CheckStatus, DomainConformanceKit, Result
from kernel.testing.fixtures import make_toyball_context, make_toyball_untimed_context


# ---------------------------------------------------------------------------
# Helpers — expected check names
# ---------------------------------------------------------------------------

_EXPECTED_CHECKS = {
    "check_context",
    "check_protocols",
    "check_stat_ordering",
    "check_clock",
    "check_atlas",
    "check_gate_wiring",
}

# Checks that are SKIP-worthy by design (require live gate / P0-B baseline)
_SKIP_WORTHY = {"check_gate_wiring"}

# Checks that should PASS on a valid context
_PASS_WORTHY = _EXPECTED_CHECKS - _SKIP_WORTHY


# ---------------------------------------------------------------------------
# Minimal broken-context builders
# ---------------------------------------------------------------------------

class _BadEntityRegistry:
    """Does NOT implement resolve_team / resolve_player — fails protocol."""

    sport_id: str = "toyball"

    # Missing: resolve_team, resolve_player, parse_game_id, season_of,
    #          entity_key, book_aliases — deliberately incomplete.


class _GoodEntityRegistry:
    """Minimal valid EntityRegistry for use in broken-context helpers."""

    sport_id: str = "toyball"

    def resolve_team(self, token: str) -> str:
        if token != "HOME" and token != "AWAY":
            raise KeyError(token)
        return token

    def resolve_player(self, token: Any) -> str:
        return str(token)

    def parse_game_id(self, game_id: str) -> dict:
        return {"season": "2025-26", "kind": "regular", "seq": 1}

    def season_of(self, d: Any) -> str:
        return "2025-26"

    def entity_key(self, kind: str, ident: Any) -> str:
        return f"{kind}:{ident}"

    def book_aliases(self) -> Mapping[str, str]:
        return {}


class _GoodPBPMapper:
    def to_canonical(self, raw_event: Any) -> CanonicalEvent:
        return CanonicalEvent(kind=CanonicalEventKind.OTHER, ts_game_sec=0.0, period=1)

    def iter_game(self, game_id: str) -> Iterator[CanonicalEvent]:
        return iter([])

    def possession_side(self, event: CanonicalEvent) -> Optional[str]:
        return None


class _GoodLeagueClient:
    def get_schedule(self, season: str) -> Any:
        return []

    def get_box_score(self, game_id: str) -> Any:
        return {}

    def get_pbp(self, game_id: str) -> Any:
        return []

    def get_roster(self, team_id: str, season: str) -> Any:
        return []

    def get_player_gamelog(self, player_id: str, season: str) -> Any:
        return []

    def get_availability(self, player_id: str, game_id: str) -> Any:
        return "active"


def _make_base_valid_context(sport_id: str = "toyball") -> SportContext:
    """Return a minimal valid context we can mutate via replacement."""
    stats = {
        "score": StatSpec(name="score", kind="count", display="Score", sigma_default=5.0),
        "assists": StatSpec(name="assists", kind="count", display="Assists", sigma_default=2.0),
    }
    return SportContext(
        stats=SportStatRegistry(
            sport_id=sport_id,
            stats=stats,
            box_score_mapping={"SCR": "score", "AST": "assists"},
            score_stat="score",
            minutes_equiv="minutes",
        ),
        clock=GameClockConfig(
            n_periods=2,
            period_len_sec=600,
            ot_len_sec=300,
            untimed=False,
        ),
        roster=RosterConfig(
            on_field_count=5,
            roster_size=10,
            season_length_games=20,
            positions=PositionSchema(positions=("F", "M", "D", "G", "U")),
        ),
        game_state=GameStateConfig(
            blowout_margin=10.0,
            clutch_margin=3.0,
            clutch_remaining_sec=120.0,
            garbage_margin=15.0,
            competitive_margin=8.0,
            final_margin_sigma=5.0,
            winprob_promotion_period=2,
            legacy_overrides={},
        ),
        pbp_mapper=_GoodPBPMapper(),
        league_client=_GoodLeagueClient(),
        entities=_GoodEntityRegistry(),
        source_tiers={"toy_feed": 1},
        atlas_schema=AtlasSchema(sport_id=sport_id, player_sections=("scoring",)),
    )


# ---------------------------------------------------------------------------
# 1. Toyball timed context — all implemented checks PASS, gate_wiring SKIP
# ---------------------------------------------------------------------------

class TestToyballTimed:
    """Valid timed context from fixtures must yield all PASS + gate_wiring SKIP."""

    def setup_method(self) -> None:
        ctx = make_toyball_context()
        self.kit = DomainConformanceKit(ctx)
        self.results: Dict[str, Result] = self.kit.run_all()

    def test_all_expected_checks_present(self) -> None:
        assert set(self.results.keys()) == _EXPECTED_CHECKS

    def test_pass_worthy_checks_pass(self) -> None:
        for name in _PASS_WORTHY:
            assert self.results[name].status == CheckStatus.PASS, (
                f"Expected PASS for {name!r}; got {self.results[name]}"
            )

    def test_skip_worthy_checks_skip_not_pass(self) -> None:
        for name in _SKIP_WORTHY:
            result = self.results[name]
            assert result.status == CheckStatus.SKIP, (
                f"Expected SKIP for {name!r}; got {result}"
            )

    def test_gate_wiring_message_mentions_p0b(self) -> None:
        msg = self.results["check_gate_wiring"].message.lower()
        assert "p0-b" in msg or "baseline" in msg, (
            f"gate_wiring SKIP message should mention P0-B baseline; got: {msg!r}"
        )

    def test_no_skip_worthy_check_fakes_pass(self) -> None:
        """Structural invariant: gate_wiring must never report PASS."""
        for name in _SKIP_WORTHY:
            assert self.results[name].status != CheckStatus.PASS, (
                f"SKIP-worthy check {name!r} must never report PASS (faking a PASS)"
            )

    def test_summary_contains_tallies(self) -> None:
        summary = self.kit.summary(self.results)
        assert "PASS=" in summary
        assert "SKIP=" in summary
        assert "FAIL=" in summary


# ---------------------------------------------------------------------------
# 2. Toyball untimed context — same contract
# ---------------------------------------------------------------------------

class TestToyballUntimed:
    """Valid untimed context from fixtures must yield all PASS + gate_wiring SKIP."""

    def setup_method(self) -> None:
        ctx = make_toyball_untimed_context()
        self.kit = DomainConformanceKit(ctx)
        self.results: Dict[str, Result] = self.kit.run_all()

    def test_all_expected_checks_present(self) -> None:
        assert set(self.results.keys()) == _EXPECTED_CHECKS

    def test_pass_worthy_checks_pass(self) -> None:
        for name in _PASS_WORTHY:
            assert self.results[name].status == CheckStatus.PASS, (
                f"Expected PASS for {name!r}; got {self.results[name]}"
            )

    def test_skip_worthy_checks_skip_not_pass(self) -> None:
        for name in _SKIP_WORTHY:
            result = self.results[name]
            assert result.status == CheckStatus.SKIP, (
                f"Expected SKIP for {name!r}; got {result}"
            )

    def test_no_skip_worthy_check_fakes_pass(self) -> None:
        for name in _SKIP_WORTHY:
            assert self.results[name].status != CheckStatus.PASS

    def test_check_clock_notes_untimed(self) -> None:
        msg = self.results["check_clock"].message.lower()
        assert "untimed" in msg, f"check_clock should note untimed; got: {msg!r}"


# ---------------------------------------------------------------------------
# 3. Broken context → relevant check FAIL
# ---------------------------------------------------------------------------

class TestBrokenContexts:
    """Deliberate breakage → expected FAIL on the right check."""

    # -- 3a. Bad protocols (swap entity registry with an incomplete object)

    def test_check_protocols_fails_on_bad_entities(self) -> None:
        ctx = _make_base_valid_context()
        # Replace entities with an object that does NOT satisfy EntityRegistry
        broken = SportContext(
            stats=ctx.stats,
            clock=ctx.clock,
            roster=ctx.roster,
            game_state=ctx.game_state,
            pbp_mapper=ctx.pbp_mapper,
            league_client=ctx.league_client,
            entities=_BadEntityRegistry(),   # type: ignore[arg-type]
            source_tiers=ctx.source_tiers,
            atlas_schema=ctx.atlas_schema,
        )
        kit = DomainConformanceKit(broken)
        result = kit.check_protocols()
        assert result.status == CheckStatus.FAIL, f"Expected FAIL; got {result}"
        assert "entityregistry" in result.message.lower()

    # -- 3b. check_stat_ordering fails when score_stat is not registered

    def test_check_stat_ordering_fails_bad_score_stat(self) -> None:
        stats = {
            "score": StatSpec(name="score", kind="count", display="Score", sigma_default=5.0),
        }
        bad_registry = SportStatRegistry(
            sport_id="toyball",
            stats=stats,
            box_score_mapping={"SCR": "score"},
            score_stat="goals",   # 'goals' is not in stats
            minutes_equiv=None,
        )
        ctx = _make_base_valid_context()
        broken = SportContext(
            stats=bad_registry,
            clock=ctx.clock,
            roster=ctx.roster,
            game_state=ctx.game_state,
            pbp_mapper=ctx.pbp_mapper,
            league_client=ctx.league_client,
            entities=ctx.entities,
            source_tiers=ctx.source_tiers,
            atlas_schema=ctx.atlas_schema,
        )
        kit = DomainConformanceKit(broken)
        result = kit.check_stat_ordering()
        assert result.status == CheckStatus.FAIL, f"Expected FAIL; got {result}"
        assert "score_stat" in result.message.lower() or "goals" in result.message

    # -- 3c. check_clock fails for timed sport with zero regulation time

    def test_check_clock_fails_timed_zero_regulation(self) -> None:
        ctx = _make_base_valid_context()
        bad_clock = GameClockConfig(
            n_periods=0,
            period_len_sec=0,
            ot_len_sec=300,
            untimed=False,   # timed, but 0 periods → regulation_sec()=0
        )
        broken = SportContext(
            stats=ctx.stats,
            clock=bad_clock,
            roster=ctx.roster,
            game_state=ctx.game_state,
            pbp_mapper=ctx.pbp_mapper,
            league_client=ctx.league_client,
            entities=ctx.entities,
            source_tiers=ctx.source_tiers,
            atlas_schema=ctx.atlas_schema,
        )
        kit = DomainConformanceKit(broken)
        result = kit.check_clock()
        assert result.status == CheckStatus.FAIL, f"Expected FAIL; got {result}"

    # -- 3d. check_atlas fails when atlas sport_id mismatches

    def test_check_atlas_fails_mismatched_sport_id(self) -> None:
        ctx = _make_base_valid_context(sport_id="toyball")
        bad_atlas = AtlasSchema(sport_id="wrong_sport")
        broken = SportContext(
            stats=ctx.stats,
            clock=ctx.clock,
            roster=ctx.roster,
            game_state=ctx.game_state,
            pbp_mapper=ctx.pbp_mapper,
            league_client=ctx.league_client,
            entities=ctx.entities,
            source_tiers=ctx.source_tiers,
            atlas_schema=bad_atlas,
        )
        kit = DomainConformanceKit(broken)
        result = kit.check_atlas()
        assert result.status == CheckStatus.FAIL, f"Expected FAIL; got {result}"
        assert "wrong_sport" in result.message or "sport_id" in result.message.lower()

    # -- 3e. Breaking one check does not corrupt unrelated checks

    def test_other_checks_unaffected_when_clock_broken(self) -> None:
        ctx = _make_base_valid_context()
        bad_clock = GameClockConfig(n_periods=0, period_len_sec=0, ot_len_sec=300, untimed=False)
        broken = SportContext(
            stats=ctx.stats,
            clock=bad_clock,
            roster=ctx.roster,
            game_state=ctx.game_state,
            pbp_mapper=ctx.pbp_mapper,
            league_client=ctx.league_client,
            entities=ctx.entities,
            source_tiers=ctx.source_tiers,
            atlas_schema=ctx.atlas_schema,
        )
        kit = DomainConformanceKit(broken)
        results = kit.run_all()
        # clock broken → check_clock FAIL
        assert results["check_clock"].status == CheckStatus.FAIL
        # stat ordering and protocols should still PASS
        assert results["check_stat_ordering"].status == CheckStatus.PASS
        assert results["check_protocols"].status == CheckStatus.PASS


# ---------------------------------------------------------------------------
# 4. gate_wiring is ALWAYS SKIP — never fakes PASS regardless of context
# ---------------------------------------------------------------------------

class TestGateWiringNeverPass:
    """gate_wiring must report SKIP on any context, never PASS."""

    @pytest.mark.parametrize("factory", [make_toyball_context, make_toyball_untimed_context])
    def test_gate_wiring_skip_on_valid_contexts(self, factory: Any) -> None:
        ctx = factory()
        kit = DomainConformanceKit(ctx)
        result = kit.check_gate_wiring()
        assert result.status == CheckStatus.SKIP
        assert result.status != CheckStatus.PASS

    def test_gate_wiring_skip_on_broken_context(self) -> None:
        ctx = _make_base_valid_context()
        bad_clock = GameClockConfig(n_periods=0, period_len_sec=0, ot_len_sec=0, untimed=False)
        broken = SportContext(
            stats=ctx.stats,
            clock=bad_clock,
            roster=ctx.roster,
            game_state=ctx.game_state,
            pbp_mapper=ctx.pbp_mapper,
            league_client=ctx.league_client,
            entities=ctx.entities,
            source_tiers=ctx.source_tiers,
            atlas_schema=ctx.atlas_schema,
        )
        kit = DomainConformanceKit(broken)
        result = kit.check_gate_wiring()
        assert result.status == CheckStatus.SKIP
        assert result.status != CheckStatus.PASS


# ---------------------------------------------------------------------------
# 5. Result dataclass is frozen
# ---------------------------------------------------------------------------

def test_result_is_frozen() -> None:
    r = Result(status=CheckStatus.PASS, message="ok")
    with pytest.raises((AttributeError, TypeError)):
        r.status = CheckStatus.FAIL  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 6. summary() string output
# ---------------------------------------------------------------------------

def test_summary_output_format() -> None:
    ctx = make_toyball_context()
    kit = DomainConformanceKit(ctx)
    results = kit.run_all()
    summary = kit.summary(results)

    assert "toyball" in summary
    assert "PASS=" in summary
    assert "SKIP=" in summary
    assert "FAIL=" in summary
    # gate_wiring is SKIP so SKIP count >= 1
    skip_part = [line for line in summary.splitlines() if "SKIP=" in line][0]
    assert "SKIP=0" not in skip_part, "Expected at least one SKIP (gate_wiring)"
