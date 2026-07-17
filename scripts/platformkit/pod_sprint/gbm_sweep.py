"""Wider GPU hyperparameter sweep for the NBA ML GBM challenger.

Same corpus, same leak-free walk-forward folds, same honest gate (inner
80/20 train-pool selection + bootstrap CI vs the devigged close) as
scripts.platformkit.models.gbm_nba_ml -- only the grid is wider (36 configs,
tractable on the A4000).  Writes to ITS OWN artifacts so the baseline
6-config run is never clobbered, then prints an honest IMPROVED /
NO-IMPROVEMENT comparison vs the baseline artifact if one exists.

Promotion of any swept model stays a human decision.

CLI: python -m scripts.platformkit.pod_sprint.gbm_sweep
"""
from __future__ import annotations

import json

from scripts.platformkit.models import gbm_nba_ml as g

WIDE_GRID = [
    {"max_depth": d, "n_estimators": n, "learning_rate": lr}
    for d in (2, 3, 4, 5)
    for n in (100, 300, 600)
    for lr in (0.03, 0.06, 0.1)
]
_ARTIFACT = g._REPO / "data" / "domains" / "nba" / "gbm_ml_sweep_benchmark.json"
_MODEL_OUT = g._REPO / "data" / "models" / "nba_ml_gbm_sweep.json"
_BASELINE = g._REPO / "data" / "domains" / "nba" / "gbm_ml_benchmark.json"


def main() -> int:
    g._GRID = WIDE_GRID          # selection still happens on the inner train
    g._ARTIFACT = _ARTIFACT      # split only -- honesty unchanged, grid wider
    g._MODEL_OUT = _MODEL_OUT
    rep = g.run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n_overlap={rep.get('n_overlap')}")
        return 0
    rep["grid_note"] = f"wide sweep: {len(WIDE_GRID)} configs (baseline runs 6)"
    _ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    _ARTIFACT.write_text(json.dumps(rep, indent=2))
    print(f"=== NBA ML GBM wide sweep (n={rep['n_overlap']}, "
          f"device={rep['device_used']}, {len(WIDE_GRID)} configs) ===")
    print(f"  chosen: {rep['chosen_hyperparams']}")
    print(f"  Brier sweep={rep['brier_gbm']} close={rep['brier_close']}")
    print(f"  VERDICT vs close: {rep['verdict']}")
    if _BASELINE.exists():
        base = json.loads(_BASELINE.read_text())
        db = rep["brier_gbm"] - base.get("brier_gbm", float("nan"))
        tag = "IMPROVED" if db < 0 else "NO-IMPROVEMENT"
        print(f"  vs baseline grid: Brier {base.get('brier_gbm')} -> "
              f"{rep['brier_gbm']} ({tag}, delta {round(db, 4)})")
    else:
        print("  baseline artifact absent -- run gbm_nba_ml first for the comparison")
    print(f"artifact -> {_ARTIFACT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
