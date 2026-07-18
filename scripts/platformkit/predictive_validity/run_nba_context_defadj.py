"""CLI: run the nba_context_shooting_defadj predictive-validity test, write
the artifact, stamp the verdict into the claims family's validation sidecar.

    python -m scripts.platformkit.predictive_validity.run_nba_context_defadj [--forward-games 20]

Fails closed (clean message, exit 0, NO artifact written) when
player_boxscores.parquet is absent -- the expected path in this isolated
worktree (data/ is gitignored and absent here); real-data smokes run
post-merge against the real corpus.
"""
from __future__ import annotations

import argparse

from scripts.platformkit.intel_validation.nba_context_defadj_asof import (
    BOXSCORE_PATH,
    load_raw_boxscores,
)
from scripts.platformkit.predictive_validity.artifacts import (
    stamp_validation,
    write_predictive_validity_artifact,
)
from scripts.platformkit.predictive_validity.harness import run_metric_test
from scripts.platformkit.predictive_validity.nba_context_defadj_adapters import (
    FORWARD_GAMES,
    defadj_ts_test,
)


def run(forward_games: int = FORWARD_GAMES) -> list[dict]:
    try:
        box = load_raw_boxscores()
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"NO_DATA: {BOXSCORE_PATH} unavailable ({exc}); "
              f"predictive_validity run skipped, no artifact written.")
        return []

    test = defadj_ts_test(box, forward_games=forward_games)
    result = run_metric_test(test)
    path = write_predictive_validity_artifact(result)
    stamp_validation(result["family"], result["metric_name"], result["verdict"],
                      result["mean_rho_metric"], result["bootstrap_delta_ci"], result["n_folds"])
    print(f"wrote -> {path}")
    print(f"{result['family']}: {result['metric_name']} verdict={result['verdict']} "
          f"n_folds={result['n_folds']} mean_rho_metric={result['mean_rho_metric']:.4f}")
    return [result]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="NBA context-shooting defense-adjusted predictive-validity test")
    ap.add_argument("--forward-games", type=int, default=FORWARD_GAMES)
    args = ap.parse_args()
    run(forward_games=args.forward_games)
