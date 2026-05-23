"""
calibrate_game_conformal_v3.py — Recompute conformal quantiles for v3 game models.

Loads the v3 holdout residuals from retrained models and fits split-conformal
prediction intervals against them.

Saves to: data/models/conformal_games_v3.json

Usage:
    conda run -n basketball_ai python scripts/calibrate_game_conformal_v3.py
"""

from __future__ import annotations

import json
import os
import sys
import pickle
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR   = os.path.join(PROJECT_DIR, "data", "models")
_OUTPUT_PATH = os.path.join(_MODEL_DIR, "conformal_games_v3.json")
_HOLDOUT_SEASON = "2024-25"


def _load_v3_holdout_preds():
    """
    Load v3 model files + scored_games holdout split, generate predictions.

    Uses the same offline overlay pattern as retrain_game_models_v3 — no live
    NBA API calls.  Ref and news features default to zeros for historical games.

    Returns dict of {output_name: (preds_array, actuals_array)}.
    """
    import numpy as np
    import pandas as pd
    import lightgbm as lgb
    from src.prediction.game_models import _fetch_scored_games, FEATURE_COLS as V2_FEATURE_COLS
    from src.features.v3_game_features import (
        _REF_DEFAULTS, _NEWS_DEFAULTS, _COACH_DEFAULTS,
        _sched_defaults, _form_defaults,
    )

    _SEASONS = ["2022-23", "2023-24", "2024-25"]

    # Load scored games
    rows = []
    for s in _SEASONS:
        rows.extend(_fetch_scored_games(s))
    df = pd.DataFrame(rows).dropna(subset=V2_FEATURE_COLS + ["game_total", "spread"])
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    df_ho = df[df["season"] == _HOLDOUT_SEASON].reset_index(drop=True)
    if len(df_ho) == 0:
        raise RuntimeError("No holdout data found for 2024-25")

    print(f"Holdout rows: {len(df_ho)}")

    # Pre-build ELO lookup (offline, reads season_games cache)
    elo_lkp: dict = {}
    try:
        from src.features.elo import compute_game_elo_lookup_v2
        elo_lkp = compute_game_elo_lookup_v2(_SEASONS)
        print(f"  ELO v2 lookup: {len(elo_lkp)} games")
    except Exception as e:
        print(f"  [warn] ELO: {e}")

    # Team ID lookup (static list)
    abbrev_to_id: dict = {}
    try:
        from nba_api.stats.static import teams as nba_teams_static
        abbrev_to_id = {t["abbreviation"]: t["id"] for t in nba_teams_static.get_teams()}
    except Exception:
        pass

    # Offline per-row overlay — mirrors _attach_v3_features in retrain_game_models_v3
    v3_rows = []
    n = len(df_ho)
    skip_form = {"team_form_games", "team_abbrev"}
    for i, (_, row) in enumerate(df_ho.iterrows()):
        home   = str(row.get("home_team", ""))
        away   = str(row.get("away_team", ""))
        gdate  = str(row.get("game_date", ""))
        season = str(row.get("season", _HOLDOUT_SEASON))
        gid    = str(row.get("game_id", ""))

        feats: dict = {}
        # Ref + News: zeros for historical rows (no live feed)
        feats.update(_REF_DEFAULTS)
        feats.update(_NEWS_DEFAULTS)

        htid = int(abbrev_to_id.get(home, 0))
        atid = int(abbrev_to_id.get(away, 0))
        for prefix, tid in [("home", htid), ("away", atid)]:
            try:
                if tid and gdate:
                    from src.features.schedule_pressure import get_team_schedule_features
                    raw = get_team_schedule_features(tid, gdate, season)
                    for k, v in raw.items():
                        if k not in {"team_id", "game_date"}:
                            feats[f"{prefix}_{k}"] = v
                else:
                    feats.update(_sched_defaults(prefix))
            except Exception:
                feats.update(_sched_defaults(prefix))

        for prefix, team in [("home", home), ("away", away)]:
            try:
                from src.features.team_form import get_team_form_features
                raw = get_team_form_features(team, gdate, season, 10)
                for k, v in raw.items():
                    if k in skip_form:
                        continue
                    feats[f"{prefix}_{k.replace('team_', '', 1)}"] = v
            except Exception:
                feats.update(_form_defaults(prefix, 10))

        try:
            from src.features.coach_features import get_coach_features
            cf = get_coach_features(home, away, season, gdate)
            feats.update({k: v for k, v in cf.items() if not isinstance(v, str)})
        except Exception:
            feats.update(_COACH_DEFAULTS)

        elo_entry = elo_lkp.get(gid, {})
        h_elo = float(elo_entry.get("home_elo", 1500.0))
        a_elo = float(elo_entry.get("away_elo", 1500.0))
        feats["v3_home_elo_v2"] = round(h_elo, 2)
        feats["v3_away_elo_v2"] = round(a_elo, 2)
        feats["v3_elo_diff_v2"] = round(h_elo - a_elo, 2)

        v3_rows.append(feats)
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{n} holdout rows processed ...")

    v3_df = pd.DataFrame(v3_rows, index=df_ho.index).fillna(0.0)
    v3_new_cols = list(v3_df.columns)
    for col in v3_new_cols:
        df_ho[col] = v3_df[col].values

    all_feature_cols = list(V2_FEATURE_COLS) + v3_new_cols
    for col in all_feature_cols:
        if col not in df_ho.columns:
            df_ho[col] = 0.0

    X_ho = df_ho[all_feature_cols].values.astype(np.float32)

    # Pace model uses a subset
    meta_path = os.path.join(_MODEL_DIR, "game_pace_v3_lgb_meta.pkl")
    if os.path.exists(meta_path):
        with open(meta_path, "rb") as f:
            pace_meta = pickle.load(f)
        pace_cols = pace_meta.get("pace_feature_cols", all_feature_cols)
    else:
        pace_cols = [c for c in all_feature_cols if c not in {"pace_avg", "pace_expectation"}]
    X_ho_pc = df_ho[[c for c in pace_cols if c in df_ho.columns]].values.astype(np.float32)

    outputs = {}
    blowout_margin = 15

    for name, model_file, is_cls, X_use, target_col in [
        ("total",      "game_total_v3_lgb.txt",      False, X_ho,    "game_total"),
        ("spread",     "game_spread_v3_lgb.txt",      False, X_ho,    "spread"),
        ("first_half", "game_first_half_v3_lgb.txt",  False, X_ho,
            ("first_half_actual" if "first_half_actual" in df_ho.columns else "first_half_proxy")),
        ("blowout_prob","game_blowout_v3_lgb.txt",    True,  X_ho,    "spread"),
        ("pace",       "game_pace_v3_lgb.txt",        False, X_ho_pc, "game_pace"),
    ]:
        path = os.path.join(_MODEL_DIR, model_file)
        if not os.path.exists(path):
            print(f"  [skip] {name}: model file not found ({path})")
            continue
        booster = lgb.Booster(model_file=path)
        raw_preds = booster.predict(X_use)

        if is_cls:
            # blowout: actuals are binary labels, preds are probabilities
            actuals = (np.abs(df_ho["spread"].values) > blowout_margin).astype(float)
            probs   = raw_preds
            outputs[name] = (probs, actuals)
        else:
            if target_col not in df_ho.columns:
                print(f"  [skip] {name}: target '{target_col}' not in holdout")
                continue
            actuals = df_ho[target_col].values.astype(float)
            outputs[name] = (raw_preds, actuals)

        print(f"  {name}: {len(actuals)} holdout preds")

    return outputs


def main():
    from src.prediction.conformal_games import GameConformalIntervals
    import numpy as np

    start_t = time.time()
    print("=" * 60)
    print("Calibrate Game Conformal Intervals — v3")
    print("=" * 60)

    outputs = _load_v3_holdout_preds()
    if not outputs:
        raise RuntimeError("No model outputs available — run retrain_game_models_v3.py first")

    preds_dict   = {k: v[0] for k, v in outputs.items()}
    actuals_dict = {k: v[1] for k, v in outputs.items()}

    gc = GameConformalIntervals(model_dir=os.path.join(PROJECT_DIR, "data", "models"))
    gc.fit(preds_dict, actuals_dict)
    gc.save(path=_OUTPUT_PATH)

    print(f"\nConformal quantiles saved -> {_OUTPUT_PATH}")

    # Print summary
    for key, qt in gc._quantiles.items():
        if "q10" in qt:
            print(f"  {key:<14}: q10={qt['q10']:+.2f}  q90={qt['q90']:+.2f}  n={qt['n']}")
        else:
            print(f"  {key:<14}: q90_res={qt.get('q90_residual', '?'):.4f}  n={qt['n']}")

    print(f"\nWall-clock: {round(time.time()-start_t,1):.1f}s")


if __name__ == "__main__":
    main()
