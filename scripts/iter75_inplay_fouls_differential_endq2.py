"""
iter75_inplay_fouls_differential_endq2.py
─────────────────────────────────────────
Iter 75: RETRY of Iter 65 foul-trouble features for endQ2 — using DIFFERENTIAL
(home - away) instead of absolute counts.

Hypothesis
----------
Iter 65 shipped at endQ3 (-0.0021 Brier) but REVERTED at endQ2 (+0.0012 — too
early, subs absorb the absolute signal). Halftime fouls are confounded by game
pace (high-foul pace produces high counts on BOTH teams). Differentials are
scale-invariant — they isolate the imbalance signal that actually moves Q3/Q4
win prob.

New features (endQ2 only)
-------------------------
  • pf_imbalance               = home_team_pfs_cum   - away_team_pfs_cum
  • top_pf_imbalance           = home_max_player_pfs - away_max_player_pfs
  • foul_pressure_imbalance    = home_starter_fouled_out_indicator
                                  - away_starter_fouled_out_indicator
                                  (∈ {-1, 0, 1})

These REPLACE Iter-65's absolute features (those are Iter 65's domain). One row
per game with the 3 differentials at endQ2.

Approach
--------
1. REUSE `data/cache/inplay_foul_state.parquet` from Iter 65 (already has
   absolute counts; we derive differentials from it). Filter to period==2.
2. Save as `data/cache/inplay_foul_state_differential.parquet` (endQ2 only).
3. Build endQ2 baseline feature matrix exactly like Iter 68's `build_rows`.
4. Train v10_fouls_diff endQ2 model with Iter 68 winning HPs
   (lr=0.03, num_leaves=15, min_child_samples=40) on baseline 9 features
   + the 3 differential features (12 total).
5. WF 4-fold split, compare vs v6_hp endQ2 baseline (0.1771).

Ship gate
---------
≥3/4 folds improved AND mean Brier delta ≤ -0.002 vs v6_hp endQ2 baseline.

Files written
-------------
  • data/cache/inplay_foul_state_differential.parquet            (always)
  • data/models/inplay_winprob_endq2_v10_fouls_diff.lgb          (only if winner)
  • data/models/inplay_winprob_endq2_v10_fouls_diff_meta.json    (only if winner)
  • data/cache/iter75_inplay_fouls_diff_results.json             (always)
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODEL_DIR = os.path.join(PROJECT, "data", "models")

FOUL_ABS_PARQUET = os.path.join(DATA_CACHE, "inplay_foul_state.parquet")
FOUL_DIFF_PARQUET = os.path.join(DATA_CACHE,
                                 "inplay_foul_state_differential.parquet")
OUT_JSON = os.path.join(DATA_CACHE, "iter75_inplay_fouls_diff_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

SNAPSHOT = "endQ2"
N_FOLDS = 4
SEED = 42

# Iter 65 absolute-count column names (from data/cache/inplay_foul_state.parquet)
ABS_COLS = [
    "home_team_pfs_cum",
    "away_team_pfs_cum",
    "home_max_player_pfs",
    "away_max_player_pfs",
    "home_starter_fouled_out_indicator",
    "away_starter_fouled_out_indicator",
]

# The 3 new differential features
DIFF_COLS = [
    "pf_imbalance",
    "top_pf_imbalance",
    "foul_pressure_imbalance",
]

# v6_hp endQ2 WF baseline (from the v6_hp _meta.json wf_eval.mean_brier)
V6_HP_ENDQ2_BASELINE = 0.17707220148808006

MINUTES_PER_QUARTER = 12.0


# ── differential cache build (from Iter 65 absolute cache) ───────────────────

def build_differential_cache() -> pd.DataFrame:
    """Read Iter 65 absolute foul-state cache, compute 3 differentials, save
    endQ2-only parquet.
    """
    if not os.path.exists(FOUL_ABS_PARQUET):
        raise RuntimeError(
            f"Iter 65 foul-state cache not found at {FOUL_ABS_PARQUET}. "
            "Re-run scripts/iter65_inplay_foul_trouble.py first."
        )

    abs_df = pd.read_parquet(FOUL_ABS_PARQUET)
    abs_df["game_id"] = abs_df["game_id"].astype(str)

    # endQ2 ↔ period == 2
    q2 = abs_df[abs_df["period"] == 2].copy().reset_index(drop=True)

    # Sanity: all required absolute columns present
    missing = [c for c in ABS_COLS if c not in q2.columns]
    if missing:
        raise RuntimeError(f"Iter 65 cache missing columns: {missing}")

    diff = pd.DataFrame({
        "game_id": q2["game_id"].astype(str),
        "period": q2["period"].astype(int),
        "pf_imbalance": (
            q2["home_team_pfs_cum"] - q2["away_team_pfs_cum"]
        ).astype(float),
        "top_pf_imbalance": (
            q2["home_max_player_pfs"] - q2["away_max_player_pfs"]
        ).astype(float),
        "foul_pressure_imbalance": (
            q2["home_starter_fouled_out_indicator"]
            - q2["away_starter_fouled_out_indicator"]
        ).astype(float),
    })

    # Save endQ2-only differentials
    diff.to_parquet(FOUL_DIFF_PARQUET, index=False)
    print(f"  wrote {FOUL_DIFF_PARQUET} ({len(diff)} rows)", flush=True)
    print(f"  pf_imbalance range:               "
          f"[{diff['pf_imbalance'].min():.1f}, {diff['pf_imbalance'].max():.1f}]"
          f"  mean={diff['pf_imbalance'].mean():.2f}",
          flush=True)
    print(f"  top_pf_imbalance range:           "
          f"[{diff['top_pf_imbalance'].min():.1f}, "
          f"{diff['top_pf_imbalance'].max():.1f}]"
          f"  mean={diff['top_pf_imbalance'].mean():.2f}",
          flush=True)
    print(f"  foul_pressure_imbalance value counts: "
          f"{diff['foul_pressure_imbalance'].value_counts().to_dict()}",
          flush=True)
    return diff


# ── data loaders (mirror Iter 68 exactly) ────────────────────────────────────

def load_linescores() -> Dict[str, Dict]:
    with open(os.path.join(NBA_CACHE, "linescores_all.json")) as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    seasons = ["2022-23", "2023-24", "2024-25"]
    rows: Dict[str, Dict] = {}
    for s in seasons:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            print(f"  [WARN] missing {path}", flush=True)
            continue
        with open(path) as f:
            data = json.load(f)
        for r in data.get("rows", []):
            rows[r["game_id"]] = r
    return rows


def load_quarter_features_summaries() -> Dict[str, Dict[str, float]]:
    path = os.path.join(DATA_CACHE, "quarter_features.parquet")
    if not os.path.exists(path):
        return {}
    df = pd.read_parquet(path)
    df["game_id"] = df["game_id"].astype(str)
    df["team_id"] = pd.to_numeric(df["team_id"], errors="coerce")
    summaries: Dict[str, Dict[str, float]] = {}
    for (gid, tid), grp in df.groupby(["game_id", "team_id"]):
        key = f"{gid}_{int(tid)}"
        ttq4 = grp["trailing_team_q4_usg_concentration"]
        summaries[key] = {
            "q1_usg_avg": float(grp["q1_usg"].mean()),
            "halftime_pace_shift": float(grp["halftime_pace_shift"].mean()),
            "trailing_team_q4_usg_hhi": float(ttq4.mean())
            if ttq4.notna().any() else float("nan"),
        }
    return summaries


def _pregame_wp_from_sg(sg: Dict) -> float:
    wp = sg.get("sim_win_prob")
    if wp is not None:
        return float(wp)
    hca = 65.0
    home_elo = sg.get("home_elo")
    away_elo = sg.get("away_elo")
    if home_elo is None or away_elo is None:
        return 0.55
    try:
        diff = float(home_elo) - float(away_elo) + hca
        return float(1.0 / (1.0 + 10.0 ** (-diff / 400.0)))
    except (TypeError, ValueError):
        return 0.55


# ── row construction (endQ2 only) ────────────────────────────────────────────

def build_endq2_rows(
    linescores: Dict,
    season_games: Dict,
    qf_summaries: Dict[str, Dict[str, float]],
    diff_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build endQ2 snapshot rows mirroring Iter 68 build_rows, joined with the
    3 differential features. ONE row per game.
    """
    # Build lookup keyed by game_id
    diff_lookup: Dict[str, Dict[str, float]] = {}
    for _, r in diff_df.iterrows():
        diff_lookup[str(r["game_id"])] = {c: float(r[c]) for c in DIFF_COLS}

    required = ["home_q1", "home_q2", "home_q3", "home_q4",
                "away_q1", "away_q2", "away_q3", "away_q4"]
    records: List[Dict] = []
    for gid, ls in linescores.items():
        sg = season_games.get(gid)
        if sg is None:
            continue
        if any(ls.get(k) is None for k in required):
            continue

        hq = [ls["home_q1"], ls["home_q2"], ls["home_q3"], ls["home_q4"]]
        aq = [ls["away_q1"], ls["away_q2"], ls["away_q3"], ls["away_q4"]]
        home_total = sum(hq)
        away_total = sum(aq)
        home_team_won = int(home_total > away_total)
        game_date = sg.get("game_date", "1900-01-01")
        home_team_id = ls.get("home_team_id", 0) or sg.get("home_team", "UNK")
        season = sg.get("season", "unknown")
        pregame_wp = _pregame_wp_from_sg(sg)

        try:
            htid_int = int(home_team_id)
        except (TypeError, ValueError):
            htid_int = 0
        qf_row = qf_summaries.get(f"{gid}_{htid_int}", {})
        # NOTE: v6_hp baseline at endQ2 does NOT use quarter_features (see meta);
        # we still load them for parity with Iter 68 but they're unused here.

        # endQ2 only: 2 quarters played
        n_qtrs = 2
        minutes_played = n_qtrs * MINUTES_PER_QUARTER
        h_cum = sum(hq[:n_qtrs])
        a_cum = sum(aq[:n_qtrs])
        total_pts = h_cum + a_cum
        score_margin = h_cum - a_cum
        pace_so_far = total_pts / minutes_played
        q1_delta = hq[0] - aq[0]
        q2_delta = hq[1] - aq[1]
        last_q_margin = hq[n_qtrs - 1] - aq[n_qtrs - 1]

        diffs = diff_lookup.get(str(gid), {})

        rec = {
            "game_id": str(gid),
            "game_date": game_date,
            "snapshot": "endQ2",
            "home_team_id": home_team_id,
            "season": season,
            "score_margin": score_margin,
            "total_pts": total_pts,
            "pace_so_far": pace_so_far,
            "q1_delta": q1_delta,
            "q2_delta": q2_delta,
            "last_q_margin": last_q_margin,
            "pregame_win_prob": pregame_wp,
            "home_team_won": home_team_won,
            "has_foul_diff": int(bool(diffs)),
        }
        for c in DIFF_COLS:
            rec[c] = diffs.get(c, np.nan)
        records.append(rec)

    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    return df


# ── walk-forward CV ──────────────────────────────────────────────────────────

def walk_forward(
    df_snap: pd.DataFrame,
    feature_cols: List[str],
    cat_cols: List[str],
    hp: Dict[str, Any],
) -> List[Dict[str, Any]]:
    import lightgbm as lgb
    from sklearn.metrics import (accuracy_score, brier_score_loss,
                                 log_loss, roc_auc_score)
    n = len(df_snap)
    min_train = int(n * 0.60)
    test_size = (n - min_train) // N_FOLDS
    out: List[Dict[str, Any]] = []
    for fold in range(N_FOLDS):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < N_FOLDS - 1 else n
        if train_end < 30 or test_start >= n:
            continue
        X_tr = df_snap[feature_cols].iloc[:train_end].copy()
        y_tr = df_snap["home_team_won"].iloc[:train_end]
        X_te = df_snap[feature_cols].iloc[test_start:test_end].copy()
        y_te = df_snap["home_team_won"].iloc[test_start:test_end]
        if len(X_te) < 10:
            continue
        active_cats = [c for c in cat_cols if c in X_tr.columns]
        for c in active_cats:
            X_tr[c] = X_tr[c].astype("category")
            X_te[c] = X_te[c].astype("category")
        model = lgb.LGBMClassifier(
            n_estimators=int(hp.get("n_estimators", 300)),
            learning_rate=float(hp.get("learning_rate", 0.03)),
            num_leaves=int(hp.get("num_leaves", 15)),
            min_child_samples=int(hp.get("min_child_samples", 40)),
            subsample=float(hp.get("subsample", 0.8)),
            colsample_bytree=float(hp.get("colsample_bytree", 0.8)),
            reg_alpha=float(hp.get("reg_alpha", 0.1)),
            reg_lambda=float(hp.get("reg_lambda", 1.0)),
            random_state=int(hp.get("random_state", SEED)),
            n_jobs=4,
            verbose=-1,
        )
        model.fit(X_tr, y_tr,
                  categorical_feature=active_cats if active_cats else "auto")
        probs = model.predict_proba(X_te)[:, 1]
        preds = (probs >= 0.5).astype(int)
        probs_safe = np.clip(probs, 1e-6, 1 - 1e-6)
        y_arr = y_te.values
        try:
            auc = float(roc_auc_score(y_arr, probs))
        except ValueError:
            auc = float("nan")
        out.append({
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "brier": float(brier_score_loss(y_arr, probs)),
            "log_loss": float(log_loss(y_arr, probs_safe)),
            "auc": auc,
            "accuracy": float(accuracy_score(y_arr, preds)),
        })
    return out


# ── full-data train + integrity check (only on ship) ─────────────────────────

def train_full_and_save(
    df_snap: pd.DataFrame,
    feature_cols: List[str],
    cat_cols: List[str],
    hp: Dict[str, Any],
    wf_summary: Dict[str, Any],
) -> Dict[str, Any]:
    import lightgbm as lgb
    from sklearn.metrics import (accuracy_score, brier_score_loss,
                                 log_loss, roc_auc_score)
    X = df_snap[feature_cols].copy()
    y = df_snap["home_team_won"]
    active_cats = [c for c in cat_cols if c in X.columns]
    for c in active_cats:
        X[c] = X[c].astype("category")
    model = lgb.LGBMClassifier(
        n_estimators=int(hp.get("n_estimators", 300)),
        learning_rate=float(hp.get("learning_rate", 0.03)),
        num_leaves=int(hp.get("num_leaves", 15)),
        min_child_samples=int(hp.get("min_child_samples", 40)),
        subsample=float(hp.get("subsample", 0.8)),
        colsample_bytree=float(hp.get("colsample_bytree", 0.8)),
        reg_alpha=float(hp.get("reg_alpha", 0.1)),
        reg_lambda=float(hp.get("reg_lambda", 1.0)),
        random_state=int(hp.get("random_state", SEED)),
        n_jobs=4,
        verbose=-1,
    )
    model.fit(X, y, categorical_feature=active_cats if active_cats else "auto")
    probs = model.predict_proba(X)[:, 1]
    preds = (probs >= 0.5).astype(int)
    probs_safe = np.clip(probs, 1e-6, 1 - 1e-6)
    in_sample = {
        "auc": float(roc_auc_score(y, probs)) if len(np.unique(y)) > 1
        else float("nan"),
        "brier": float(brier_score_loss(y, probs)),
        "log_loss": float(log_loss(y, probs_safe)),
        "accuracy": float(accuracy_score(y, preds)),
    }

    out_lgb = os.path.join(MODEL_DIR,
                           "inplay_winprob_endq2_v10_fouls_diff.lgb")
    out_meta = os.path.join(MODEL_DIR,
                            "inplay_winprob_endq2_v10_fouls_diff_meta.json")

    booster = model.booster_
    booster.save_model(out_lgb)

    # pkl integrity check
    reloaded = lgb.Booster(model_file=out_lgb)
    probs_reload = reloaded.predict(X)
    max_diff = float(np.abs(probs - probs_reload).max())
    n_features_in = int(model.n_features_in_)
    booster_n_features = int(reloaded.num_feature())
    integrity_ok = (
        max_diff < 1e-6
        and n_features_in == len(feature_cols)
        and booster_n_features == len(feature_cols)
    )
    if not integrity_ok:
        try:
            os.remove(out_lgb)
        except OSError:
            pass
        raise RuntimeError(
            f"[INTEGRITY FAIL] endQ2 v10_fouls_diff: max_diff={max_diff:.6f} "
            f"n_features_in={n_features_in} "
            f"booster_n_features={booster_n_features} "
            f"vs feature_cols_len={len(feature_cols)}"
        )

    meta = {
        "snapshot": "endQ2",
        "variant": "v10_fouls_diff",
        "iter": "iter75",
        "feature_cols": feature_cols,
        "categorical_cols": cat_cols,
        "n_train_rows": int(len(X)),
        "n_features_in_": n_features_in,
        "home_win_rate": float(y.mean()),
        "in_sample": in_sample,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe": "iter75_inplay_fouls_differential_endq2",
        "parent_meta": "inplay_winprob_endq2_v6_hp_meta.json",
        "hyperparams": hp,
        "wf_eval": wf_summary,
        "integrity": {
            "max_prob_diff_pkl_vs_inmemory": max_diff,
            "n_features_in": n_features_in,
            "booster_num_feature": booster_n_features,
            "ok": integrity_ok,
        },
    }
    with open(out_meta, "w") as f:
        json.dump(meta, f, indent=2, default=str)
    print(f"    saved {out_lgb}", flush=True)
    print(f"    saved {out_meta}", flush=True)
    print(f"    integrity OK: max_prob_diff={max_diff:.2e}, "
          f"n_features_in={n_features_in}", flush=True)
    return meta


# ── orchestrator ─────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== iter75: foul-DIFFERENTIAL features for endQ2 inplay winprob ===",
          flush=True)
    print(f"  random_seed={SEED}, n_folds={N_FOLDS}", flush=True)
    print(f"  v6_hp endQ2 WF baseline: {V6_HP_ENDQ2_BASELINE:.6f}", flush=True)

    # [1] Build differential cache from Iter 65 absolute cache
    print("\n[1] Building differential foul-state cache "
          "(from Iter 65 absolute cache) ...", flush=True)
    diff_df = build_differential_cache()
    n_games_diff = diff_df["game_id"].nunique()
    print(f"    unique games with endQ2 foul-differential state: {n_games_diff}",
          flush=True)

    # [2] Load data
    print("\n[2] Loading linescores + season_games ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    qf_summaries = load_quarter_features_summaries()
    print(f"    linescores={len(linescores)}, season_games={len(season_games)}",
          flush=True)

    # [3] Build endQ2 rows
    print("\n[3] Building endQ2 snapshot rows ...", flush=True)
    df = build_endq2_rows(linescores, season_games, qf_summaries, diff_df)
    print(f"    total endQ2 rows: {len(df)}", flush=True)
    n_covered = int((df["has_foul_diff"] == 1).sum())
    print(f"    rows with foul-differential present: {n_covered}", flush=True)

    # Restrict to rows where differential features are present (apples-to-apples)
    sub = df[df["has_foul_diff"] == 1].copy().reset_index(drop=True)
    print(f"    rows after foul-coverage filter: {len(sub)}", flush=True)

    coverage_flag = "OK" if len(sub) >= 1500 else "INSUFFICIENT_COVERAGE"
    print(f"    coverage flag: {coverage_flag}", flush=True)

    # [4] Load v6_hp endQ2 meta — feature cols, cat cols, HPs
    v6_meta_path = os.path.join(
        MODEL_DIR, "inplay_winprob_endq2_v6_hp_meta.json")
    with open(v6_meta_path) as f:
        v6_meta = json.load(f)
    base_features = list(v6_meta["feature_cols"])
    cat_cols = list(v6_meta.get("categorical_cols", []))
    hp = dict(v6_meta.get("hyperparams", {}))

    v10_features = base_features + DIFF_COLS
    print(f"\n[4] v6_hp baseline features ({len(base_features)}): "
          f"{base_features}", flush=True)
    print(f"    v10_fouls_diff features ({len(v10_features)}) = "
          f"baseline + {len(DIFF_COLS)} differential features: {DIFF_COLS}",
          flush=True)
    print(f"    HPs: lr={hp.get('learning_rate')}, "
          f"num_leaves={hp.get('num_leaves')}, "
          f"min_child_samples={hp.get('min_child_samples')}", flush=True)

    results: Dict[str, Any] = {
        "iter": "iter75_inplay_fouls_differential_endq2",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "random_seed": SEED,
        "n_folds": N_FOLDS,
        "snapshot": SNAPSHOT,
        "coverage": {
            "n_games_with_diff": n_games_diff,
            "n_rows_total": int(len(df)),
            "n_rows_with_diff": n_covered,
            "n_rows_used": int(len(sub)),
            "flag": coverage_flag,
        },
        "v6_hp_baseline_mean_brier": V6_HP_ENDQ2_BASELINE,
        "feature_cols_v10": v10_features,
        "categorical_cols": cat_cols,
        "hyperparams": hp,
        "diff_cols": DIFF_COLS,
    }

    if coverage_flag == "INSUFFICIENT_COVERAGE":
        results["verdict"] = "REVERT"
        results["reason"] = (
            f"endQ2 foul-diff coverage {len(sub)} < 1500 — "
            "features not broadly enough available"
        )
        with open(OUT_JSON, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  REVERT: insufficient coverage. Saved to {OUT_JSON}",
              flush=True)
        return

    # [5] Re-fit baseline on this row ordering for apples-to-apples comparison
    print(f"\n[5] Re-fitting v6_hp BASELINE on this row ordering ...",
          flush=True)
    rebase_folds = walk_forward(sub, base_features, cat_cols, hp)
    rebase_briers = [f["brier"] for f in rebase_folds]
    rebase_mean = float(np.mean(rebase_briers)) if rebase_briers else float("nan")
    print(f"    BASELINE(refit) per-fold:  "
          f"{[f'{b:.4f}' for b in rebase_briers]}", flush=True)
    print(f"    BASELINE(refit) mean:      {rebase_mean:.4f}", flush=True)

    # [6] WF on v10_fouls_diff
    print(f"\n[6] Training V10_FOULS_DIFF walk-forward ...", flush=True)
    v10_folds = walk_forward(sub, v10_features, cat_cols, hp)
    v10_briers = [f["brier"] for f in v10_folds]
    v10_mean = float(np.mean(v10_briers)) if v10_briers else float("nan")
    print(f"    V10_FOULS_DIFF per-fold Brier:  "
          f"{[f'{b:.4f}' for b in v10_briers]}", flush=True)
    print(f"    V10_FOULS_DIFF mean Brier:      {v10_mean:.4f}", flush=True)

    deltas = [v - b for v, b in zip(v10_briers, rebase_briers)]
    mean_delta = float(np.mean(deltas)) if deltas else float("nan")
    improved = sum(1 for d in deltas if d < 0)
    print(f"    DELTA v10-rebase per-fold:  "
          f"{[f'{d:+.4f}' for d in deltas]}", flush=True)
    print(f"    DELTA mean: {mean_delta:+.4f}  "
          f"folds_improved={improved}/{len(deltas)}", flush=True)

    # Also report delta vs *frozen* v6_hp baseline (sanity check)
    delta_vs_frozen = v10_mean - V6_HP_ENDQ2_BASELINE
    print(f"    Delta vs frozen v6_hp baseline ({V6_HP_ENDQ2_BASELINE:.4f}): "
          f"{delta_vs_frozen:+.4f}", flush=True)

    ship = improved >= 3 and mean_delta <= -0.002
    print(f"\n    SHIP? folds_improved={improved}/4 (need >=3), "
          f"mean_delta={mean_delta:+.4f} (need <=-0.002)  ->  "
          f"{'YES' if ship else 'no'}", flush=True)

    wf_summary = {
        "fold_briers_v10": v10_briers,
        "fold_briers_rebaseline": rebase_briers,
        "mean_brier_v10": v10_mean,
        "mean_brier_rebaseline": rebase_mean,
        "mean_brier_delta_vs_rebaseline": mean_delta,
        "mean_brier_delta_vs_frozen_v6hp": delta_vs_frozen,
        "deltas_per_fold": deltas,
        "n_folds_improved": improved,
        "n_folds": len(deltas),
        "fold_detail_v10": v10_folds,
        "fold_detail_rebaseline": rebase_folds,
    }

    results["wf_results"] = wf_summary
    results["ship_gate"] = {
        "min_folds_improved": 3,
        "max_mean_delta": -0.002,
        "passed": ship,
    }

    if ship:
        print(f"\n[7] SHIP — training v10_fouls_diff endQ2 on FULL data "
              "+ integrity check ...", flush=True)
        train_meta = train_full_and_save(
            sub, v10_features, cat_cols, hp, wf_summary,
        )
        results["verdict"] = "SHIP"
        results["reason"] = (
            f"endQ2 v10_fouls_diff passed ship gate: "
            f"folds_improved={improved}/4, mean_delta={mean_delta:+.4f}"
        )
        results["saved_lgb"] = train_meta["integrity"]
    else:
        results["verdict"] = "REVERT"
        results["reason"] = (
            f"endQ2 v10_fouls_diff failed ship gate: "
            f"folds_improved={improved}/4, mean_delta={mean_delta:+.4f}"
        )
        # Make absolutely sure no v10_fouls_diff artefacts exist on revert
        for sfx in (".lgb", "_meta.json"):
            p = os.path.join(MODEL_DIR,
                             f"inplay_winprob_endq2_v10_fouls_diff{sfx}")
            if os.path.exists(p):
                try:
                    os.remove(p)
                    print(f"  removed stale {p}", flush=True)
                except OSError:
                    pass

    results["elapsed_s"] = float(time.time() - t0)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n" + "=" * 70, flush=True)
    print(f"ITER 75 VERDICT: {results['verdict']}", flush=True)
    print(f"Reason: {results['reason']}", flush=True)
    print("=" * 70, flush=True)
    print(f"  endQ2 v6_hp baseline (frozen): {V6_HP_ENDQ2_BASELINE:.4f}",
          flush=True)
    print(f"  endQ2 v6_hp baseline (refit):  {rebase_mean:.4f}", flush=True)
    print(f"  endQ2 v10_fouls_diff:          {v10_mean:.4f}", flush=True)
    print(f"  Mean delta vs refit baseline:  {mean_delta:+.4f}", flush=True)
    print(f"  Folds improved:                {improved}/{len(deltas)}",
          flush=True)
    print(f"  Per-fold deltas:               "
          f"{[f'{d:+.4f}' for d in deltas]}", flush=True)
    print(f"  Elapsed: {results['elapsed_s']:.1f}s", flush=True)
    print(f"  Results: {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
