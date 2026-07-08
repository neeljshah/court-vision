"""cli -- run the relevance gate over every team-mappable claim family.

    python -m scripts.platformkit.intel_weighting.cli --sport nba

Prints an ASCII scoreboard (family / metric / n / brier_base / brier_cond /
delta / verdict) and upserts the weight ledger. Most rows are expected NULL or
UNTESTABLE -- that catalogue IS the deliverable. No dollar/edge output.
"""
from __future__ import annotations

import argparse
from typing import List

from scripts.platformkit.intel_query.claims_index import discover_families
from scripts.platformkit.intel_weighting.relevance_gate import GateResult, run_family
from scripts.platformkit.intel_weighting.weight_ledger import LEDGER, append_results

_SPORT_PREFIX = {"nba": "nba_", "mlb": "mlb_"}


def _families_for(sport: str) -> List[str]:
    prefix = _SPORT_PREFIX[sport]
    return [f for f in discover_families() if f.startswith(prefix)]


def run(sport: str) -> List[GateResult]:
    results: List[GateResult] = []
    for fam in _families_for(sport):
        try:
            results.extend(run_family(sport, fam))
        except Exception as exc:  # noqa: BLE001 -- one bad family must not sink the run
            results.append(GateResult(fam, sport, "-", "?", 0, 0.0, 0.0, 0.0, 0.0,
                                      1.0, "UNTESTABLE", [f"error: {exc}"]))
    return results


def _print_board(sport: str, results: List[GateResult]) -> None:
    print(f"\nintel_weighting scoreboard -- {sport.upper()} "
          f"(method=prior_season_claim_walkforward_v1; calibration only, no edge)")
    print("-" * 96)
    print(f"{'family':<26}{'metric':<22}{'n':>5}  {'brier_base':>10} {'brier_cond':>10} "
          f"{'delta':>9}  verdict")
    print("-" * 96)
    order = {"MATTERS": 0, "NULL": 1, "UNTESTABLE": 2}
    for g in sorted(results, key=lambda r: (order.get(r.verdict, 3), r.family, r.metric)):
        print(f"{g.family[:25]:<26}{g.metric[:21]:<22}{g.n_games:>5}  "
              f"{g.brier_base:>10.5f} {g.brier_cond:>10.5f} {g.delta:>+9.5f}  {g.verdict}")
    n_m = sum(1 for g in results if g.verdict == "MATTERS")
    n_n = sum(1 for g in results if g.verdict == "NULL")
    n_u = sum(1 for g in results if g.verdict == "UNTESTABLE")
    print("-" * 96)
    print(f"MATTERS={n_m}  NULL={n_n}  UNTESTABLE={n_u}   (honest nulls are wins)")


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="claim-relevance weighting scoreboard")
    ap.add_argument("--sport", default="nba", choices=sorted(_SPORT_PREFIX))
    ap.add_argument("--no-write", action="store_true", help="scoreboard only, skip ledger")
    args = ap.parse_args(argv)

    results = run(args.sport)
    _print_board(args.sport, results)
    if not args.no_write:
        path = append_results(results)
        print(f"\nledger -> {path}")
    else:
        print(f"\n(--no-write; ledger at {LEDGER} untouched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
