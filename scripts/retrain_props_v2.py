"""
retrain_props_v2.py -- Retrain all 7 prop models on real per-game rolling features.

Data source  : data/nba/gamelog_full_{pid}_{season}.json for 2022-23, 2023-24, 2024-25
               Plus 2025-26 files when present (used for test/holdout only).
Features     : same _build_row() / _load_gamelogs() as prop_holdout.py
Train        : games < 2025-10-01  (all 3 completed seasons: 2022-23, 2023-24, 2024-25)
Test         : 2025-10-01 - 2026-01-01  (early 2025-26 games)
Validate     : 2026-01-01+  (2025-26 mid-season holdout)

Season resets: rolling averages reset at each season boundary so 2023-24 stats
               don't bleed into the first game of 2024-25.

Output
  data/models/props_{stat}_v2.json   -- new model (always saved)
  data/models/props_{stat}.json      -- overwritten if holdout R2 improves
  data/models/model_registry.json    -- updated with new metrics + needs_retrain=false

Usage
-----
    conda activate basketball_ai
    python scripts/retrain_props_v2.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score

# -- Paths ----------------------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_FEATS_JSON = os.path.join(PROJECT_DIR, "scripts", "validate", "_all_feats.json")
_REG_PATH   = os.path.join(_MODEL_DIR, "model_registry.json")

# -- Config ---------------------------------------------------------------------
_PROP_STATS   = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
# All games before 2025-10-01 are training (2022-23, 2023-24, 2024-25 completed seasons).
# Early 2025-26 games (Oct 2025 - Jan 2026) form the test set.
# 2026-01-01+ is the holdout / validation set.
_TRAIN_CUTOFF = datetime(2025, 10, 1)
_TEST_CUTOFF  = datetime(2026, 1, 1)
_BAYES_K     = 15
_ROLL_N      = 10
_MIN_PRIOR   = 3   # minimum prior games needed to build a feature row

# XGBoost hyperparameters (same as original, but trained on real data)
_XGB_PARAMS = {
    "n_estimators":     400,
    "max_depth":        5,
    "learning_rate":    0.05,
    "subsample":        0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 3,
    "reg_alpha":        0.1,
    "reg_lambda":       1.0,
    "random_state":     42,
    "n_jobs":           -1,
    "tree_method":      "hist",
}

# STL-specific params: more regularization for noisy count stat (MSE beats Poisson objective)
_XGB_PARAMS_STL = {
    "n_estimators":     200,
    "max_depth":        3,
    "learning_rate":    0.05,
    "subsample":        0.7,
    "colsample_bytree": 0.7,
    "min_child_weight": 8,
    "reg_alpha":        0.5,
    "reg_lambda":       3.0,
    "random_state":     42,
    "n_jobs":           -1,
    "tree_method":      "hist",
}


# -- Feature list --------------------------------------------------------------

def _load_all_feats() -> List[str]:
    if os.path.exists(_FEATS_JSON):
        return json.load(open(_FEATS_JSON))
    import ast
    src_path = os.path.join(PROJECT_DIR, "src", "prediction", "player_props.py")
    src = open(src_path, encoding="utf-8").read()
    m = re.search(r"_ALL_FEATS\s*=\s*(\[.*?\])", src, re.DOTALL)
    if m:
        return ast.literal_eval(m.group(1))
    raise RuntimeError("Cannot find _ALL_FEATS in player_props.py")


# -- Date parser ---------------------------------------------------------------

def _parse_date(s: str) -> Optional[datetime]:
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


# -- Gamelog loader ------------------------------------------------------------

def _load_gamelogs() -> Dict[int, List[dict]]:
    by_player: Dict[int, List[dict]] = defaultdict(list)
    # Load gamelogs for all available seasons -- pick up 2025-26 files if present
    files = glob.glob(os.path.join(_NBA_CACHE, "gamelog_full_*_????-??.json"))
    print(f"[retrain] Found {len(files)} gamelog files")
    for fpath in files:
        m = re.search(r"gamelog_full_(\d+)_(\d{4}-\d{2})\.json", os.path.basename(fpath))
        if not m:
            continue
        pid    = int(m.group(1))
        season = m.group(2)
        try:
            rows = json.load(open(fpath))
        except Exception:
            continue
        for r in rows:
            d = _parse_date(str(r.get("game_date", "")))
            if d is None:
                continue
            # Tag each row with its season so rolling averages can reset at season boundaries
            by_player[pid].append({**r, "_dt": d, "_season": season})
    for pid in by_player:
        by_player[pid].sort(key=lambda r: r["_dt"])
    return by_player


# -- Feature builder (mirrors prop_holdout.py exactly) -------------------------

def _avg(key: str, rows: List[dict]) -> float:
    vals = [float(r.get(key, 0) or 0) for r in rows]
    return sum(vals) / len(vals) if vals else 0.0


def _build_row(pid: int, prior: List[dict], all_feats: List[str]) -> dict:
    """Build one feature row from prior games; unknowns -> 0.0."""
    n_all  = len(prior)
    n_roll = min(_ROLL_N, n_all)
    roll   = prior[-n_roll:] if n_roll > 0 else []

    def _bayes(rv: float, sv: float) -> float:
        n = float(n_roll)
        return round(n / (n + _BAYES_K) * rv + _BAYES_K / (n + _BAYES_K) * sv, 4)

    s = {k: _avg(k, prior) for k in ("pts","reb","ast","min","fg3m","stl","blk","tov")}
    r = {k: _avg(k, roll)  for k in ("pts","reb","ast","min","fg3m","stl","blk","tov")}

    fga_sum = sum(float(x.get("fga", 0) or 0) for x in prior)
    fgm_sum = sum(float(x.get("fgm", 0) or 0) for x in prior)
    fg_pct  = fgm_sum / fga_sum if fga_sum > 0 else 0.44

    home_g = [x for x in roll if "@" not in str(x.get("matchup", ""))]
    away_g = [x for x in roll if "@"     in str(x.get("matchup", ""))]

    r_oreb = _avg("oreb",  roll); r_dreb = _avg("dreb", roll)
    r_pf   = _avg("pf",   roll)
    r_fga  = _avg("fga",  roll); r_fg3a = _avg("fg3a", roll)
    r_fta  = _avg("fta",  roll)
    r_pm   = _avg("plus_minus", roll)
    min_vals  = [float(x.get("min", 0) or 0) for x in roll]
    min_var   = float(np.var(min_vals)) if len(min_vals) > 1 else 0.0
    fga_vals  = [float(x.get("fga", 0) or 0) for x in roll]
    fga_trend = (fga_vals[-1] - fga_vals[0]) / max(len(fga_vals)-1, 1) if len(fga_vals) > 1 else 0.0
    dd_rate   = sum(
        1 for x in roll
        if float(x.get("pts", 0) or 0) >= 10 and float(x.get("reb", 0) or 0) >= 10
    ) / max(n_roll, 1)

    # STL-specific derived features
    _min_r = max(r["min"], 1.0)
    stl_per_min       = round(r["stl"] / _min_r * 36, 4)
    def_activity_rate = round((r["stl"] + r["blk"]) / _min_r, 4)
    stl_vals = [float(x.get("stl", 0) or 0) for x in roll]
    stl_consistency = float(np.var(stl_vals)) if len(stl_vals) > 1 else 0.0

    row = {f: 0.0 for f in all_feats}
    row.update({
        "season_pts": s["pts"], "season_reb": s["reb"], "season_ast": s["ast"],
        "season_min": s["min"], "season_fg3m": s["fg3m"], "season_stl": s["stl"],
        "season_blk": s["blk"], "season_tov": s["tov"],
        "pts_roll":  r["pts"],  "reb_roll":  r["reb"],
        "ast_roll":  r["ast"],  "min_roll":  r["min"],
        "stl_roll":  r["stl"],  "blk_roll":  r["blk"],
        "stl_per_min":       stl_per_min,
        "def_activity_rate": def_activity_rate,
        "stl_consistency":   stl_consistency,
        "pts_bayes":  _bayes(r["pts"],  s["pts"]),
        "reb_bayes":  _bayes(r["reb"],  s["reb"]),
        "ast_bayes":  _bayes(r["ast"],  s["ast"]),
        "fg3m_bayes": _bayes(r["fg3m"], s["fg3m"]),
        "stl_bayes":  _bayes(r["stl"],  s["stl"]),
        "blk_bayes":  _bayes(r["blk"],  s["blk"]),
        "tov_bayes":  _bayes(r["tov"],  s["tov"]),
        "fg_pct": fg_pct,
        "home_pts_avg": _avg("pts", home_g) if home_g else s["pts"],
        "away_pts_avg": _avg("pts", away_g) if away_g else s["pts"],
        "home_reb_avg": _avg("reb", home_g) if home_g else s["reb"],
        "away_reb_avg": _avg("reb", away_g) if away_g else s["reb"],
        "home_ast_avg": _avg("ast", home_g) if home_g else s["ast"],
        "away_ast_avg": _avg("ast", away_g) if away_g else s["ast"],
        "pts_vs_opp": s["pts"], "reb_vs_opp": s["reb"], "ast_vs_opp": s["ast"],
        "oreb_roll": r_oreb, "dreb_roll": r_dreb, "pf_roll": r_pf,
        "fga_roll": r_fga, "fg3a_roll": r_fg3a, "fta_roll": r_fta,
        "plus_minus_roll": r_pm, "min_variance": min_var,
        "fga_trend": fga_trend, "double_double_rate": dd_rate,
    })
    return row


# -- Dataset builder -----------------------------------------------------------

def _build_dataset(
    by_player: Dict[int, List[dict]],
    all_feats: List[str],
) -> Dict[str, dict]:
    """
    Returns per-stat dict with keys:
      X_train, y_train, X_test, y_test, X_val, y_val
    """
    # Build opponent tov_pct / pace lookup: {season: {abbrev: {tov_pct, pace}}}
    _opp_stats_by_season: Dict[str, dict] = {}
    try:
        from nba_api.stats.static import teams as _nba_teams
        _abbrev_to_id = {t["abbreviation"]: str(t["id"]) for t in _nba_teams.get_teams()}
    except Exception:
        _abbrev_to_id = {}
    for _s in ("2022-23", "2023-24", "2024-25", "2025-26"):
        _ts_path = os.path.join(_NBA_CACHE, f"team_stats_{_s}.json")
        if os.path.exists(_ts_path):
            try:
                _ts = json.load(open(_ts_path))
                _opp_stats_by_season[_s] = {
                    abbr: {
                        "opp_tov_pct":  float(_ts.get(_abbrev_to_id.get(abbr, ""), {}).get("tov_pct",       0.145) or 0.145),
                        "opp_pace":     float(_ts.get(_abbrev_to_id.get(abbr, ""), {}).get("pace",          100.0) or 100.0),
                        "opp_stl_rate": float(_ts.get(_abbrev_to_id.get(abbr, ""), {}).get("stl_per_poss",  0.080) or 0.080),
                    }
                    for abbr in _abbrev_to_id
                }
            except Exception:
                pass

    def _opp_abbr(matchup: str) -> str:
        """Extract opponent abbreviation from matchup string like 'SAS vs. TOR' or 'SAS @ TOR'."""
        m = str(matchup)
        for sep in (" vs. ", " @ "):
            if sep in m:
                return m.split(sep)[-1].strip()
        return ""

    rows_train = {s: [] for s in _PROP_STATS}
    rows_test  = {s: [] for s in _PROP_STATS}
    rows_val   = {s: [] for s in _PROP_STATS}
    y_train = {s: [] for s in _PROP_STATS}
    y_test  = {s: [] for s in _PROP_STATS}
    y_val   = {s: [] for s in _PROP_STATS}

    n_players = len(by_player)
    for idx, (pid, games) in enumerate(by_player.items()):
        if idx % 100 == 0:
            print(f"  [build] {idx}/{n_players} players ...", flush=True)
        for i, game in enumerate(games):
            # Only use prior games from the same season as rolling context.
            # This prevents a player's 2023-24 rolling average from bleeding into
            # the first game of 2024-25 (which would have no same-season prior).
            cur_season = game.get("_season", "")
            prior_same_season = [g for g in games[:i] if g.get("_season") == cur_season]
            prior = prior_same_season
            if len(prior) < _MIN_PRIOR:
                continue
            dt = game["_dt"]
            feat_row = _build_row(pid, prior, all_feats)

            # Add opponent tov_pct / pace for this game
            _opp = _opp_abbr(game.get("matchup", ""))
            _os  = _opp_stats_by_season.get(cur_season, {}).get(_opp, {})
            feat_row["opp_tov_pct"]  = _os.get("opp_tov_pct",  0.145)
            feat_row["opp_pace"]     = _os.get("opp_pace",    100.0)
            feat_row["opp_stl_rate"] = _os.get("opp_stl_rate", 0.080)

            for stat in _PROP_STATS:
                actual = game.get(stat)
                if actual is None:
                    continue
                try:
                    actual = float(actual)
                except (TypeError, ValueError):
                    continue

                if dt < _TRAIN_CUTOFF:
                    rows_train[stat].append(feat_row)
                    y_train[stat].append(actual)
                elif dt < _TEST_CUTOFF:
                    rows_test[stat].append(feat_row)
                    y_test[stat].append(actual)
                else:
                    rows_val[stat].append(feat_row)
                    y_val[stat].append(actual)

    out = {}
    for stat in _PROP_STATS:
        cols = [c for c in all_feats if c != f"season_{stat}"]
        def _to_X(rows):
            return pd.DataFrame(rows)[cols] if rows else pd.DataFrame(columns=cols)
        out[stat] = {
            "cols":    cols,
            "X_train": _to_X(rows_train[stat]),
            "y_train": np.array(y_train[stat]),
            "X_test":  _to_X(rows_test[stat]),
            "y_test":  np.array(y_test[stat]),
            "X_val":   _to_X(rows_val[stat]),
            "y_val":   np.array(y_val[stat]),
        }
        print(
            f"  [build] {stat:4s}  train={len(y_train[stat])}  "
            f"test={len(y_test[stat])}  val={len(y_val[stat])}"
        )
    return out


# -- Train + evaluate ----------------------------------------------------------

def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    if len(y_true) == 0:
        return {"mae": None, "r2": None, "n": 0}
    y_pred = np.maximum(y_pred, 0.0)
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "r2":  round(float(r2_score(y_true, y_pred)), 4),
        "n":   int(len(y_true)),
    }


def train_and_save(datasets: Dict[str, dict], only_stat: str = None) -> Dict[str, dict]:
    os.makedirs(_MODEL_DIR, exist_ok=True)
    results = {}

    stats_to_train = (only_stat,) if only_stat else _PROP_STATS

    for stat in stats_to_train:
        d = datasets[stat]
        X_train, y_train = d["X_train"], d["y_train"]
        X_test,  y_test  = d["X_test"],  d["y_test"]
        X_val,   y_val   = d["X_val"],   d["y_val"]

        if len(y_train) == 0:
            print(f"[train] {stat}: no training data -- skipping")
            continue

        print(f"\n[train] {stat.upper()} -- {len(y_train)} train rows", flush=True)

        params = _XGB_PARAMS_STL if stat == "stl" else _XGB_PARAMS
        model = xgb.XGBRegressor(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)] if len(y_test) > 0 else None,
            verbose=False,
        )

        train_m = _metrics(y_train, model.predict(X_train))
        test_m  = _metrics(y_test,  model.predict(X_test)  if len(y_test) > 0 else np.array([]))
        val_m   = _metrics(y_val,   model.predict(X_val)   if len(y_val)  > 0 else np.array([]))

        print(
            f"  train  MAE={train_m['mae']:.4f}  R2={train_m['r2']:.4f}  n={train_m['n']}\n"
            f"  test   MAE={test_m['mae']}  R2={test_m['r2']}  n={test_m['n']}\n"
            f"  val    MAE={val_m['mae']}   R2={val_m['r2']}   n={val_m['n']}"
        )

        # Always save v2
        v2_path = os.path.join(_MODEL_DIR, f"props_{stat}_v2.json")
        model.save_model(v2_path)
        metrics_path = os.path.join(_MODEL_DIR, f"props_{stat}_v2_metrics.json")
        with open(metrics_path, "w") as _mf:
            json.dump({"stat": stat, "train": train_m, "test": test_m, "val": val_m}, _mf, indent=2)
        print(f"  saved -> {v2_path}")

        # Overwrite props_{stat}.json if val R2 beats current registry
        old_r2 = _get_registry_r2(stat)
        val_r2 = val_m["r2"] if val_m["r2"] is not None else -999.0
        if val_r2 > (old_r2 or -999.0):
            prod_path = os.path.join(_MODEL_DIR, f"props_{stat}.json")
            tmp_path  = prod_path + ".tmp"
            model.save_model(tmp_path)
            os.replace(tmp_path, prod_path)
            print(f"  promoted -> {prod_path}  (val R2 {val_r2:.4f} > old {old_r2})")

        results[stat] = {
            "train": train_m,
            "test":  test_m,
            "val":   val_m,
        }

    return results


def _get_registry_r2(stat: str) -> Optional[float]:
    if not os.path.exists(_REG_PATH):
        return None
    try:
        reg = json.load(open(_REG_PATH))
        return reg.get(f"props_{stat}", {}).get("holdout_r2")
    except Exception:
        return None


# -- Registry update -----------------------------------------------------------

def _update_registry(results: Dict[str, dict]) -> None:
    try:
        registry = json.load(open(_REG_PATH)) if os.path.exists(_REG_PATH) else {}
    except Exception:
        registry = {}

    for stat, r in results.items():
        val  = r["val"]
        test = r["test"]
        key  = f"props_{stat}"
        if key not in registry:
            registry[key] = {}
        registry[key].update({
            "train_mae":    r["train"]["mae"],
            "train_r2":     r["train"]["r2"],
            "train_n":      r["train"]["n"],
            "test_mae":     test["mae"],
            "test_r2":      test["r2"],
            "test_n":       test["n"],
            "holdout_mae":  val["mae"],
            "holdout_r2":   val["r2"],
            "holdout_n":    val["n"],
            "needs_retrain": (val["r2"] is None) or (val["r2"] < 0.10),
            "retrained_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "retrain_version": "v2_multiseasson_2022-23_to_2024-25",
        })

    with open(_REG_PATH, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"\n[retrain] Registry updated -> {_REG_PATH}")


# -- Main ----------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--stat", default=None, help="Only retrain this stat (e.g. stl)")
    args = parser.parse_args()
    only_stat = args.stat.lower() if args.stat else None
    if only_stat and only_stat not in _PROP_STATS:
        print(f"[retrain] Unknown stat: {only_stat}. Choose from {_PROP_STATS}")
        return

    print("[retrain] Loading feature list ...")
    all_feats = _load_all_feats()
    print(f"[retrain] {len(all_feats)} features")

    print("[retrain] Loading gamelogs ...")
    by_player = _load_gamelogs()
    print(f"[retrain] {len(by_player)} players")

    print("[retrain] Building dataset (train/test/val) ...")
    datasets = _build_dataset(by_player, all_feats)

    print("\n[retrain] Training models ...")
    results = train_and_save(datasets, only_stat=only_stat)

    print("\n-- Final Results -----------------------------------------")
    for stat in (_PROP_STATS if not only_stat else (only_stat,)):
        if stat not in results:
            continue
        r = results[stat]
        print(
            f"  {stat.upper():4s}  "
            f"train R2={r['train']['r2']:.4f}  "
            f"test R2={r['test']['r2']}  "
            f"val R2={r['val']['r2']}  "
            f"val MAE={r['val']['mae']}"
        )
    print("----------------------------------------------------------\n")

    _update_registry(results)
    print("[retrain] Done.")


if __name__ == "__main__":
    main()
