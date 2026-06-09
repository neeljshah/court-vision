"""exp_atlas_residual.py — do the unwired ATLAS features explain OOF residual?

The user's hypothesis: the prop model isn't using the rich atlas intelligence.
Test it directly. Atlas files are one-row-per-player SEASON aggregates, so they
are player-constant and (being full-season) LEAK-PRONE — which makes this a
CONSERVATIVE test: a leaky feature would tend to HELP, so if these do NOT reduce
held-out residual MAE, they genuinely carry no usable orthogonal signal.

PTS: usage_role + scoring_creation;  REB: rebounding_profile + usage_role.
GPU XGB; touches no production model.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

_ROOT = Path(__file__).resolve().parent.parent
OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
ATLAS = _ROOT / "data" / "cache"
SPLIT = "2026-02-15"


def atlas_feats(names):
    df = None
    for nm in names:
        a = pd.read_parquet(ATLAS / f"atlas_player_{nm}.parquet")
        nums = [c for c in a.columns
                if a[c].dtype.kind in "fi" and c not in ("player_id", "n")]
        a = a[["player_id"] + nums].rename(columns={c: f"{nm}__{c}" for c in nums})
        df = a if df is None else df.merge(a, on="player_id", how="outer")
    return df


def main():
    oof = pd.read_parquet(OOF)
    oof = oof[oof["game_date"].astype(str) >= "2025-10-01"].copy()
    oof["date"] = oof["game_date"].astype(str).str[:10]

    for stat, names in (("pts", ["usage_role", "scoring_creation"]),
                        ("reb", ["rebounding_profile", "usage_role"])):
        feats_df = atlas_feats(names)
        fcols = [c for c in feats_df.columns if c != "player_id"]
        d = oof[oof["stat"] == stat].merge(feats_df, on="player_id", how="inner")
        d["resid"] = d["actual"] - d["oof_pred"]
        tr = d[d["date"] < SPLIT]; te = d[d["date"] >= SPLIT]
        if len(te) < 200:
            print(f"[{stat}] too few test rows ({len(te)})"); continue
        params = {"objective": "reg:absoluteerror", "max_depth": 4, "eta": 0.03,
                  "subsample": 0.8, "colsample_bytree": 0.8,
                  "device": "cuda", "tree_method": "hist"}
        try:
            bst = xgb.train(params, xgb.DMatrix(tr[fcols], label=tr["resid"]),
                            num_boost_round=300)
        except Exception as exc:
            print(f"[cuda->cpu {exc}]"); params["device"] = "cpu"
            bst = xgb.train(params, xgb.DMatrix(tr[fcols], label=tr["resid"]),
                            num_boost_round=300)
        corr = bst.predict(xgb.DMatrix(te[fcols]))
        base = te["resid"].abs().mean()
        full = (te["resid"].values - corr).__abs__().mean()
        half = (te["resid"].values - 0.5 * corr).__abs__().mean()
        print(f"\n{stat.upper()} atlas={names} (n_feat={len(fcols)}, "
              f"train={len(tr):,}, test={len(te):,}):")
        print(f"  OOF MAE                : {base:.4f}")
        print(f"  OOF + atlas correction : {full:.4f}  ({(base-full)/base*100:+.2f}%)  [leak-prone]")
        print(f"  OOF + 0.5x (damped)    : {half:.4f}  ({(base-half)/base*100:+.2f}%)")
        imp = sorted(bst.get_score(importance_type="gain").items(),
                     key=lambda kv: -kv[1])[:6]
        print(f"  top gain: {', '.join(f'{k.split(chr(95)+chr(95))[-1]}={v:.0f}' for k,v in imp)}")


if __name__ == "__main__":
    sys.exit(main())
