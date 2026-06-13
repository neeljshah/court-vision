"""scripts/platformkit/validate_adapter.py — Adapter bootstrap scorecard.

CLI + importable validator that prints a PASS/SKIP/FAIL scorecard for a
domain adapter's SportContext.

Usage
-----
    python scripts/platformkit/validate_adapter.py --sport <sport_id>
    python scripts/platformkit/validate_adapter.py --toy

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
from typing import Dict, List, Optional

from kernel.config.context import SportContext
from kernel.testing.conformance import check_sport_context
from kernel.testing.fixtures import make_toyball_context

# Re-export public types so callers can do:
#   from scripts.platformkit.validate_adapter import Status, CheckResult
from scripts.platformkit.validate_adapter_types import (  # noqa: F401
    CheckResult,
    Status,
)

# Internal check helpers
from scripts.platformkit.validate_adapter_checks import (
    _baseline_skip_items,
    _check_clock_invariant,
    _check_game_state_fields,
    _check_protocol_types,
    _check_roster_invariant,
    _check_source_tiers,
    _check_stats_loop_tail,
    _check_stats_ordering,
    _check_stats_sport_id,
    _not_yet_contracted_items,
)


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
