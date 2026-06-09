"""train_pregame_calibrators.py — persist per-stat pregame calibration models.

Trains a covariate GBM that maps (base prediction + pre-game covariates) -> actual,
the calibration validated in scripts/calibration_gate1_test.py. For SHIPPING we
train on ALL available history (forward-serving on future games is leak-free).

Saved to data/models/pregame_cal/<stat>.json + meta.json. The serving module
(src/prediction/pregame_calibration.py) loads these. Only PTS is enabled by default
(it is the stat where the base model demonstrably loses to Vegas, so calibrating
toward the conditional mean cuts the bleed without erasing a real edge; AST is left
RAW on purpose — calibration destroys its +EV divergence).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import xgboost as xgb

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
# v2 enriched frame: adds minutes-shape + vacated-minutes (from the confirmed-
# inactives feed at serve time) + scoring rates. Validated +1.50% held-out vs the
# v1 simple frame's +0.33% (calibration_temporal_validation.py).
FRAME = _ROOT / "data" / "cache" / "calibration_frame_v2.parquet"
OUT_DIR = _ROOT / "data" / "models" / "pregame_cal"
COVS = ["pred", "l3_min", "l5_min", "l10_min", "std_min", "prev_min", "min_trend",
        "rest_days", "is_b2b", "is_home", "opp_pace", "opp_def",
        "vac_min", "vac_pts", "n_out", "l5_pts_pm", "l5_reb_pm",
        "month", "days_into_season"]
# Per-stat BLEND weight a: served = a*calibrated + (1-a)*base.
# Principle (validated multi-corpus leak-free in scripts/validate_calibration_multicorpus.py
# EX-7): calibrate FULLY where the base model loses to Vegas (PTS), stay RAW where it
# wins (AST — calibration kills its +7% edge), HALF-calibrate REB (robust at a=0.5 on
# 2/3 corpora), FULLY calibrate FG3M (a=1.0 justified on 2/3 corpora by EX-7 run;
# upgraded from a=0.5 which only won on 1 corpus). Stats absent serve raw (a=0).
BLEND = {"pts": 1.0, "reb": 0.5, "fg3m": 1.0}


def main():
    df = pd.read_parquet(FRAME).dropna(subset=COVS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {"covariates": COVS, "enabled": list(BLEND), "blend": BLEND, "models": {}}
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        s = df[df["stat"] == stat]
        if len(s) < 1000:
            continue
        params = {"objective": "reg:absoluteerror", "max_depth": 4, "eta": 0.03,
                  "subsample": 0.8, "colsample_bytree": 0.8, "device": "cuda",
                  "tree_method": "hist"}
        try:
            bst = xgb.train(params, xgb.DMatrix(s[COVS], label=s["actual"]),
                            num_boost_round=400)
        except Exception:
            params["device"] = "cpu"
            bst = xgb.train(params, xgb.DMatrix(s[COVS], label=s["actual"]),
                            num_boost_round=400)
        path = OUT_DIR / f"{stat}.json"
        bst.save_model(str(path))
        meta["models"][stat] = {"n_train": int(len(s)), "file": path.name}
        tag = f"  [BLEND a={BLEND[stat]}]" if stat in BLEND else ""
        print(f"  {stat}: trained on {len(s):,} rows -> {path.name}{tag}")
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nmeta -> {(OUT_DIR / 'meta.json').relative_to(_ROOT)}; blend={BLEND}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
