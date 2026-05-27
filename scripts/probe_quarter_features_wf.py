"""
probe_quarter_features_wf.py — Walk-forward comparison for endQ3 quarter features expansion.

Compares WF Brier BEFORE and AFTER adding q1_usg_avg, halftime_pace_shift,
trailing_team_q4_usg_hhi to the endQ3 _SNAP_FEATURES.

Quarter features join: uses data/cache/quarter_features.parquet.
For games without a quarter_features row (~88% of dataset), the three new
features are NaN — LightGBM handles NaN natively via its missing-value splits.

SHIP gate: 3+/4 folds improve (Brier strictly lower in post vs pre).
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List, Any

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
OUT_JSON = os.path.join(DATA_CACHE, "probe_quarter_features_wf_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)


def load_linescores() -> Dict[str, Dict]:
    path = os.path.join(NBA_CACHE, "linescores_all.json")
    with open(path) as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    seasons = ["2022-23", "2023-24", "2024-25"]
    all_rows: Dict[str, Dict] = {}
    for s in seasons:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            print(f"  [WARN] missing {path}", flush=True)
            continue
        with open(path) as f:
            data = json.load(f)
        for row in data.get("rows", []):
            all_rows[row["game_id"]] = row
    return all_rows


def load_quarter_features_team_summary() -> Dict[str, Dict]:
    """Load quarter_features parquet and aggregate to team-level summaries per game.

    Returns dict keyed by "{game_id}_{team_id}" -> {q1_usg_avg, halftime_pace_shift,
    trailing_team_q4_usg_hhi}.
    """
    path = os.path.join(DATA_CACHE, "quarter_features.parquet")
    if not os.path.exists(path):
        print("  [WARN] quarter_features.parquet missing", flush=True)
        return {}
    df = pd.read_parquet(path)
    df["game_id"] = df["game_id"].astype(str)
    df["team_id"] = pd.to_numeric(df["team_id"], errors="coerce")

    summaries: Dict[str, Dict] = {}
    for (gid, tid), grp in df.groupby(["game_id", "team_id"]):
        key = f"{gid}_{int(tid)}"
        summaries[key] = {
            "q1_usg_avg": float(grp["q1_usg"].mean()),
            "halftime_pace_shift": float(grp["halftime_pace_shift"].mean()),
            "trailing_team_q4_usg_hhi": float(
                grp["trailing_team_q4_usg_concentration"].mean()
                if grp["trailing_team_q4_usg_concentration"].notna().any()
                else np.nan
            ),
        }
    print(f"  quarter_features team summaries: {len(summaries)} entries", flush=True)
    return summaries


MINUTES_PER_QUARTER = 12.0


def build_rows(linescores: Dict, season_games: Dict,
               quarter_summaries: Dict) -> pd.DataFrame:
    """Build one row per (game_id, snapshot) with base + quarter features."""
    records: List[Dict] = []

    for gid, ls in linescores.items():
        sg = season_games.get(gid)
        if sg is None:
            continue

        required_qs = ["home_q1", "home_q2", "home_q3", "home_q4",
                       "away_q1", "away_q2", "away_q3", "away_q4"]
        if any(ls.get(k) is None for k in required_qs):
            continue

        hq = [ls["home_q1"], ls["home_q2"], ls["home_q3"], ls["home_q4"]]
        aq = [ls["away_q1"], ls["away_q2"], ls["away_q3"], ls["away_q4"]]

        home_total = sum(hq)
        away_total = sum(aq)
        home_team_won = int(home_total > away_total)

        game_date = sg.get("game_date", "1900-01-01")
        home_team_id = ls.get("home_team_id", 0) or sg.get("home_team", "UNK")
        season = sg.get("season", "unknown")

        pregame_wp = sg.get("sim_win_prob")
        if pregame_wp is None:
            pregame_wp = 0.5

        # Quarter features lookup (NaN if not in parquet)
        try:
            htid_int = int(home_team_id)
        except (TypeError, ValueError):
            htid_int = 0
        qf_key = f"{gid}_{htid_int}"
        qf_row = quarter_summaries.get(qf_key, {})
        q1_usg_avg = qf_row.get("q1_usg_avg", np.nan)
        halftime_pace_shift = qf_row.get("halftime_pace_shift", np.nan)
        trailing_team_q4_usg_hhi = qf_row.get("trailing_team_q4_usg_hhi", np.nan)

        for snap_idx, snapshot in enumerate(["endQ1", "endQ2", "endQ3"]):
            n_qtrs = snap_idx + 1
            minutes_played = n_qtrs * MINUTES_PER_QUARTER

            h_cum = sum(hq[:n_qtrs])
            a_cum = sum(aq[:n_qtrs])
            total_pts = h_cum + a_cum

            if snapshot == "endQ3" and total_pts < 60:
                continue

            score_margin = h_cum - a_cum
            pace_so_far = total_pts / minutes_played

            q1_delta = hq[0] - aq[0]
            q2_delta = (hq[1] - aq[1]) if n_qtrs >= 2 else np.nan
            q3_delta = (hq[2] - aq[2]) if n_qtrs >= 3 else np.nan
            last_q_margin = hq[n_qtrs - 1] - aq[n_qtrs - 1]

            records.append({
                "game_id": gid,
                "game_date": game_date,
                "snapshot": snapshot,
                "home_team_id": home_team_id,
                "season": season,
                "score_margin": score_margin,
                "total_pts": total_pts,
                "pace_so_far": pace_so_far,
                "q1_delta": q1_delta,
                "q2_delta": q2_delta,
                "q3_delta": q3_delta,
                "last_q_margin": last_q_margin,
                "pregame_win_prob": pregame_wp,
                "home_team_won": home_team_won,
                # quarter features (NaN for unmatched games)
                "q1_usg_avg": q1_usg_avg,
                "halftime_pace_shift": halftime_pace_shift,
                "trailing_team_q4_usg_hhi": trailing_team_q4_usg_hhi,
            })

    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values("game_date").reset_index(drop=True)
    print(f"  Built {len(df)} snapshot rows from {df['game_id'].nunique()} games",
          flush=True)
    return df


BASE_FEATURES_ENDQ3 = [
    "score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
    "q3_delta", "last_q_margin", "pregame_win_prob", "home_team_id", "season",
]
EXPANDED_FEATURES_ENDQ3 = BASE_FEATURES_ENDQ3 + [
    "q1_usg_avg", "halftime_pace_shift", "trailing_team_q4_usg_hhi",
]
CAT_COLS = ["home_team_id", "season"]


def walk_forward_cv(X: pd.DataFrame, y: pd.Series,
                    n_folds: int = 4) -> List[Dict[str, float]]:
    import lightgbm as lgb
    from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score

    n = len(X)
    min_train = int(n * 0.60)
    test_size = (n - min_train) // n_folds

    fold_results = []
    for fold in range(n_folds):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < n_folds - 1 else n

        if train_end < 30 or test_start >= n:
            continue

        X_tr = X.iloc[:train_end].copy()
        y_tr = y.iloc[:train_end]
        X_te = X.iloc[test_start:test_end].copy()
        y_te = y.iloc[test_start:test_end]

        if len(X_te) < 10:
            continue

        cat_cols = [c for c in CAT_COLS if c in X_tr.columns]
        for c in cat_cols:
            X_tr[c] = X_tr[c].astype("category")
            X_te[c] = X_te[c].astype("category")

        model = lgb.LGBMClassifier(
            n_estimators=300,
            learning_rate=0.05,
            num_leaves=31,
            min_child_samples=20,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=4,
            verbose=-1,
        )
        model.fit(X_tr, y_tr,
                  categorical_feature=cat_cols if cat_cols else "auto")

        probs = model.predict_proba(X_te)[:, 1]
        preds = (probs >= 0.5).astype(int)

        fold_results.append({
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "brier": float(brier_score_loss(y_te, probs)),
            "accuracy": float(accuracy_score(y_te, preds)),
            "auc": float(roc_auc_score(y_te, probs)),
        })
        print(f"    fold {fold}: train={len(X_tr)}, test={len(X_te)}, "
              f"Brier={fold_results[-1]['brier']:.4f}, "
              f"Acc={fold_results[-1]['accuracy']:.4f}", flush=True)

    return fold_results


def run_wf(df: pd.DataFrame, label: str,
           features: List[str]) -> List[Dict]:
    print(f"\n  [{label}] endQ3 walk-forward CV with {len(features)} features",
          flush=True)
    sub = df[df["snapshot"] == "endQ3"].copy()
    X = sub[features].copy()
    y = sub["home_team_won"].copy()
    print(f"    rows={len(sub)}, home_win_rate={y.mean():.3f}", flush=True)
    return walk_forward_cv(X, y, n_folds=4)


def main() -> None:
    t0 = time.time()
    print("=== probe_quarter_features_wf: endQ3 quarter-features expansion ===",
          flush=True)

    print("\n[1] Loading data ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    quarter_summaries = load_quarter_features_team_summary()
    print(f"  linescores={len(linescores)}, season_games={len(season_games)}",
          flush=True)

    print("\n[2] Building rows ...", flush=True)
    df = build_rows(linescores, season_games, quarter_summaries)

    # Filter to games that pass endQ3 constraint
    valid_games = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid_games)].copy()
    n_endq3 = len(df[df["snapshot"] == "endQ3"])
    qf_coverage = (
        df[df["snapshot"] == "endQ3"]["q1_usg_avg"].notna().sum()
    )
    print(f"  endQ3 rows: {n_endq3}, quarter_features coverage: "
          f"{qf_coverage}/{n_endq3} ({100*qf_coverage/n_endq3:.1f}%)", flush=True)

    # PRE: baseline features (no quarter features)
    print("\n[3] PRE-change walk-forward (baseline features) ...", flush=True)
    pre_folds = run_wf(df, "PRE", BASE_FEATURES_ENDQ3)
    pre_briers = [r["brier"] for r in pre_folds]

    # POST: expanded features (with quarter features)
    print("\n[4] POST-change walk-forward (+ quarter features) ...", flush=True)
    post_folds = run_wf(df, "POST", EXPANDED_FEATURES_ENDQ3)
    post_briers = [r["brier"] for r in post_folds]

    # Compare
    print("\n[5] Comparison ...", flush=True)
    deltas = [post_briers[i] - pre_briers[i] for i in range(len(pre_briers))]
    improved = sum(1 for d in deltas if d < 0)
    n_folds = len(pre_briers)
    ship = improved >= 3

    print(f"\n{'='*55}", flush=True)
    print(f"  {'Fold':<6} {'PRE Brier':<12} {'POST Brier':<12} {'Delta':<10} Result",
          flush=True)
    for i, (pre, post, delta) in enumerate(zip(pre_briers, post_briers, deltas)):
        result = "IMPROVE" if delta < 0 else "REGRESS"
        print(f"  {i:<6} {pre:<12.4f} {post:<12.4f} {delta:+.4f}    {result}",
              flush=True)
    print(f"\n  PRE  mean Brier: {np.mean(pre_briers):.4f}", flush=True)
    print(f"  POST mean Brier: {np.mean(post_briers):.4f}", flush=True)
    print(f"  Mean delta:      {np.mean(deltas):+.4f}", flush=True)
    print(f"  Folds improved:  {improved}/{n_folds}", flush=True)
    print(f"\n  DECISION: {'SHIP' if ship else 'REVERT'} "
          f"({'3+/4 folds improved' if ship else 'less than 3/4 folds improved'})",
          flush=True)

    elapsed = time.time() - t0

    result = {
        "probe": "quarter_features_expansion_endq3",
        "decision": "SHIP" if ship else "REVERT",
        "folds_improved": improved,
        "n_folds": n_folds,
        "pre_briers": pre_briers,
        "post_briers": post_briers,
        "deltas": deltas,
        "pre_mean_brier": float(np.mean(pre_briers)),
        "post_mean_brier": float(np.mean(post_briers)),
        "mean_delta": float(np.mean(deltas)),
        "qf_coverage_pct": float(100 * qf_coverage / n_endq3) if n_endq3 > 0 else 0.0,
        "base_features": BASE_FEATURES_ENDQ3,
        "expanded_features": EXPANDED_FEATURES_ENDQ3,
        "elapsed_s": float(elapsed),
        "pre_folds_detail": pre_folds,
        "post_folds_detail": post_folds,
    }

    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n  Results saved to: {OUT_JSON}", flush=True)
    print(f"  Elapsed: {elapsed:.1f}s", flush=True)


if __name__ == "__main__":
    main()
