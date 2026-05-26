"""probe_R10_M16_streak.py — M16 Hot-hand / Streak Detection (loop 5, R10).

WHY: Existing features capture rolling MEANS (l5/l10/l20/ewma) but not
STREAK DIRECTION. A player on a 3-game hot streak has a different Q4
distribution than one who was hot 10 games ago. True z-score streak features
encode TREND, not just level.

FEATURES (computed strictly from games BEFORE target_date, shift(1) discipline):
  hot_streak_<stat>   = (mean_l3 - mean_l20) / (std_l20 + eps)   — z-score trend
  cold_streak_<stat>  = -(mean_l3 - mean_l20) / (std_l20 + eps)  — inverse
  consec_above_<stat> = consecutive games at end of history where player
                        exceeded their L20 mean (streak length)
  For stats: pts, reb, ast, fg3m

METHOD:
  1. Load gamelog files -> per-player time-sorted history.
  2. For each OOF row (player_id, game_date, stat), locate the player's
     prior games (strictly before game_date), compute streak features.
  3. Walk-forward 4-fold: train LGB residual head on streak features only;
     measure delta vs OOF baseline.

SHIP GATE: WF 4/4 folds positive, mean delta <= -0.005, >= 4/7 stats improving.
BASELINE (endQ3 projection):
  pts=2.214, reb=0.8987, ast=0.5755, fg3m=0.3528, stl=0.2506, blk=0.1543, tov=0.3663

Run:
    python -u scripts/probe_R10_M16_streak.py > scripts/_results/improve_R10_M16_run.log 2>&1
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# ── constants ────────────────────────────────────────────────────────────────

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
STREAK_STATS = ("pts", "reb", "ast", "fg3m")  # streak features computed for these
BASELINES = {
    "pts":  2.214,
    "reb":  0.8987,
    "ast":  0.5755,
    "fg3m": 0.3528,
    "stl":  0.2506,
    "blk":  0.1543,
    "tov":  0.3663,
}
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_OOF_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
_RESULTS_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
_CACHE_OUT = os.path.join(PROJECT_DIR, "data", "cache", "probe_R10_M16_streak_results.json")

_EPS = 1e-6
_L3 = 3
_L20 = 20


# ── gamelog loader ────────────────────────────────────────────────────────────

def _parse_date(raw: str) -> Optional[datetime]:
    """Parse NBA gamelog date 'Apr 06, 2023' -> datetime."""
    try:
        return datetime.strptime(str(raw).strip(), "%b %d, %Y")
    except Exception:
        return None


def load_player_histories(nba_cache: str = _NBA_CACHE) -> Dict[int, List[Tuple[datetime, Dict]]]:
    """Load all gamelog_<pid>_<season>.json files.

    Returns {player_id: [(date, {pts, reb, ast, fg3m, stl, blk, tov, min}), ...]}
    sorted oldest->newest. Merges across seasons per player.
    """
    print("Loading gamelog files ...", flush=True)
    histories: Dict[int, List[Tuple[datetime, Dict]]] = {}
    n_files = n_rows = 0
    for fname in os.listdir(nba_cache):
        if not fname.startswith("gamelog_") or not fname.endswith(".json"):
            continue
        parts = fname[len("gamelog_"):-len(".json")].rsplit("_", 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        fpath = os.path.join(nba_cache, fname)
        try:
            with open(fpath, encoding="utf-8") as fh:
                games = json.load(fh)
        except Exception:
            continue
        if not isinstance(games, list):
            continue
        n_files += 1
        for g in games:
            d = _parse_date(g.get("GAME_DATE") or "")
            if d is None:
                continue
            try:
                row = {
                    "pts":  float(g.get("PTS") or 0),
                    "reb":  float(g.get("REB") or 0),
                    "ast":  float(g.get("AST") or 0),
                    "fg3m": float(g.get("FG3M") or 0),
                    "stl":  float(g.get("STL") or 0),
                    "blk":  float(g.get("BLK") or 0),
                    "tov":  float(g.get("TOV") or 0),
                    "min":  float(g.get("MIN") or 0),
                }
            except (TypeError, ValueError):
                continue
            if row["min"] < 1.0:
                continue  # DNP — skip
            histories.setdefault(pid, []).append((d, row))
            n_rows += 1

    # Sort each player's history oldest->newest; deduplicate by date (same-date = one game)
    for pid in histories:
        seen: Dict[datetime, Dict] = {}
        for d, row in histories[pid]:
            seen[d] = row  # last entry wins (season overlap)
        histories[pid] = sorted(seen.items())

    print(f"  Loaded {n_files} gamelog files, {n_rows} player-game rows, "
          f"{len(histories)} unique players.", flush=True)
    return histories


# ── streak feature computation ────────────────────────────────────────────────

def compute_streak_features(
    history: List[Tuple[datetime, Dict]],
    target_date: datetime,
) -> Dict[str, float]:
    """Compute streak features from prior games only (strictly before target_date).

    Uses shift(1) semantics: only games where date < target_date are used.
    Returns dict with hot_streak_<stat>, cold_streak_<stat>, consec_above_<stat>
    for each stat in STREAK_STATS.
    """
    out: Dict[str, float] = {}

    # Games strictly before target_date, sorted oldest->newest
    prior = [(d, row) for d, row in history if d < target_date]

    for stat in STREAK_STATS:
        vals = [row[stat] for _, row in prior]

        # L3 and L20 windows (most recent at end)
        l3 = vals[-_L3:] if len(vals) >= _L3 else vals
        l20 = vals[-_L20:] if len(vals) >= _L20 else vals

        mean_l3 = float(np.mean(l3)) if l3 else 0.0
        mean_l20 = float(np.mean(l20)) if l20 else 0.0
        std_l20 = float(np.std(l20)) if l20 else 0.0

        z = (mean_l3 - mean_l20) / (std_l20 + _EPS)
        out[f"hot_streak_{stat}"]  = z
        out[f"cold_streak_{stat}"] = -z

        # Consecutive games (from most recent) where player exceeded L20 mean
        consec = 0
        for _, row in reversed(prior):
            if row[stat] > mean_l20:
                consec += 1
            else:
                break
        out[f"consec_above_{stat}"] = float(consec)

        # Additional: n_prior games (coverage signal)
        out[f"n_prior_{stat}"] = float(len(prior))

    return out


# ── build feature matrix ──────────────────────────────────────────────────────

STREAK_FEATURE_NAMES = [
    f"{prefix}_{stat}"
    for stat in STREAK_STATS
    for prefix in ("hot_streak", "cold_streak", "consec_above")
] + [f"n_prior_{stat}" for stat in STREAK_STATS[:1]]  # just one n_prior as coverage


def _streak_feature_names() -> List[str]:
    names = []
    for stat in STREAK_STATS:
        names += [f"hot_streak_{stat}", f"cold_streak_{stat}", f"consec_above_{stat}"]
    names.append("n_prior_pts")  # coverage proxy
    return names


def build_streak_matrix(
    oof_df: pd.DataFrame,
    stat: str,
    histories: Dict[int, List[Tuple[datetime, Dict]]],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]]:
    """Build (X, oof_pred, actual, folds) for the given stat.

    X contains only streak features. Rows with no history are dropped.
    """
    fc = _streak_feature_names()
    sub = oof_df[oof_df["stat"] == stat].copy()
    sub["_date"] = pd.to_datetime(sub["game_date"]).dt.to_pydatetime()

    X_list, oof_list, act_list, fold_list = [], [], [], []
    n_miss = 0

    for _, row in sub.iterrows():
        pid = int(row["player_id"])
        gdate = row["_date"]
        if isinstance(gdate, pd.Timestamp):
            gdate = gdate.to_pydatetime()

        hist = histories.get(pid)
        if not hist:
            n_miss += 1
            continue

        # Only include rows with at least L3 prior games
        prior_count = sum(1 for d, _ in hist if d < gdate)
        if prior_count < _L3:
            n_miss += 1
            continue

        feats = compute_streak_features(hist, gdate)
        vec = np.array([feats.get(f, 0.0) for f in fc], dtype=np.float32)

        X_list.append(vec)
        oof_list.append(float(row["oof_pred"]))
        act_list.append(float(row["actual"]))
        fold_list.append(int(row["fold"]))

    total = len(X_list) + n_miss
    join_rate = len(X_list) / total if total else 0.0
    print(f"  [{stat:>4}] rows={len(X_list):,}/{total:,} ({join_rate:.1%}), "
          f"no-hist dropped={n_miss:,}", flush=True)

    if len(X_list) < 100:
        return (np.zeros((0, len(fc)), dtype=np.float32),
                np.zeros(0, dtype=np.float32),
                np.zeros(0, dtype=np.float32),
                np.zeros(0, dtype=np.int32),
                fc)

    X = np.vstack(X_list).astype(np.float32)
    return (X,
            np.array(oof_list, dtype=np.float32),
            np.array(act_list, dtype=np.float32),
            np.array(fold_list, dtype=np.int32),
            fc)


# ── walk-forward eval ─────────────────────────────────────────────────────────

def _lgb_params() -> Dict:
    return {
        "objective":         "regression_l1",
        "num_leaves":        15,
        "min_child_samples": 40,
        "learning_rate":     0.03,
        "n_estimators":      300,
        "random_state":      42,
        "verbosity":         -1,
        "n_jobs":            -1,
    }


def wf_eval(
    X: np.ndarray,
    folds: np.ndarray,
    oof_pred: np.ndarray,
    actual: np.ndarray,
    fc: List[str],
    stat: str,
) -> Dict:
    """Walk-forward 4-fold eval. Returns fold_wins, mean_delta, per-fold records."""
    try:
        import lightgbm as lgb
    except ImportError:
        return {"fold_wins": 0, "mean_delta": 0.0, "folds": [], "error": "lgb missing"}

    params = _lgb_params()
    fold_records = []
    fold_wins = 0
    deltas: List[float] = []

    for k in (1, 2, 3, 4):
        tr_mask = folds != k
        va_mask = folds == k
        if tr_mask.sum() < 50 or va_mask.sum() < 10:
            fold_records.append({"fold": k, "skip": True})
            continue

        y_resid_tr = actual[tr_mask] - oof_pred[tr_mask]

        model = lgb.LGBMRegressor(**params)
        model.fit(X[tr_mask], y_resid_tr, feature_name=fc)
        resid_pred = model.predict(X[va_mask])

        adjusted = oof_pred[va_mask] + resid_pred
        mae_adj  = float(np.mean(np.abs(adjusted - actual[va_mask])))
        mae_base = float(np.mean(np.abs(oof_pred[va_mask] - actual[va_mask])))
        delta = mae_adj - mae_base
        deltas.append(delta)
        fold_records.append({
            "fold":     k,
            "n":        int(va_mask.sum()),
            "mae_adj":  round(mae_adj, 6),
            "mae_base": round(mae_base, 6),
            "delta":    round(delta, 6),
        })
        win = delta < 0
        if win:
            fold_wins += 1
        print(f"    fold {k}: base={mae_base:.5f} adj={mae_adj:.5f} "
              f"delta={delta:+.5f} {'WIN' if win else '---'}", flush=True)

    mean_delta = float(np.mean(deltas)) if deltas else 0.0
    return {
        "fold_wins":  fold_wins,
        "mean_delta": round(mean_delta, 6),
        "folds":      fold_records,
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    t0 = time.time()

    print("=" * 65, flush=True)
    print("probe_R10_M16_streak — Hot-hand / Streak Detection", flush=True)
    print("=" * 65, flush=True)

    # 1. Load data
    histories = load_player_histories()
    print("Loading OOF parquet ...", flush=True)
    oof_df = pd.read_parquet(_OOF_PATH)
    print(f"  OOF shape: {oof_df.shape}", flush=True)

    # 2. Per-stat walk-forward
    results: Dict[str, Dict] = {}
    stat_wins = 0

    for stat in STATS:
        print(f"\n--- Stat: {stat} ---", flush=True)
        X, oof_pred, actual, folds, fc = build_streak_matrix(oof_df, stat, histories)

        if X.shape[0] < 100:
            print(f"  SKIP — insufficient rows ({X.shape[0]})", flush=True)
            results[stat] = {
                "fold_wins": 0, "mean_delta": 0.0, "skip": True,
                "baseline": BASELINES.get(stat, 0.0),
            }
            continue

        res = wf_eval(X, folds, oof_pred, actual, fc, stat)
        res["baseline"] = BASELINES.get(stat, 0.0)
        res["mean_adj_mae"] = round(
            res["baseline"] + res["mean_delta"], 6
        ) if res["mean_delta"] != 0.0 else None
        results[stat] = res

        gate_ok = res["fold_wins"] == 4 and res["mean_delta"] <= -0.005
        if res["mean_delta"] < 0:
            stat_wins += 1
        print(
            f"  => fold_wins={res['fold_wins']}/4  "
            f"mean_delta={res['mean_delta']:+.5f}  "
            f"{'GATE PASS' if gate_ok else 'gate fail'}",
            flush=True,
        )

    elapsed = time.time() - t0

    # 3. Aggregate gate
    fold_wins_all = [r.get("fold_wins", 0) for r in results.values() if not r.get("skip")]
    mean_deltas = [r.get("mean_delta", 0.0) for r in results.values() if not r.get("skip")]

    overall_fold_wins = all(w == 4 for w in fold_wins_all)
    overall_mean_delta = float(np.mean(mean_deltas)) if mean_deltas else 0.0
    overall_delta_gate = overall_mean_delta <= -0.005
    stats_improving = stat_wins
    stats_gate = stats_improving >= 4

    ship = overall_fold_wins and overall_delta_gate and stats_gate

    print("\n" + "=" * 65, flush=True)
    print("GATE SUMMARY", flush=True)
    print(f"  WF 4/4 all stats:       {'PASS' if overall_fold_wins else 'FAIL'}", flush=True)
    print(f"  Mean delta <= -0.005:   {overall_mean_delta:+.5f}  "
          f"{'PASS' if overall_delta_gate else 'FAIL'}", flush=True)
    print(f"  Stats improving >= 4/7: {stats_improving}/7  "
          f"{'PASS' if stats_gate else 'FAIL'}", flush=True)
    print(f"  SHIP: {'YES' if ship else 'NO'}", flush=True)
    print(f"  Elapsed: {elapsed:.1f}s", flush=True)

    print("\nPer-stat deltas:", flush=True)
    for stat in STATS:
        r = results[stat]
        if r.get("skip"):
            print(f"  {stat:>4}: SKIP", flush=True)
        else:
            print(f"  {stat:>4}: base={r['baseline']:.4f}  "
                  f"delta={r['mean_delta']:+.5f}  wins={r['fold_wins']}/4", flush=True)

    # 4. Write JSON
    out = {
        "probe":          "R10_M16_streak",
        "timestamp":      datetime.utcnow().isoformat(),
        "elapsed_s":      round(elapsed, 1),
        "ship":           ship,
        "gate": {
            "wf_4_4_all":      overall_fold_wins,
            "mean_delta":      round(overall_mean_delta, 6),
            "mean_delta_gate": overall_delta_gate,
            "stats_improving": stats_improving,
            "stats_gate":      stats_gate,
        },
        "per_stat":   results,
        "baselines":  BASELINES,
        "streak_features": _streak_feature_names(),
        "lgb_params": _lgb_params(),
    }
    with open(_CACHE_OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nWrote: {_CACHE_OUT}", flush=True)

    return 0 if ship else 1


if __name__ == "__main__":
    sys.exit(main())
