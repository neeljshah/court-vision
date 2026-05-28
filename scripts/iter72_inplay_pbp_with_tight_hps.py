"""
iter72_inplay_pbp_with_tight_hps.py
───────────────────────────────────
Iter 72: RETRY of Iter 64 (PBP microstructure features for inplay winprob) with
Iter 68's WINNING tight-regularization hyperparameters. Hypothesis: Iter 64
reverted because the default HPs (lr=0.05, num_leaves=31, min_child_samples=20)
were OVERFITTING the new microstructure features. Tighter trees from Iter 68
should let the PBP signal show through.

WINNING HPs per snapshot (from Iter 68 _v6_hp_meta.json):
  endQ1: lr=0.03, num_leaves=15, min_child_samples=40
  endQ2: lr=0.03, num_leaves=15, min_child_samples=40
  endQ3: lr=0.03, num_leaves=15, min_child_samples=10

PBP microstructure features added (10, from Iter 64):
  home_run_last_240s, away_run_last_240s
  home_pts_last_120s, away_pts_last_120s
  home_to_last_quarter, away_to_last_quarter
  home_ft_trips_last_quarter, away_ft_trips_last_quarter
  lead_changes_last_quarter, last_event_type_scoring

PBP parquet at data/cache/inplay_pbp_microstructure.parquet must already exist
(from Iter 64). This script never rebuilds it.

Baselines (v6_hp WF mean Brier, single-model, NOT meta-blend):
  endQ1: 0.2120
  endQ2: 0.1771
  endQ3: 0.1250

Ship gate (per snapshot):
  >=3/4 folds improved AND mean Brier delta <= -0.002 vs v6_hp single-model baseline.

DO NOT TOUCH any existing .lgb/_meta.json/joblib/meta_blend file.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List

import numpy as np
import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODELS_DIR = os.path.join(PROJECT, "data", "models")
MICRO_PARQUET = os.path.join(DATA_CACHE, "inplay_pbp_microstructure.parquet")
OUT_JSON = os.path.join(DATA_CACHE, "iter72_inplay_pbp_tight_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)

SNAPSHOTS = ["endQ1", "endQ2", "endQ3"]
N_FOLDS = 4
RANDOM_SEED = 42

MINUTES_PER_QUARTER = 12.0

# Iter 68 winning HPs (override on top of base meta hyperparams).
TIGHT_HP: Dict[str, Dict[str, Any]] = {
    "endQ1": {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 40},
    "endQ2": {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 40},
    "endQ3": {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 10},
}

# v6_hp single-model WF mean Brier baseline (must beat by >= 0.002).
V6_BASELINE_BRIER: Dict[str, float] = {
    "endQ1": 0.2120,
    "endQ2": 0.1771,
    "endQ3": 0.1250,
}

# PBP microstructure columns (added on top of v6_hp base features).
MICRO_COLS = [
    "home_run_last_240s", "away_run_last_240s",
    "home_pts_last_120s", "away_pts_last_120s",
    "home_to_last_quarter", "away_to_last_quarter",
    "home_ft_trips_last_quarter", "away_ft_trips_last_quarter",
    "lead_changes_last_quarter", "last_event_type_scoring",
]

SHIP_MIN_FOLDS_IMPROVED = 3
SHIP_MEAN_DELTA_MAX = -0.002


# ── data loaders (match Iter 64 / Iter 68 exactly) ────────────────────────────

def load_meta(snapshot: str) -> Dict[str, Any]:
    """Load v6_hp meta (NOT the prod meta) — features+HPs for tight retry."""
    path = os.path.join(
        MODELS_DIR, f"inplay_winprob_{snapshot.lower()}_v6_hp_meta.json"
    )
    with open(path) as f:
        return json.load(f)


def load_linescores() -> Dict[str, Dict]:
    with open(os.path.join(NBA_CACHE, "linescores_all.json")) as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    seasons = ["2022-23", "2023-24", "2024-25"]
    all_rows: Dict[str, Dict] = {}
    for s in seasons:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for row in data.get("rows", []):
            all_rows[row["game_id"]] = row
    return all_rows


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
        summaries[key] = {
            "q1_usg_avg": float(grp["q1_usg"].mean()),
            "halftime_pace_shift": float(grp["halftime_pace_shift"].mean()),
            "trailing_team_q4_usg_hhi": float(
                grp["trailing_team_q4_usg_concentration"].mean()
                if grp["trailing_team_q4_usg_concentration"].notna().any()
                else np.nan
            ),
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


def load_micro_df() -> pd.DataFrame:
    """Load the Iter 64 PBP microstructure parquet (must exist)."""
    if not os.path.exists(MICRO_PARQUET):
        raise FileNotFoundError(
            f"PBP microstructure parquet not found at {MICRO_PARQUET}. "
            f"Iter 64 must run first to build it."
        )
    df = pd.read_parquet(MICRO_PARQUET)
    df["game_id"] = df["game_id"].astype(str)
    return df


def build_rows_with_micro(
    linescores: Dict,
    season_games: Dict,
    qf_summaries: Dict[str, Dict[str, float]],
    micro_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build snapshot rows including micro features. Mirrors Iter 64 exactly."""
    micro_lookup: Dict = {}
    if not micro_df.empty:
        for _, r in micro_df.iterrows():
            key = (str(r["game_id"]), int(r["period"]))
            micro_lookup[key] = {
                c: float(r[c]) for c in micro_df.columns
                if c not in ("game_id", "period")
            }

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
        pregame_wp = _pregame_wp_from_sg(sg)
        try:
            htid_int = int(home_team_id)
        except (TypeError, ValueError):
            htid_int = 0
        qf_row = qf_summaries.get(f"{gid}_{htid_int}", {})
        q1_usg_avg = qf_row.get("q1_usg_avg", np.nan)
        halftime_pace_shift = qf_row.get("halftime_pace_shift", np.nan)
        trailing_team_q4_usg_hhi = qf_row.get("trailing_team_q4_usg_hhi", np.nan)

        for snap_idx, snapshot in enumerate(SNAPSHOTS):
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

            micro = micro_lookup.get((str(gid), n_qtrs), {})

            rec = {
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
                "q1_usg_avg": q1_usg_avg,
                "halftime_pace_shift": halftime_pace_shift,
                "trailing_team_q4_usg_hhi": trailing_team_q4_usg_hhi,
                "home_run_last_240s": micro.get("home_run_last_240s", np.nan),
                "away_run_last_240s": micro.get("away_run_last_240s", np.nan),
                "home_pts_last_120s": micro.get("home_pts_last_120s", np.nan),
                "away_pts_last_120s": micro.get("away_pts_last_120s", np.nan),
                "home_to_last_quarter": micro.get("home_to_last_quarter", np.nan),
                "away_to_last_quarter": micro.get("away_to_last_quarter", np.nan),
                "home_ft_trips_last_quarter":
                    micro.get("home_ft_trips_last_quarter", np.nan),
                "away_ft_trips_last_quarter":
                    micro.get("away_ft_trips_last_quarter", np.nan),
                "lead_changes_last_quarter":
                    micro.get("lead_changes_last_quarter", np.nan),
                "last_event_type_scoring":
                    micro.get("last_event_type_scoring", np.nan),
                "has_micro": int(bool(micro)),
            }
            records.append(rec)
    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    return df


# ── walk-forward (4-fold expanding) ──────────────────────────────────────────

def walk_forward(
    df_snap: pd.DataFrame,
    feature_cols: List[str],
    cat_cols: List[str],
    hp: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Replicates the WF split from oos_validation_2026_05_27.json."""
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
            learning_rate=float(hp.get("learning_rate", 0.05)),
            num_leaves=int(hp.get("num_leaves", 31)),
            min_child_samples=int(hp.get("min_child_samples", 20)),
            subsample=float(hp.get("subsample", 0.8)),
            colsample_bytree=float(hp.get("colsample_bytree", 0.8)),
            reg_alpha=float(hp.get("reg_alpha", 0.1)),
            reg_lambda=float(hp.get("reg_lambda", 1.0)),
            random_state=int(hp.get("random_state", RANDOM_SEED)),
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


# ── train + save (only if winner) ────────────────────────────────────────────

def train_full_and_save(
    df_snap: pd.DataFrame,
    feature_cols: List[str],
    cat_cols: List[str],
    hp: Dict[str, Any],
    snapshot: str,
    wf_stats: Dict[str, Any],
) -> Dict[str, Any]:
    """Train on FULL data with the tight HPs + PBP features. Integrity-check."""
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
        learning_rate=float(hp.get("learning_rate", 0.05)),
        num_leaves=int(hp.get("num_leaves", 31)),
        min_child_samples=int(hp.get("min_child_samples", 20)),
        subsample=float(hp.get("subsample", 0.8)),
        colsample_bytree=float(hp.get("colsample_bytree", 0.8)),
        reg_alpha=float(hp.get("reg_alpha", 0.1)),
        reg_lambda=float(hp.get("reg_lambda", 1.0)),
        random_state=int(hp.get("random_state", RANDOM_SEED)),
        n_jobs=4,
        verbose=-1,
    )
    model.fit(X, y, categorical_feature=active_cats if active_cats else "auto")
    probs = model.predict_proba(X)[:, 1]
    preds = (probs >= 0.5).astype(int)
    probs_safe = np.clip(probs, 1e-6, 1 - 1e-6)
    in_sample = {
        "auc": float(roc_auc_score(y, probs)) if len(np.unique(y)) > 1 else float("nan"),
        "brier": float(brier_score_loss(y, probs)),
        "log_loss": float(log_loss(y, probs_safe)),
        "accuracy": float(accuracy_score(y, preds)),
    }

    out_lgb = os.path.join(
        MODELS_DIR, f"inplay_winprob_{snapshot.lower()}_v8_pbp_tight.lgb"
    )
    out_meta = os.path.join(
        MODELS_DIR, f"inplay_winprob_{snapshot.lower()}_v8_pbp_tight_meta.json"
    )
    booster = model.booster_
    booster.save_model(out_lgb)

    # ── pkl integrity check: reload booster, compare probs + verify n_features
    reloaded = lgb.Booster(model_file=out_lgb)
    probs_reload = reloaded.predict(X)
    max_diff = float(np.abs(probs - probs_reload).max())
    booster_n_features = int(reloaded.num_feature())
    n_features_in = int(model.n_features_in_)
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
            f"[INTEGRITY FAIL] {snapshot}: max_diff={max_diff:.6f} "
            f"n_features_in={n_features_in} booster_nfeat={booster_n_features} "
            f"vs feature_cols_len={len(feature_cols)}"
        )

    meta = {
        "snapshot": snapshot,
        "variant": "v8_pbp_tight",
        "iter": "iter72",
        "feature_cols": feature_cols,
        "categorical_cols": active_cats,
        "n_train_rows": int(len(X)),
        "n_features_in_": int(len(feature_cols)),
        "home_win_rate": float(y.mean()),
        "in_sample": in_sample,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe": "iter72_inplay_pbp_with_tight_hps",
        "parent_meta": f"inplay_winprob_{snapshot.lower()}_v6_hp_meta.json",
        "hyperparams": hp,
        "wf_eval": wf_stats,
        "integrity": {
            "max_prob_diff_pkl_vs_inmemory": max_diff,
            "n_features_in": n_features_in,
            "booster_n_features": booster_n_features,
            "ok": integrity_ok,
        },
    }
    with open(out_meta, "w") as f:
        json.dump(meta, f, indent=2, default=str)
    print(f"    saved {out_lgb}", flush=True)
    print(f"    saved {out_meta}", flush=True)
    print(f"    PKL integrity: max_diff={max_diff:.2e}, "
          f"n_features_in={n_features_in}, booster_nfeat={booster_n_features}",
          flush=True)
    return meta


# ── orchestrator ─────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== iter72: PBP microstructure + tight HPs (RETRY of Iter 64) ===",
          flush=True)
    print(f"  random_seed={RANDOM_SEED}", flush=True)
    print(f"  ship gate: >=3/4 folds improved AND mean delta <= -0.002 "
          f"vs v6_hp single-model baseline", flush=True)

    print("\n[1] Loading metas (v6_hp, READ-ONLY) ...", flush=True)
    metas = {snap: load_meta(snap) for snap in SNAPSHOTS}
    for snap, m in metas.items():
        print(f"    {snap}: {len(m['feature_cols'])} base features, "
              f"hp(lr/nl/mcs)=({m['hyperparams']['learning_rate']}/"
              f"{m['hyperparams']['num_leaves']}/"
              f"{m['hyperparams']['min_child_samples']})", flush=True)

    print("\n[2] Loading data ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    qf_summaries = load_quarter_features_summaries()
    print(f"    linescores={len(linescores)}, season_games={len(season_games)}, "
          f"qf_summaries={len(qf_summaries)}", flush=True)

    print("\n[3] Loading Iter 64 PBP microstructure parquet ...", flush=True)
    micro_df = load_micro_df()
    print(f"    micro_df rows: {len(micro_df)}, "
          f"unique games: {micro_df['game_id'].nunique()}", flush=True)

    print("\n[4] Building snapshot table with micro ...", flush=True)
    df = build_rows_with_micro(linescores, season_games, qf_summaries, micro_df)
    valid_games = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid_games)].copy().reset_index(drop=True)
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)

    n_games_full_micro = 0
    for gid, g in df.groupby("game_id"):
        if (g["has_micro"] == 1).sum() == 3:
            n_games_full_micro += 1
    print(f"    total snapshot rows: {len(df)}", flush=True)
    print(f"    games total: {df['game_id'].nunique()}", flush=True)
    print(f"    games with full micro on endQ1+Q2+Q3: {n_games_full_micro}",
          flush=True)

    results: Dict[str, Any] = {
        "iter": "iter72_inplay_pbp_with_tight_hps",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "random_seed": RANDOM_SEED,
        "n_folds": N_FOLDS,
        "tight_hps_used": TIGHT_HP,
        "v6_baseline_brier": V6_BASELINE_BRIER,
        "ship_gate": {
            "min_folds_improved": SHIP_MIN_FOLDS_IMPROVED,
            "max_mean_delta": SHIP_MEAN_DELTA_MAX,
        },
        "coverage": {
            "n_games_full_micro": n_games_full_micro,
            "n_games_total": int(df["game_id"].nunique()),
            "n_pbp_quarter_files_parsed": int(len(micro_df)),
        },
        "snapshots": {},
    }

    n_snaps_ship = 0
    for snapshot in SNAPSHOTS:
        print(f"\n[5] Snapshot {snapshot}", flush=True)
        meta = metas[snapshot]
        base_features = list(meta["feature_cols"])
        cat_cols = list(meta.get("categorical_cols", []))
        base_hp = dict(meta["hyperparams"])
        # Override with tight HPs
        hp = dict(base_hp)
        hp["learning_rate"] = TIGHT_HP[snapshot]["learning_rate"]
        hp["num_leaves"] = TIGHT_HP[snapshot]["num_leaves"]
        hp["min_child_samples"] = TIGHT_HP[snapshot]["min_child_samples"]

        v8_features = base_features + MICRO_COLS
        print(f"    base ({len(base_features)}) + micro ({len(MICRO_COLS)}) "
              f"= v8 ({len(v8_features)})", flush=True)
        print(f"    HPs: lr={hp['learning_rate']} nl={hp['num_leaves']} "
              f"mcs={hp['min_child_samples']}", flush=True)

        sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
        print(f"    rows: {len(sub)}", flush=True)

        # Refit v6_hp baseline on this row ordering for apples-to-apples
        print(f"    refit v6_hp baseline (same HPs, base features only) ...",
              flush=True)
        base_folds = walk_forward(sub, base_features, cat_cols, hp)
        base_briers = [f["brier"] for f in base_folds]
        base_mean = float(np.mean(base_briers)) if base_briers else float("nan")
        print(f"    v6_hp refit per-fold: {[f'{b:.4f}' for b in base_briers]}",
              flush=True)
        print(f"    v6_hp refit mean:     {base_mean:.4f} "
              f"(stored baseline {V6_BASELINE_BRIER[snapshot]:.4f})", flush=True)

        # v8 = base + micro under tight HPs
        print(f"    fit v8_pbp_tight WF ...", flush=True)
        v8_folds = walk_forward(sub, v8_features, cat_cols, hp)
        v8_briers = [f["brier"] for f in v8_folds]
        v8_mean = float(np.mean(v8_briers)) if v8_briers else float("nan")
        print(f"    v8 per-fold: {[f'{b:.4f}' for b in v8_briers]}", flush=True)
        print(f"    v8 mean:     {v8_mean:.4f}", flush=True)

        # Deltas vs refit baseline (apples-to-apples).
        deltas = [v - b for v, b in zip(v8_briers, base_briers)]
        mean_delta = float(np.mean(deltas)) if deltas else float("nan")
        improved = sum(1 for d in deltas if d < 0)
        print(f"    delta vs refit per-fold: {[f'{d:+.4f}' for d in deltas]}",
              flush=True)
        print(f"    delta mean: {mean_delta:+.4f}  "
              f"folds_improved={improved}/{len(deltas)}", flush=True)

        # Also report vs stored v6 baseline for transparency.
        stored_baseline = V6_BASELINE_BRIER[snapshot]
        mean_delta_vs_stored = v8_mean - stored_baseline
        print(f"    delta vs STORED v6 baseline: {mean_delta_vs_stored:+.4f}",
              flush=True)

        ship = (improved >= SHIP_MIN_FOLDS_IMPROVED
                and mean_delta <= SHIP_MEAN_DELTA_MAX)
        print(f"    SHIP per-snap: {ship}  "
              f"(>=3/4 improved AND mean_delta <= -0.002 vs refit)",
              flush=True)

        snap_results = {
            "n_rows": int(len(sub)),
            "feature_cols_v8": v8_features,
            "cat_cols": cat_cols,
            "hyperparams": hp,
            "v6_refit_briers": base_briers,
            "v6_refit_mean": base_mean,
            "v6_stored_baseline": stored_baseline,
            "v8_briers": v8_briers,
            "v8_mean": v8_mean,
            "deltas_per_fold_vs_refit": deltas,
            "mean_delta_vs_refit": mean_delta,
            "mean_delta_vs_stored_baseline": mean_delta_vs_stored,
            "folds_improved_vs_refit": improved,
            "n_folds": len(deltas),
            "ships": ship,
            "v8_fold_detail": v8_folds,
            "v6_refit_fold_detail": base_folds,
        }
        results["snapshots"][snapshot] = snap_results

        if ship:
            n_snaps_ship += 1
            print(f"    training v8_pbp_tight on FULL data + integrity check ...",
                  flush=True)
            wf_stats = {
                "fold_briers": v8_briers,
                "mean_brier": v8_mean,
                "v6_refit_baseline_briers": base_briers,
                "v6_refit_baseline_mean": base_mean,
                "v6_stored_baseline": stored_baseline,
                "deltas_per_fold_vs_refit": deltas,
                "mean_delta_vs_refit": mean_delta,
                "folds_improved_vs_refit": improved,
            }
            train_meta = train_full_and_save(
                sub, v8_features, cat_cols, hp, snapshot, wf_stats,
            )
            snap_results["saved_meta"] = {
                "lgb": train_meta.get("integrity", {}),
                "in_sample": train_meta.get("in_sample"),
            }

    overall_ship = n_snaps_ship >= 1
    results["snapshots_passed"] = n_snaps_ship
    results["verdict"] = "SHIP" if overall_ship else "REVERT"
    if overall_ship:
        results["reason"] = (
            f"{n_snaps_ship}/3 snapshots passed ship gate "
            f"(>=3/4 folds improved AND mean_delta <= -0.002 vs refit baseline)"
        )
    else:
        results["reason"] = (
            "no snapshot passed ship gate — Iter 64 saturation lesson "
            "confirmed: tight HPs do not unlock PBP signal"
        )

    elapsed = time.time() - t0
    results["elapsed_s"] = float(elapsed)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # ── summary ──
    print("\n" + "=" * 70, flush=True)
    print(f"ITER 72 VERDICT: {results['verdict']}", flush=True)
    print(f"Reason: {results['reason']}", flush=True)
    print("=" * 70, flush=True)
    print(f"  {'Snap':<7} {'v6_refit':<10} {'v8_pbp':<10} {'Delta':<10} "
          f"{'Folds':<7} {'Ship?':<6}", flush=True)
    for snap in SNAPSHOTS:
        r = results["snapshots"].get(snap)
        if not r:
            continue
        print(
            f"  {snap:<7} {r['v6_refit_mean']:<10.4f} {r['v8_mean']:<10.4f} "
            f"{r['mean_delta_vs_refit']:<+10.4f} "
            f"{r['folds_improved_vs_refit']}/{r['n_folds']:<5} "
            f"{'YES' if r['ships'] else 'no':<6}",
            flush=True,
        )
    print(f"  Elapsed: {elapsed:.1f}s", flush=True)
    print(f"  Results: {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
