"""scripts/platformkit/validate_adapter_checks.py — Individual check functions.

Internal helpers for validate_adapter.py.  Each function receives a
SportContext and returns one or more CheckResult objects.  Also contains the
static NOT_YET_CONTRACTED and SKIP item lists.

Not intended to be imported by callers outside scripts/platformkit/.
"""
from __future__ import annotations

from typing import List

from kernel.config.context import SportContext
from kernel.config.stats import SportStatRegistry
from kernel.config.clock import GameClockConfig
from kernel.config.roster import RosterConfig
from kernel.config.game_state import GameStateConfig
from kernel.config.pbp import LeagueClient, PBPEventMapper
from kernel.config.entities import EntityRegistry
from kernel.config.atlas_schema import AtlasSchema

from scripts.platformkit.validate_adapter_types import CheckResult, Status


# ---------------------------------------------------------------------------
# SportContext-era checks (what we CAN verify right now)
# ---------------------------------------------------------------------------


def _check_stats_ordering(ctx: SportContext) -> CheckResult:
    """§7 item 1 — stat ordering: priced_order() ⊆ target_names()."""
    item = "stats.priced_order ⊆ target_names"
    try:
        target_set = set(ctx.stats.target_names())
        extra = set(ctx.stats.priced_order()) - target_set
        if extra:
            return CheckResult(item, Status.FAIL, f"extra priced keys: {sorted(extra)}")
        return CheckResult(item, Status.PASS)
    except Exception as exc:  # noqa: BLE001
        return CheckResult(item, Status.FAIL, str(exc))


def _check_stats_loop_tail(ctx: SportContext) -> CheckResult:
    """§7 item 1 — loop_targets ends with the required meta-tail."""
    item = "stats.loop_targets meta-tail"
    required_tail = ("minutes", "total", "winprob", "usage", "sigma")
    try:
        lt = ctx.stats.loop_targets
        tail = lt[-len(required_tail):]
        if tail != required_tail:
            return CheckResult(item, Status.FAIL,
                               f"expected tail {required_tail!r}, got {tail!r}")
        return CheckResult(item, Status.PASS)
    except Exception as exc:  # noqa: BLE001
        return CheckResult(item, Status.FAIL, str(exc))


def _check_stats_sport_id(ctx: SportContext) -> CheckResult:
    """§7 item 1d — stats.sport_id is a non-empty string."""
    item = "stats.sport_id non-empty str"
    try:
        sid = ctx.stats.sport_id
        if not isinstance(sid, str) or not sid.strip():
            return CheckResult(item, Status.FAIL,
                               f"got {sid!r}")
        return CheckResult(item, Status.PASS)
    except Exception as exc:  # noqa: BLE001
        return CheckResult(item, Status.FAIL, str(exc))


def _check_protocol_types(ctx: SportContext) -> List[CheckResult]:
    """§7 items 2-4 — protocol isinstance checks for all mandatory sub-objects."""
    results: List[CheckResult] = []
    checks = [
        ("ctx.stats SportStatRegistry", ctx.stats, SportStatRegistry),
        ("ctx.clock GameClockConfig", ctx.clock, GameClockConfig),
        ("ctx.roster RosterConfig", ctx.roster, RosterConfig),
        ("ctx.game_state GameStateConfig", ctx.game_state, GameStateConfig),
        ("ctx.pbp_mapper PBPEventMapper", ctx.pbp_mapper, PBPEventMapper),
        ("ctx.league_client LeagueClient", ctx.league_client, LeagueClient),
        ("ctx.entities EntityRegistry", ctx.entities, EntityRegistry),
        ("ctx.atlas_schema AtlasSchema", ctx.atlas_schema, AtlasSchema),
    ]
    for item, obj, expected_type in checks:
        if isinstance(obj, expected_type):
            results.append(CheckResult(item, Status.PASS))
        else:
            results.append(CheckResult(
                item, Status.FAIL,
                f"expected {expected_type.__name__}, got {type(obj).__name__}",
            ))
    return results


def _check_clock_invariant(ctx: SportContext) -> CheckResult:
    """§7 clock — regulation_sec > 0 or clock.untimed is True."""
    item = "clock.regulation_sec > 0 or untimed"
    try:
        ok = ctx.clock.regulation_sec() > 0 or ctx.clock.untimed
        if ok:
            return CheckResult(item, Status.PASS)
        return CheckResult(item, Status.FAIL,
                           f"regulation_sec={ctx.clock.regulation_sec()} untimed={ctx.clock.untimed}")
    except Exception as exc:  # noqa: BLE001
        return CheckResult(item, Status.FAIL, str(exc))


def _check_roster_invariant(ctx: SportContext) -> CheckResult:
    """§7 roster — roster_size >= on_field_count >= 1."""
    item = "roster size >= on_field_count >= 1"
    try:
        r = ctx.roster
        if r.on_field_count < 1:
            return CheckResult(item, Status.FAIL,
                               f"on_field_count={r.on_field_count} < 1")
        if r.roster_size < r.on_field_count:
            return CheckResult(item, Status.FAIL,
                               f"roster_size={r.roster_size} < on_field_count={r.on_field_count}")
        return CheckResult(item, Status.PASS)
    except Exception as exc:  # noqa: BLE001
        return CheckResult(item, Status.FAIL, str(exc))


def _check_game_state_fields(ctx: SportContext) -> CheckResult:
    """§7 item 4 — GameStateConfig has all required fields."""
    item = "game_state required fields"
    required = (
        "blowout_margin", "clutch_margin", "clutch_remaining_sec",
        "garbage_margin", "competitive_margin", "final_margin_sigma",
        "winprob_promotion_period",
    )
    missing = [f for f in required if not hasattr(ctx.game_state, f)]
    if missing:
        return CheckResult(item, Status.FAIL, f"missing: {missing}")
    return CheckResult(item, Status.PASS)


def _check_source_tiers(ctx: SportContext) -> CheckResult:
    """source_tiers is a non-empty mapping of str→int."""
    item = "source_tiers non-empty"
    try:
        tiers = ctx.source_tiers
        if not tiers:
            return CheckResult(item, Status.FAIL, "source_tiers is empty")
        return CheckResult(item, Status.PASS)
    except Exception as exc:  # noqa: BLE001
        return CheckResult(item, Status.FAIL, str(exc))


# ---------------------------------------------------------------------------
# Phase-4 contract items (not yet implemented — honest NOT_YET_CONTRACTED)
# ---------------------------------------------------------------------------


def _not_yet_contracted_items() -> List[CheckResult]:
    """Items from §7/§8 that belong to the Phase-4 DomainAdapter contract.

    These checks CANNOT pass yet because the DomainAdapter ABC (kernel/domain/)
    does not exist.  They are listed so the scorecard is honest about gap coverage
    rather than silently skipping future requirements.
    """
    items = [
        "DomainAdapter.capabilities() → AdapterCapabilities",
        "DomainAdapter.stat_registry property present",
        "DomainAdapter.outcome_engine mode in {simulator,surrogate,market_only}",
        "DomainAdapter.market_source.capture_openers present",
        "joint_quality guard: joint_prob raises on independent joints",
        "entity round-trip: resolve_team(resolve_team(x).abbrev).team_uid stable",
        "PBP truncation-invariance across ≥5 replay games (§7 item 5)",
        "engine determinism: same seed → identical arrays (§7 item 6)",
        "marginal coherence: prob_over monotone in line (§7 item 7)",
        "CLV grading refused when has_opener_capture=False (§7 item 8)",
        "feature extractor leak guard: asof < game_date (§7 item 9)",
        "LeagueClient cache discipline: second call hits disk (§7 item 10)",
    ]
    return [CheckResult(item, Status.NOT_YET_CONTRACTED,
                        "requires Phase-4 DomainAdapter contract")
            for item in items]


# ---------------------------------------------------------------------------
# P0-B baseline items (require baseline corpus — skipped until available)
# ---------------------------------------------------------------------------


def _baseline_skip_items() -> List[CheckResult]:
    """Items from §8 that require a P0-B baseline corpus.

    The baseline corpus (≥2 seasons of settled predictions + closes) has not
    yet been established for any sport.  These items will be SKIP until a
    running baseline exists.
    """
    items = [
        "calibration reliability curve (§8 step 9)",
        "opener capture → CLV ledger accruing (§8 step 9)",
        "cross-season corpus ≥2 seasons (§8 step 10 — sets historical_seasons)",
        "gate verdict: surrogate vs Tier-M baseline on calibration+CLV",
    ]
    return [CheckResult(item, Status.SKIP, "needs P0-B baseline corpus")
            for item in items]
