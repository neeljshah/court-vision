"""
retrain_props_v3.py — Retrain all 7 prop models with the v3 feature set.

Integrates all 12 new feature modules via build_v3_features().
Walk-forward split is identical to retrain_props_v2.py:
  Train  : games < 2025-10-01  (2022-23, 2023-24, 2024-25)
  Test   : 2025-10-01 – 2026-01-01  (early 2025-26)
  Val    : 2026-01-01+  (holdout)

Output
  data/models/prop_{stat}_v3_lgb.txt     — LightGBM booster per stat
  data/models/prop_v3_metrics.json       — full metrics + feature importance
  data/models/prop_residuals.json        — val {predicted, actual, stat} for
                                          calibrate_props.py to consume

Usage
-----
    conda activate basketball_ai
    python scripts/retrain_props_v3.py
    python scripts/retrain_props_v3.py --stat pts
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.features.v3_prop_features import build_v3_features

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_REG_PATH  = os.path.join(_MODEL_DIR, "model_registry.json")

_PROP_STATS   = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_TRAIN_CUTOFF = datetime(2025, 10, 1)
_TEST_CUTOFF  = datetime(2026,  1, 1)
_MIN_PRIOR    = 3

_LGB_PARAMS = {
    "n_estimators":    600,
    "learning_rate":   0.05,
    "num_leaves":      63,
    "min_child_samples": 20,
    "reg_lambda":      1.0,
    "objective":       "regression_l1",
    "n_jobs":          -1,
    "random_state":    42,
    "verbose":         -1,
}

_BASELINE_V2_MAE = {
    "pts": 4.12, "reb": 1.84, "ast": 1.52, "fg3m": 0.91,
    "stl": 0.48, "blk": 0.42, "tov": 0.76,
}
_BASELINE_V2_R2 = {
    "pts": 0.41, "reb": 0.38, "ast": 0.36, "fg3m": 0.29,
    "stl": 0.18, "blk": 0.16, "tov": 0.22,
}


# ── Date parser ───────────────────────────────────────────────────────────────

def _parse_date(s: str) -> Optional[datetime]:
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


# ── Gamelog loader (same as v2) ───────────────────────────────────────────────

def _load_gamelogs() -> Dict[int, List[dict]]:
    by_player: Dict[int, List[dict]] = defaultdict(list)
    files = glob.glob(os.path.join(_NBA_CACHE, "gamelog_full_*_????-??.json"))
    print(f"[retrain-v3] Found {len(files)} gamelog files")
    for fpath in files:
        m = re.search(r"gamelog_full_(\d+)_(\d{4}-\d{2})\.json", os.path.basename(fpath))
        if not m:
            continue
        pid = int(m.group(1))
        season = m.group(2)
        try:
            rows = json.load(open(fpath))
        except Exception:
            continue
        for r in rows:
            d = _parse_date(str(r.get("game_date", "")))
            if d is None:
                continue
            by_player[pid].append({**r, "_dt": d, "_season": season})
    for pid in by_player:
        by_player[pid].sort(key=lambda r: r["_dt"])
    return by_player


# ── NBA team-id lookup (cached) ───────────────────────────────────────────────

_ABBR_TO_ID: Optional[Dict[str, int]] = None

def _abbr_to_team_id(abbr: str) -> int:
    global _ABBR_TO_ID
    if _ABBR_TO_ID is None:
        try:
            from nba_api.stats.static import teams as _nt
            _ABBR_TO_ID = {t["abbreviation"]: t["id"] for t in _nt.get_teams()}
        except Exception:
            _ABBR_TO_ID = {}
    return _ABBR_TO_ID.get(abbr.upper(), 0)


def _opp_abbr(matchup: str) -> str:
    m = str(matchup)
    for sep in (" vs. ", " @ "):
        if sep in m:
            return m.split(sep)[-1].strip()
    return ""


def _is_home(matchup: str) -> bool:
    return "@" not in str(matchup)


# ── Opponent stats loader (for opp_tov_pct / opp_pace) ────────────────────────

def _load_opp_stats() -> Dict[str, dict]:
    out = {}
    try:
        from nba_api.stats.static import teams as _nt
        abbrev_to_id = {t["abbreviation"]: str(t["id"]) for t in _nt.get_teams()}
    except Exception:
        abbrev_to_id = {}
    for _s in ("2022-23", "2023-24", "2024-25", "2025-26"):
        path = os.path.join(_NBA_CACHE, f"team_stats_{_s}.json")
        if not os.path.exists(path):
            continue
        try:
            ts = json.load(open(path))
            for abbr, tid in abbrev_to_id.items():
                entry = ts.get(tid, {})
                if entry:
                    out[abbr] = {
                        "opp_tov_pct":  float(entry.get("tov_pct",       0.145) or 0.145),
                        "opp_pace":     float(entry.get("pace",          100.0) or 100.0),
                        "opp_stl_rate": float(entry.get("stl_per_poss",  0.080) or 0.080),
                    }
        except Exception:
            pass
    return out


# ── Dataset builder ───────────────────────────────────────────────────────────

def _build_dataset(by_player: Dict[int, List[dict]]) -> Dict[str, dict]:
    opp_stats = _load_opp_stats()

    rows_train = {s: [] for s in _PROP_STATS}
    rows_test  = {s: [] for s in _PROP_STATS}
    rows_val   = {s: [] for s in _PROP_STATS}
    y_train    = {s: [] for s in _PROP_STATS}
    y_test     = {s: [] for s in _PROP_STATS}
    y_val      = {s: [] for s in _PROP_STATS}

    # Collect residuals for calibrate_props.py (val split only)
    val_residuals: List[dict] = []

    n_players = len(by_player)
    for idx, (pid, games) in enumerate(by_player.items()):
        if idx % 100 == 0:
            print(f"  [build] {idx}/{n_players} players ...", flush=True)
        for i, game in enumerate(games):
            cur_season = game.get("_season", "")
            prior = [g for g in games[:i] if g.get("_season") == cur_season]
            if len(prior) < _MIN_PRIOR:
                continue

            dt = game["_dt"]
            game_date_str = dt.strftime("%Y-%m-%d")
            matchup       = str(game.get("matchup", ""))
            opp_abbr      = _opp_abbr(matchup)
            at_home       = _is_home(matchup)
            home_team     = (matchup.split(" vs.")[0].strip().split()[-1]
                             if "vs." in matchup else opp_abbr)
            away_team     = (matchup.split("@ ")[-1].strip().split()[0]
                             if "@" in matchup else opp_abbr)

            opp_s         = opp_stats.get(opp_abbr, {})
            team_id_val   = _abbr_to_team_id(home_team if at_home else away_team)
            opp_team_id   = _abbr_to_team_id(opp_abbr)

            try:
                feat_row = build_v3_features(
                    player_id  = pid,
                    game_date  = game_date_str,
                    season     = cur_season,
                    team_id    = team_id_val,
                    opp_team_id= opp_team_id,
                    home_team  = home_team if at_home else opp_abbr,
                    away_team  = opp_abbr  if at_home else home_team,
                    is_home    = at_home,
                    prior_games= prior,
                )
            except Exception as exc:
                print(f"  [build] build_v3_features error pid={pid} date={game_date_str}: {exc}")
                continue

            # Patch in accurate opp stats (they're filled as defaults inside v3)
            feat_row["opp_tov_pct"]  = opp_s.get("opp_tov_pct",  0.145)
            feat_row["opp_pace"]     = opp_s.get("opp_pace",     100.0)
            feat_row["opp_stl_rate"] = opp_s.get("opp_stl_rate", 0.080)

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

    # Determine feature columns (union of all keys, exclude target season_{stat})
    all_keys: set = set()
    for stat in _PROP_STATS:
        for lst in (rows_train[stat], rows_test[stat], rows_val[stat]):
            for r in lst:
                all_keys.update(r.keys())

    out = {}
    for stat in _PROP_STATS:
        cols = sorted(k for k in all_keys if k != f"season_{stat}")

        def _to_X(rows):
            if not rows:
                return pd.DataFrame(columns=cols)
            df = pd.DataFrame(rows)
            for c in cols:
                if c not in df.columns:
                    df[c] = 0.0
            return df[cols].fillna(0.0)

        out[stat] = {
            "cols":    cols,
            "X_train": _to_X(rows_train[stat]),
            "y_train": np.array(y_train[stat], dtype=np.float32),
            "X_test":  _to_X(rows_test[stat]),
            "y_test":  np.array(y_test[stat],  dtype=np.float32),
            "X_val":   _to_X(rows_val[stat]),
            "y_val":   np.array(y_val[stat],   dtype=np.float32),
            "val_rows": rows_val[stat],   # for residuals export
        }
        print(
            f"  [build] {stat:4s}  train={len(y_train[stat])}"
            f"  test={len(y_test[stat])}  val={len(y_val[stat])}"
        )
    return out


# ── Train & evaluate ──────────────────────────────────────────────────────────

def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    if len(y_true) == 0:
        return {"mae": None, "r2": None, "n": 0}
    y_pred = np.maximum(y_pred, 0.0)
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "r2":  round(float(r2_score(y_true, y_pred)), 4),
        "n":   int(len(y_true)),
    }


def train_all(datasets: Dict[str, dict], only_stat: Optional[str] = None) -> dict:
    import lightgbm as lgb

    os.makedirs(_MODEL_DIR, exist_ok=True)
    results = {}
    all_residuals: List[dict] = []

    stats_to_train = (only_stat,) if only_stat else _PROP_STATS

    for stat in stats_to_train:
        d = datasets[stat]
        X_train, y_train = d["X_train"], d["y_train"]
        X_test,  y_test  = d["X_test"],  d["y_test"]
        X_val,   y_val   = d["X_val"],   d["y_val"]
        cols             = d["cols"]

        if len(y_train) == 0:
            print(f"[train-v3] {stat}: no training data -- skipping")
            continue

        print(f"\n[train-v3] {stat.upper()} — {len(y_train)} train rows / {len(cols)} features",
              flush=True)

        model = lgb.LGBMRegressor(**_LGB_PARAMS)

        eval_sets = [(X_val.values, y_val)] if len(y_val) > 0 else None
        model.fit(
            X_train.values, y_train,
            eval_set=eval_sets,
            callbacks=[lgb.early_stopping(50, verbose=False),
                       lgb.log_evaluation(period=-1)],
        )

        train_m = _metrics(y_train, model.predict(X_train.values))
        test_m  = _metrics(y_test,  model.predict(X_test.values)  if len(y_test) > 0 else np.array([]))
        val_m   = _metrics(y_val,   model.predict(X_val.values)   if len(y_val)  > 0 else np.array([]))

        print(
            f"  train  MAE={train_m['mae']:.4f}  R²={train_m['r2']:.4f}  n={train_m['n']}\n"
            f"  test   MAE={test_m['mae']}  R²={test_m['r2']}  n={test_m['n']}\n"
            f"  val    MAE={val_m['mae']}   R²={val_m['r2']}   n={val_m['n']}"
        )

        # Feature importance (top 20)
        imp = model.feature_importances_
        feat_imp = sorted(zip(cols, imp), key=lambda x: x[1], reverse=True)[:20]

        # Save model
        model_path = os.path.join(_MODEL_DIR, f"prop_{stat}_v3_lgb.txt")
        model.booster_.save_model(model_path)
        print(f"  saved -> {model_path}")

        # Collect val residuals for calibrate_props.py
        if len(y_val) > 0:
            val_preds = model.predict(X_val.values)
            for actual, pred in zip(y_val, val_preds):
                all_residuals.append({
                    "stat":      stat,
                    "predicted": round(float(max(pred, 0.0)), 4),
                    "actual":    round(float(actual), 4),
                })

        results[stat] = {
            "train":    train_m,
            "test":     test_m,
            "val":      val_m,
            "top_features": [f for f, _ in feat_imp],
            "best_iteration": int(getattr(model, "best_iteration_", _LGB_PARAMS["n_estimators"])),
        }

    # Write residuals for calibrate_props.py
    residuals_path = os.path.join(_MODEL_DIR, "prop_residuals.json")
    if all_residuals:
        with open(residuals_path, "w") as f:
            json.dump(all_residuals, f)
        print(f"\n[train-v3] Residuals written -> {residuals_path}  ({len(all_residuals)} rows)")

    return results


# ── Metrics persistence ───────────────────────────────────────────────────────

def _save_metrics(results: dict, datasets: dict) -> None:
    stats_block = {}
    for stat, r in results.items():
        d = datasets.get(stat, {})
        stats_block[stat] = {
            "mae_val":    r["val"]["mae"],
            "mae_holdout": r["val"]["mae"],
            "r2_val":     r["val"]["r2"],
            "r2_holdout": r["val"]["r2"],
            "n_train":    r["train"]["n"],
            "n_val":      r["val"]["n"],
            "n_holdout":  r["val"]["n"],
            "features":   r["top_features"],
            "best_iteration": r.get("best_iteration"),
        }

    out = {
        "version":         "v3_integration",
        "stats":           stats_block,
        "trained_at":      datetime.now().isoformat(),
        "feature_count":   len(datasets[list(results.keys())[0]]["cols"]) if results else 0,
        "baseline_v2_mae": _BASELINE_V2_MAE,
        "baseline_v2_r2":  _BASELINE_V2_R2,
    }
    path = os.path.join(_MODEL_DIR, "prop_v3_metrics.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n[train-v3] Metrics -> {path}")


# ── Before/after table ────────────────────────────────────────────────────────

def _print_table(results: dict) -> None:
    header = f"{'stat':<6}  {'v2_mae':>7}  {'v3_mae':>7}  {'delta_mae':>10}  {'v2_r2':>6}  {'v3_r2':>6}  {'delta_r2':>9}"
    print("\n" + "=" * len(header))
    print("BEFORE / AFTER TABLE (holdout)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for stat in _PROP_STATS:
        if stat not in results:
            continue
        v2m = _BASELINE_V2_MAE.get(stat)
        v3m = results[stat]["val"]["mae"]
        v2r = _BASELINE_V2_R2.get(stat)
        v3r = results[stat]["val"]["r2"]
        if v3m is None or v2m is None:
            continue
        dm = v3m - v2m
        dr = (v3r - v2r) if (v3r is not None and v2r is not None) else None
        print(
            f"{stat:<6}  {v2m:>7.4f}  {v3m:>7.4f}  {dm:>+10.4f}  "
            f"{v2r:>6.4f}  {v3r:>6.4f}  {dr:>+9.4f}"
        )
    print("=" * len(header))
    print()


# ── Top global features ───────────────────────────────────────────────────────

def _print_top_features(results: dict) -> None:
    freq: Dict[str, int] = defaultdict(int)
    for r in results.values():
        for f in r.get("top_features", []):
            freq[f] += 1
    ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:15]
    print("TOP 15 FEATURES (by frequency in top-20 across all stats):")
    for i, (feat, cnt) in enumerate(ranked, 1):
        print(f"  {i:2d}. {feat:<45s}  (in top-20 for {cnt}/7 stats)")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--stat", default=None)
    args = parser.parse_args()
    only_stat = args.stat.lower() if args.stat else None
    if only_stat and only_stat not in _PROP_STATS:
        print(f"[retrain-v3] Unknown stat: {only_stat}")
        return

    t0 = time.time()

    print("[retrain-v3] Loading gamelogs ...")
    by_player = _load_gamelogs()
    print(f"[retrain-v3] {len(by_player)} players")

    print("[retrain-v3] Building v3 dataset ...")
    datasets = _build_dataset(by_player)

    print("\n[retrain-v3] Training LightGBM models ...")
    results = train_all(datasets, only_stat=only_stat)

    _save_metrics(results, datasets)
    _print_table(results)
    _print_top_features(results)

    elapsed = time.time() - t0
    print(f"[retrain-v3] Done in {elapsed / 60:.1f} min.")


if __name__ == "__main__":
    main()
