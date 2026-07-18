"""CLI: run the MLB v1 predictive-validity menu, write artifacts, stamp
validation files, print an ASCII verdict table.

    python -m scripts.platformkit.predictive_validity.run_mlb [--forward-games 20]

Fails closed per-test (clean message, exit 0, NO artifact written for that
test) when its source parquet(s) are absent -- the expected path in this
isolated worktree (data/ is gitignored and absent here); real-data smokes run
post-merge against the real corpus. The two tests read DIFFERENT corpora
(savant_full__2023/2024 for framing, statcast_fuller__2022/2023 for putaway --
see mlb_adapters.py's CORPUS DEVIATION docstring), so one can run while the
other reports NO_DATA.
"""
from __future__ import annotations

import argparse

from scripts.platformkit.predictive_validity.artifacts import (
    stamp_validation,
    write_predictive_validity_artifact,
)
from scripts.platformkit.predictive_validity.harness import run_metric_test
from scripts.platformkit.predictive_validity.mlb_adapters import (
    FORWARD_GAMES,
    framing_test,
    load_framing_source,
    load_putaway_source,
    putaway_test,
)


def _print_table(results: list[dict]) -> None:
    header = f"{'family':<26}{'metric':<32}{'verdict':<20}{'n_folds':>8}{'rho_metric':>12}{'delta_ci_lo':>12}"
    print(header)
    print("-" * len(header))
    for r in results:
        delta_lo = r["bootstrap_delta_ci"].get("ci_lo") if r["bootstrap_delta_ci"] else float("nan")
        print(f"{r['family']:<26}{r['metric_name']:<32}{r['verdict']:<20}{r['n_folds']:>8}"
              f"{r['mean_rho_metric']:>12.4f}{delta_lo:>12.4f}")


def _build_tests(forward_games: int) -> list:
    tests = []
    try:
        taken = load_framing_source()
        tests.append(framing_test(taken, forward_games=forward_games))
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"NO_DATA: savant_full__2023/2024 unavailable ({exc}); "
              f"mlb_framing predictive_validity run skipped.")
    try:
        k = load_putaway_source()
        tests.append(putaway_test(k, forward_games=forward_games))
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"NO_DATA: statcast_fuller__2022/2023 unavailable ({exc}); "
              f"mlb_pitcher_putaway predictive_validity run skipped.")
    return tests


def run(forward_games: int = FORWARD_GAMES) -> list[dict]:
    tests = _build_tests(forward_games)
    if not tests:
        return []

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
    ap = argparse.ArgumentParser(description="MLB predictive-validity harness -- v1 menu")
    ap.add_argument("--forward-games", type=int, default=FORWARD_GAMES)
    args = ap.parse_args()
    run(forward_games=args.forward_games)
