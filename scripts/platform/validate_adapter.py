"""scripts/platform/validate_adapter.py — Adapter bootstrap scorecard.

CLI + importable validator that prints a PASS/SKIP/FAIL scorecard for a
domain adapter's SportContext.

Usage
-----
    python scripts/platform/validate_adapter.py --sport <sport_id>
    python scripts/platform/validate_adapter.py --toy

The script exits non-zero if any item has status FAIL.

Honesty conventions
-------------------
* Items whose contract is not yet implemented (Phase-4 adapter-level checks)
  print status NOT_YET_CONTRACTED — they are never faked as PASS.
* Items that require a baseline corpus (P0-B baseline data) print SKIP with
  a reason string.
* The SportContext-era subset of §7/§8 checklist items that CAN be verified
  from a SportContext alone use check_sport_context() from
  kernel.testing.conformance plus local isinstance / protocol checks.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from kernel.config.context import SportContext
from kernel.config.stats import SportStatRegistry
from kernel.config.clock import GameClockConfig
from kernel.config.roster import RosterConfig
from kernel.config.game_state import GameStateConfig
from kernel.config.pbp import LeagueClient, PBPEventMapper
from kernel.config.entities import EntityRegistry
from kernel.config.atlas_schema import AtlasSchema
from kernel.testing.conformance import check_sport_context
from kernel.testing.fixtures import make_toyball_context


# ---------------------------------------------------------------------------
# Result enum
# ---------------------------------------------------------------------------


class Status(str, Enum):
    """Scorecard status codes."""
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    NOT_YET_CONTRACTED = "NOT_YET_CONTRACTED"


@dataclass
class CheckResult:
    """One scorecard row."""

    item: str
    status: Status
    detail: str = ""

    def __str__(self) -> str:
        pad = 40
        base = f"  [{self.status.value:<20}]  {self.item:<{pad}}"
        if self.detail:
            return f"{base}  # {self.detail}"
        return base


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


# ---------------------------------------------------------------------------
# Public API: validate_context
# ---------------------------------------------------------------------------


def validate_context(ctx: SportContext) -> Dict[str, CheckResult]:
    """Run the SportContext-era subset of the §7/§8 checklist.

    Parameters
    ----------
    ctx:
        The SportContext to validate.

    Returns
    -------
    Dict[str, CheckResult]
        Ordered mapping from item name to CheckResult.  Iterate in insertion
        order to print the scorecard in logical sequence.

    Notes
    -----
    * Items that CAN be verified from the SportContext print PASS or FAIL.
    * Items belonging to the not-yet-built Phase-4 DomainAdapter contract
      print NOT_YET_CONTRACTED — they are never faked as PASS.
    * Items that require a P0-B baseline corpus print SKIP.
    """
    results: Dict[str, CheckResult] = {}

    # --- Delegated comprehensive check via check_sport_context ---
    violations = check_sport_context(ctx)
    overall_item = "check_sport_context (conformance harness)"
    if violations:
        detail = "; ".join(violations)
        results[overall_item] = CheckResult(overall_item, Status.FAIL, detail)
    else:
        results[overall_item] = CheckResult(overall_item, Status.PASS)

    # --- Individual protocol checks ---
    for cr in _check_protocol_types(ctx):
        results[cr.item] = cr

    # --- Structural invariants ---
    for cr in [
        _check_stats_sport_id(ctx),
        _check_stats_ordering(ctx),
        _check_stats_loop_tail(ctx),
        _check_clock_invariant(ctx),
        _check_roster_invariant(ctx),
        _check_game_state_fields(ctx),
        _check_source_tiers(ctx),
    ]:
        results[cr.item] = cr

    # --- Phase-4 contract items: NOT_YET_CONTRACTED ---
    for cr in _not_yet_contracted_items():
        results[cr.item] = cr

    # --- Baseline-dependent items: SKIP ---
    for cr in _baseline_skip_items():
        results[cr.item] = cr

    return results


# ---------------------------------------------------------------------------
# Scorecard printer + exit-code logic
# ---------------------------------------------------------------------------


def print_scorecard(
    sport_label: str,
    results: Dict[str, CheckResult],
    *,
    file: object = None,
) -> int:
    """Print the scorecard and return exit code (0=all OK, 1=any FAIL).

    Parameters
    ----------
    sport_label:
        Human-readable label printed in the header.
    results:
        Output of ``validate_context``.
    file:
        Output stream.  Defaults to ``sys.stdout``.

    Returns
    -------
    int
        0 if no FAIL items, 1 otherwise.
    """
    if file is None:
        file = sys.stdout

    total = len(results)
    n_pass = sum(1 for r in results.values() if r.status == Status.PASS)
    n_fail = sum(1 for r in results.values() if r.status == Status.FAIL)
    n_skip = sum(1 for r in results.values() if r.status == Status.SKIP)
    n_nyc = sum(1 for r in results.values()
                if r.status == Status.NOT_YET_CONTRACTED)

    print(f"\n=== Adapter bootstrap scorecard: {sport_label} ===", file=file)
    print(f"  {n_pass} PASS  {n_fail} FAIL  "
          f"{n_skip} SKIP  {n_nyc} NOT_YET_CONTRACTED  ({total} total)\n",
          file=file)

    for cr in results.values():
        print(str(cr), file=file)

    print(file=file)
    if n_fail:
        print(f"RESULT: FAIL — {n_fail} item(s) failed.", file=file)
        return 1
    print("RESULT: OK (no FAIL items)", file=file)
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Adapter bootstrap scorecard for a domain sport.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  No FAIL items\n"
            "  1  At least one FAIL item\n"
            "  2  Invalid arguments or import error\n"
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--sport",
        metavar="SPORT_ID",
        help="Canonical sport_id to load via load_sport(). "
             "Example: basketball_nba",
    )
    group.add_argument(
        "--toy",
        action="store_true",
        help="Validate make_toyball_context() (no registered domain required).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI main function.

    Parameters
    ----------
    argv:
        Argument list; defaults to sys.argv[1:].

    Returns
    -------
    int
        Exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.toy:
        ctx = make_toyball_context()
        label = "toyball (toy fixture)"
    else:
        # Import here to avoid pulling in registry at module level
        from kernel.config.registry import load_sport  # noqa: PLC0415
        try:
            ctx = load_sport(args.sport)
        except (ValueError, KeyError) as exc:
            print(f"ERROR: cannot load sport {args.sport!r}: {exc}",
                  file=sys.stderr)
            return 2

        label = f"{args.sport} (registered domain)"

    results = validate_context(ctx)
    return print_scorecard(label, results)


if __name__ == "__main__":
    sys.exit(main())
