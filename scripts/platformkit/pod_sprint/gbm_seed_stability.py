"""Seed-stability check for the NBA ML GBM sweep result.

The wide sweep reported Brier 0.2065 at seed 0.  A single-seed number can
be a seed artifact -- rerun the FULL pipeline (hyperparam selection +
walk-forward folds) at 4 seeds and report the spread.  Honest reading:
if the spread is wide, the "improvement" over the 6-config baseline grid
is partly noise and the artifact says so.

CLI: python -m scripts.platformkit.pod_sprint.gbm_seed_stability
"""
from __future__ import annotations

import json

from scripts.platformkit.models import gbm_nba_ml as g
from scripts.platformkit.pod_sprint.gbm_sweep import WIDE_GRID

SEEDS = (0, 1, 2, 3)
_OUT = g._REPO / "data" / "domains" / "nba" / "gbm_ml_seed_stability.json"


def main() -> int:
    g._GRID = WIDE_GRID
    g._MODEL_OUT = g._REPO / "data" / "models" / "nba_ml_gbm_seedcheck.json"
    rows = []
    for seed in SEEDS:
        g._SEED = seed
        rep = g.run()
        if rep.get("status") != "ok":
            print(f"seed {seed}: {rep.get('status')}")
            continue
        rows.append({"seed": seed, "brier_gbm": rep["brier_gbm"],
                     "brier_close": rep["brier_close"],
                     "chosen": rep["chosen_hyperparams"],
                     "verdict": rep["verdict"].split(":")[0]})
        print(f"seed {seed}: brier={rep['brier_gbm']} "
              f"chosen={rep['chosen_hyperparams']}")
    if not rows:
        print("no seed completed")
        return 1
    briers = [r["brier_gbm"] for r in rows]
    spread = round(max(briers) - min(briers), 4)
    out = {
        "seeds": rows, "brier_min": min(briers), "brier_max": max(briers),
        "brier_spread": spread, "edge_claimed": False,
        "honest_note": (
            "Full-pipeline rerun (selection+folds) per seed. A spread "
            "comparable to the sweep-vs-baseline delta (-0.0293) would mean "
            "the improvement is partly seed noise -- report it as such."),
    }
    _OUT.write_text(json.dumps(out, indent=1))
    print(f"spread across seeds: {spread} (sweep-vs-baseline delta was -0.0293)")
    print(f"artifact -> {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
