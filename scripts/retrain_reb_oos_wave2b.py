"""retrain_reb_oos_wave2b.py — Wave-2b OOS REB retrain with 109 features.

Retains the cycle-29 recipe (LGB-q50 quantile) but now uses the extended
109-feature set including dmatch_* + prof_* + bbref_extra. Writes to
data/models/oos_pre_playoffs/.
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import src.prediction.prop_pergame as pg

CUTOFF_DATE = "2024-04-21"
STAT = "reb"
OOS_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")


def main() -> None:
    os.makedirs(OOS_MODEL_DIR, exist_ok=True)
    t0 = time.time()

    original_build = pg.build_pergame_dataset
    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    n_holder: dict = {"n_all": 0, "n_pre": 0}

    def _filtered_build(gamelog_dir=None, **kw):
        rows, fcols = original_build(gamelog_dir, **kw)
        n_holder["n_all"] = len(rows)
        rows = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
        n_holder["n_pre"] = len(rows)
        return rows, fcols

    print(f"  Wave-2b OOS REB retrain (LGB-q50, cutoff < {CUTOFF_DATE})")
    pg.build_pergame_dataset = _filtered_build
    try:
        from src.prediction.prop_quantiles import train_quantile_models
        metrics = train_quantile_models(
            stats=[STAT],
            model_dir=OOS_MODEL_DIR,
        )
    finally:
        pg.build_pergame_dataset = original_build

    elapsed = time.time() - t0
    print(f"  train_quantile_models([{STAT}]) done in {elapsed:.1f}s")
    print(f"  n_all={n_holder['n_all']}  n_pre_cutoff={n_holder['n_pre']}")

    reb_m = metrics.get(STAT, {}) if isinstance(metrics, dict) else {}
    val_mae = reb_m.get("val_mae") or reb_m.get("val_pinball_q50")
    print(f"  REB val_mae (q50 pinball): {val_mae}")

    # Update _meta.json
    meta_path = os.path.join(OOS_MODEL_DIR, "_meta.json")
    all_meta: dict = {}
    if os.path.exists(meta_path):
        try:
            all_meta = json.load(open(meta_path, encoding="utf-8"))
        except Exception:
            all_meta = {}
    if "stats" not in all_meta:
        all_meta = {"stats": {}}

    all_meta["stats"][STAT] = {
        "cutoff_date": CUTOFF_DATE,
        "stat": STAT,
        "method": "lgb_q50",
        "val_mae": float(val_mae or 0.0),
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": float(elapsed),
        "n_total_rows": n_holder["n_all"],
        "n_pre_cutoff_rows": n_holder["n_pre"],
        "n_features": 109,
    }
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(all_meta, fh, indent=2)
    print(f"  Meta -> {meta_path}")
    print(f"\n  Summary: cutoff={CUTOFF_DATE}  n_pre={n_holder['n_pre']}  "
          f"val_mae={val_mae}  time={elapsed:.1f}s")


if __name__ == "__main__":
    main()
