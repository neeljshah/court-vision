"""CLI: run the nba_rest_context b2b-TS-drop-vs-zero predictive-validity
test, write the artifact, stamp the verdict into nba_rest_context_claims_
validation.json.

    python -m scripts.platformkit.predictive_validity.run_nba_rest_context [--forward-games 20]

Does NOT call harness.run_metric_test -- the zero/constant baseline is
undefined under Spearman rank-correlation (see nba_rest_context_adapter.py
docstring for why the two-arm bootstrap would crash), so this module
aggregates folds itself, reusing harness._build_fold/_bootstrap_single_rho/
_verdict directly (same primitives, same thresholds, just no two-arm call).

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
from scripts.platformkit.predictive_validity.harness import (
    _bootstrap_single_rho,
    _build_fold,
    _verdict,
)
from scripts.platformkit.predictive_validity.nba_rest_context_adapter import (
    FORWARD_GAMES,
    rest_context_b2b_drop_test,
)


def run_zero_baseline_test(test) -> dict:
    """Fold assembly identical to harness.run_metric_test, EXCEPT: no
    paired_bootstrap_delta call (undefined for a constant baseline -- see
    nba_rest_context_adapter.py). rho_metric_bootstrap doubles as the
    delta-vs-zero CI (delta = rho_metric - 0 = rho_metric); sign_holds counts
    folds where rho_metric > 0 directly, not via the (always-NaN) `delta`
    field _build_fold would otherwise compute against the constant arm."""
    folds = [_build_fold(test, c) for c in test.cutoffs]
    ok = [f for f in folds if f["status"] == "OK"]
    n_folds = len(ok)

    mean_rho_metric = float(sum(f["rho_metric"] for f in ok) / n_folds) if ok else float("nan")
    sign_holds = sum(1 for f in ok if f["rho_metric"] > 0)

    bootstrap_metric: dict = {}
    if n_folds >= 2:
        bootstrap_metric = _bootstrap_single_rho([f["table"] for f in ok], "metric_value", "outcome")

    verdict = _verdict(n_folds, bootstrap_metric, sign_holds)

    return {
        "family": test.family, "sport": test.sport,
        "metric_name": test.metric_name, "baseline_name": test.baseline_name,
        "verdict": verdict,
        "mean_rho_metric": mean_rho_metric, "mean_rho_baseline": 0.0,
        "rho_metric_bootstrap": bootstrap_metric,
        "bootstrap_delta_ci": bootstrap_metric,
        "sign_holds_folds": sign_holds, "n_folds": n_folds,
        "per_cutoff": [{k: v for k, v in f.items() if k != "table"} for f in folds],
        "forward_games": test.forward_games,
        "caveat": test.caveat,
    }


def run(forward_games: int = FORWARD_GAMES) -> list[dict]:
    try:
        box = load_boxscores()
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"NO_DATA: {BOXSCORE_PATH} unavailable ({exc}); "
              f"predictive_validity run skipped, no artifact written.")
        return []

    test = rest_context_b2b_drop_test(box, forward_games=forward_games)
    result = run_zero_baseline_test(test)
    path = write_predictive_validity_artifact(result)
    stamp_validation(result["family"], result["metric_name"], result["verdict"],
                      result["mean_rho_metric"], result["bootstrap_delta_ci"], result["n_folds"])
    print(f"wrote -> {path}")
    print(f"{result['family']}: {result['metric_name']} verdict={result['verdict']} "
          f"n_folds={result['n_folds']} mean_rho_metric={result['mean_rho_metric']:.4f}")
    return [result]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="NBA rest-context b2b-drop-vs-zero predictive-validity test")
    ap.add_argument("--forward-games", type=int, default=FORWARD_GAMES)
    args = ap.parse_args()
    run(forward_games=args.forward_games)
