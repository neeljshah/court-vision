"""CLI: run the NBA v1 predictive-validity menu, write artifacts, stamp
validation files, print an ASCII verdict table.

    python -m scripts.platformkit.predictive_validity.run_nba [--forward-games 20]

Fails closed (clean message, exit 0, NO artifact written) when
player_boxscores.parquet is absent -- the expected path in this isolated
worktree (data/ is gitignored and absent here); real-data smokes run
post-merge against the real corpus.
"""
from __future__ import annotations

import argparse

from domains.basketball_nba.quality_indices import BOXSCORE_PATH, load_boxscores
from scripts.platformkit.predictive_validity.artifacts import (
    stamp_validation,
    write_predictive_validity_artifact,
)
from scripts.platformkit.predictive_validity.harness import run_metric_test
from scripts.platformkit.predictive_validity.nba_adapters import (
    FORWARD_GAMES,
    gravity_proxy_test,
    rest_adjusted_form_test,
    shooter_composite_v2_test,
)


def _print_table(results: list[dict]) -> None:
    header = f"{'family':<26}{'metric':<32}{'verdict':<20}{'n_folds':>8}{'rho_metric':>12}{'delta_ci_lo':>12}"
    print(header)
    print("-" * len(header))
    for r in results:
        delta_lo = r["bootstrap_delta_ci"].get("ci_lo") if r["bootstrap_delta_ci"] else float("nan")
        print(f"{r['family']:<26}{r['metric_name']:<32}{r['verdict']:<20}{r['n_folds']:>8}"
              f"{r['mean_rho_metric']:>12.4f}{delta_lo:>12.4f}")


def run(forward_games: int = FORWARD_GAMES) -> list[dict]:
    try:
        box = load_boxscores()
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"NO_DATA: {BOXSCORE_PATH} unavailable ({exc}); "
              f"predictive_validity run skipped, no artifact written.")
        return []

    tests = [
        gravity_proxy_test(box, forward_games=forward_games),
        rest_adjusted_form_test(box, forward_games=forward_games),
        shooter_composite_v2_test(box, forward_games=forward_games),
    ]
    results = []
    for test in tests:
        result = run_metric_test(test)
        path = write_predictive_validity_artifact(result)
        stamp_validation(result["family"], result["metric_name"], result["verdict"],
                          result["mean_rho_metric"], result["bootstrap_delta_ci"], result["n_folds"])
        print(f"wrote -> {path}")
        results.append(result)

    _print_table(results)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="NBA predictive-validity harness -- v1 menu")
    ap.add_argument("--forward-games", type=int, default=FORWARD_GAMES)
    args = ap.parse_args()
    run(forward_games=args.forward_games)
