"""
Iter 74: Polarity-corrected pregame retrain vs v6_hp internal-flip baseline.

The polarity bug audit (vault/Models/Polarity Bug Audit 2026-05-27.md) found
that `season_games.sim_win_prob` is INVERTED (corr with home_won = -0.194).
The v6_hp models (Iter 68, lr=0.03/nl=15) learn to flip the sign internally
during training.

Hypothesis: training on the corrected signal directly
(`pregame_win_prob = 1.0 - pregame_win_prob`) may produce SHARPER splits than
relying on the trees' internal compensation.

This is a SOURCE-FIX SIMULATION at the training-data level — we do NOT modify
`src/prediction/win_probability.py:178`; we just swap the feature value going
into the trainer (and the matching inference rows).

Method (per snapshot endQ1/Q2/Q3):
  1) Build training table identically to Iter 68 (linescores + season_games +
     quarter_features parquet).
  2) Apply `pregame_win_prob = 1.0 - pregame_win_prob` to ALL rows.
  3) Train with Iter 68 winning HPs (frozen from v6_hp _meta.json):
       endQ1: lr=0.03, num_leaves=15, min_child_samples=40
       endQ2: lr=0.03, num_leaves=15, min_child_samples=40
       endQ3: lr=0.03, num_leaves=15, min_child_samples=10
     All other HPs from v6_hp meta. seed=42.
  4) 4-fold expanding WF (same protocol as the OOS validator).
  5) Ship gate: >=3/4 folds improved AND mean delta <= -0.001 vs v6_hp.
  6) For shippers, retrain on FULL data and save as
     inplay_winprob_endq{N}_v9_polarity.lgb + _meta.json (with
     `polarity_corrected: true` flag).
  7) pkl integrity check on each saved model.

Baselines (v6_hp WF Brier, from prompt + meta files):
  endQ1: 0.2120
  endQ2: 0.1771
  endQ3: 0.1250

DO NOT TOUCH (READ-ONLY):
  data/models/inplay_winprob_endq{1,2,3}.lgb + _meta.json
  data/models/inplay_winprob_endq{1,2,3}_v6_hp.lgb + _meta.json
  data/models/inplay_winprob_endq3_v4_fouls.lgb
  data/models/inplay_winprob_endq2_v7_bag5_*.lgb
  data/models/inplay_isotonic_endq*.joblib
  data/models/inplay_meta_blend_endq*.json
  src/prediction/win_probability.py
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
OUT_JSON = os.path.join(DATA_CACHE, "iter74_inplay_polarity_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

MINUTES_PER_QUARTER = 12.0
SNAPSHOTS = ["endQ1", "endQ2", "endQ3"]
N_FOLDS = 4
SEED = 42

# v6_hp WF Brier baselines (from prompt + v6_hp _meta.json files).
# These are the numbers v9_polarity must beat.
V6HP_BRIER_BASELINE: Dict[str, float] = {
    "endQ1": 0.2120,
    "endQ2": 0.1771,
    "endQ3": 0.1250,
}

# Iter 68 winning HPs per snapshot (frozen).
ITER68_HPS: Dict[str, Dict[str, Any]] = {
    "endQ1": {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 40},
    "endQ2": {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 40},
    "endQ3": {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 10},
}

# Slightly relaxed ship gate (v6_hp internal flip may already be near-optimal).
SHIP_MIN_FOLDS_IMPROVED = 3
SHIP_MEAN_DELTA_MAX = -0.001


# ── meta loader (READ-ONLY) ──────────────────────────────────────────────────

def load_v6hp_meta(snapshot: str) -> Dict[str, Any]:
    path = os.path.join(
        MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_v6_hp_meta.json"
    )
    with open(path) as f:
        return json.load(f)


# ── data loaders (mirror Iter 68 exactly) ────────────────────────────────────

def load_linescores() -> Dict[str, Dict]:
    path = os.path.join(NBA_CACHE, "linescores_all.json")
    with open(path) as f:
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
        print(f"  [WARN] {path} missing", flush=True)
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
    print(f"  quarter_features summaries: {len(summaries)} entries", flush=True)
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


def build_rows(
    linescores: Dict,
    season_games: Dict,
    qf_summaries: Dict[str, Dict[str, float]],
) -> pd.DataFrame:
    records: List[Dict] = []
    required = ["home_q1", "home_q2", "home_q3", "home_q4",
                "away_q1", "away_q2", "away_q3", "away_q4"]

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
        pregame_wp_raw = _pregame_wp_from_sg(sg)

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
                "pregame_win_prob": pregame_wp_raw,
                "home_team_won": home_team_won,
                "q1_usg_avg": q1_usg_avg,
                "halftime_pace_shift": halftime_pace_shift,
                "trailing_team_q4_usg_hhi": trailing_team_q4_usg_hhi,
            })

    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    return df


# ── walk-forward CV ──────────────────────────────────────────────────────────

def walk_forward(
    df_snap: pd.DataFrame,
    feature_cols: List[str],
    cat_cols: List[str],
    hyperparams: Dict[str, Any],
    n_folds: int = N_FOLDS,
) -> List[float]:
    import lightgbm as lgb
    from sklearn.metrics import brier_score_loss

    n = len(df_snap)
    min_train = int(n * 0.60)
    test_size = (n - min_train) // n_folds

    fold_briers: List[float] = []

    for fold in range(n_folds):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < n_folds - 1 else n

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
            n_estimators=int(hyperparams.get("n_estimators", 300)),
            learning_rate=float(hyperparams["learning_rate"]),
            num_leaves=int(hyperparams["num_leaves"]),
            min_child_samples=int(hyperparams["min_child_samples"]),
            subsample=float(hyperparams.get("subsample", 0.8)),
            colsample_bytree=float(hyperparams.get("colsample_bytree", 0.8)),
            reg_alpha=float(hyperparams.get("reg_alpha", 0.1)),
            reg_lambda=float(hyperparams.get("reg_lambda", 1.0)),
            random_state=SEED,
            n_jobs=4,
            verbose=-1,
        )
        model.fit(
            X_tr, y_tr,
            categorical_feature=active_cats if active_cats else "auto",
        )
        probs = model.predict_proba(X_te)[:, 1]
        fold_briers.append(float(brier_score_loss(y_te.values, probs)))

    return fold_briers


# ── per-snapshot evaluation ──────────────────────────────────────────────────

def eval_snapshot(
    df: pd.DataFrame, snapshot: str, meta: Dict[str, Any],
) -> Dict[str, Any]:
    feature_cols = list(meta["feature_cols"])
    cat_cols = list(meta.get("categorical_cols", []))
    base_hyperparams = dict(meta.get("hyperparams", {}))

    # apply Iter 68 winning HPs (already the v6_hp HPs, but be explicit)
    hp = dict(base_hyperparams)
    iter68_hp = ITER68_HPS[snapshot]
    hp["learning_rate"] = iter68_hp["learning_rate"]
    hp["num_leaves"] = iter68_hp["num_leaves"]
    hp["min_child_samples"] = iter68_hp["min_child_samples"]

    sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
    n = len(sub)
    home_win_rate = float(sub["home_team_won"].mean()) if n > 0 else float("nan")

    print(f"\n  [{snapshot}] n_rows={n}, home_win_rate={home_win_rate:.3f}",
          flush=True)
    print(f"    features ({len(feature_cols)}): {feature_cols}", flush=True)
    print(f"    HPs (Iter68 frozen): lr={hp['learning_rate']} "
          f"nl={hp['num_leaves']} mcs={hp['min_child_samples']}", flush=True)

    # ── (A) baseline: v6_hp recipe — RAW pregame ──────────────────────────
    pregame_raw = sub["pregame_win_prob"].copy()
    sub["pregame_win_prob"] = pregame_raw  # ensure raw
    raw_corr = float(np.corrcoef(
        sub["pregame_win_prob"].fillna(0.5), sub["home_team_won"]
    )[0, 1])
    print(f"    RAW pregame corr w/ home_won: {raw_corr:+.4f} "
          f"(negative => polarity inverted as expected)", flush=True)
    print(f"    [A] training v6_hp-repro (RAW pregame) WF ...", flush=True)
    raw_fold_briers = walk_forward(sub, feature_cols, cat_cols, hp)
    raw_mean = float(np.mean(raw_fold_briers))
    raw_std = float(np.std(raw_fold_briers))

    # ── (B) candidate: polarity-corrected — FLIPPED pregame ────────────────
    sub["pregame_win_prob"] = 1.0 - pregame_raw
    flip_corr = float(np.corrcoef(
        sub["pregame_win_prob"].fillna(0.5), sub["home_team_won"]
    )[0, 1])
    print(f"    FLIPPED pregame corr w/ home_won: {flip_corr:+.4f} "
          f"(should be ~+|raw_corr|)", flush=True)
    print(f"    [B] training v9_polarity (FLIPPED pregame) WF ...", flush=True)
    flip_fold_briers = walk_forward(sub, feature_cols, cat_cols, hp)
    flip_mean = float(np.mean(flip_fold_briers))
    flip_std = float(np.std(flip_fold_briers))

    # restore (defensive — not strictly needed since we use the candidate flip
    # at full retrain too)
    sub["pregame_win_prob"] = pregame_raw

    # ── compare against the v6_hp BASELINE NUMBER (from prompt) ────────────
    baseline_num = V6HP_BRIER_BASELINE[snapshot]
    delta_vs_baseline = flip_mean - baseline_num
    # also delta vs (A) — the head-to-head re-run comparison
    delta_vs_repro = flip_mean - raw_mean

    # per-fold improved counts (vs reproduced baseline; honest head-to-head)
    n_folds_improved_vs_repro = sum(
        1 for (a, b) in zip(raw_fold_briers, flip_fold_briers) if b < a
    )

    ships = (
        n_folds_improved_vs_repro >= SHIP_MIN_FOLDS_IMPROVED
        and delta_vs_baseline <= SHIP_MEAN_DELTA_MAX
    )

    print(f"\n    [{snapshot}] v6_hp-repro mean Brier: {raw_mean:.4f} "
          f"(folds={[round(x, 4) for x in raw_fold_briers]})",
          flush=True)
    print(f"    [{snapshot}] v9_polarity   mean Brier: {flip_mean:.4f} "
          f"(folds={[round(x, 4) for x in flip_fold_briers]})",
          flush=True)
    print(f"    [{snapshot}] delta v9 vs v6_hp baseline (0.{int(baseline_num * 10000)}): "
          f"{delta_vs_baseline:+.4f}", flush=True)
    print(f"    [{snapshot}] delta v9 vs head-to-head repro: {delta_vs_repro:+.4f}; "
          f"folds improved {n_folds_improved_vs_repro}/{len(flip_fold_briers)}; "
          f"ship={'YES' if ships else 'no'}", flush=True)

    return {
        "snapshot": snapshot,
        "n_rows": n,
        "home_win_rate": home_win_rate,
        "feature_cols": feature_cols,
        "categorical_cols": cat_cols,
        "hyperparams": hp,
        "raw_pregame_corr": raw_corr,
        "flipped_pregame_corr": flip_corr,
        "v6hp_baseline_published": baseline_num,
        "v6hp_repro_fold_briers": raw_fold_briers,
        "v6hp_repro_mean_brier": raw_mean,
        "v6hp_repro_std_brier": raw_std,
        "v9_polarity_fold_briers": flip_fold_briers,
        "v9_polarity_mean_brier": flip_mean,
        "v9_polarity_std_brier": flip_std,
        "delta_vs_v6hp_baseline": delta_vs_baseline,
        "delta_vs_v6hp_repro": delta_vs_repro,
        "n_folds_improved_vs_repro": n_folds_improved_vs_repro,
        "n_folds": len(flip_fold_briers),
        "ship_min_folds_improved": SHIP_MIN_FOLDS_IMPROVED,
        "ship_mean_delta_max": SHIP_MEAN_DELTA_MAX,
        "ships": ships,
    }


# ── full retrain + save for shippable snapshots ──────────────────────────────

def retrain_and_save(
    df: pd.DataFrame, snapshot: str, meta: Dict[str, Any],
    eval_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Retrain on ALL data with FLIPPED pregame. Save as v9_polarity."""
    import lightgbm as lgb
    from sklearn.metrics import (
        accuracy_score, brier_score_loss, log_loss, roc_auc_score,
    )

    feature_cols = list(meta["feature_cols"])
    cat_cols = list(meta.get("categorical_cols", []))
    hp = dict(eval_result["hyperparams"])

    sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
    # apply the polarity correction to training rows
    sub["pregame_win_prob"] = 1.0 - sub["pregame_win_prob"]

    X = sub[feature_cols].copy()
    y = sub["home_team_won"].astype(int)
    active_cats = [c for c in cat_cols if c in X.columns]
    for c in active_cats:
        X[c] = X[c].astype("category")

    model = lgb.LGBMClassifier(
        n_estimators=int(hp.get("n_estimators", 300)),
        learning_rate=float(hp["learning_rate"]),
        num_leaves=int(hp["num_leaves"]),
        min_child_samples=int(hp["min_child_samples"]),
        subsample=float(hp.get("subsample", 0.8)),
        colsample_bytree=float(hp.get("colsample_bytree", 0.8)),
        reg_alpha=float(hp.get("reg_alpha", 0.1)),
        reg_lambda=float(hp.get("reg_lambda", 1.0)),
        random_state=SEED,
        n_jobs=4,
        verbose=-1,
    )
    model.fit(X, y, categorical_feature=active_cats if active_cats else "auto")

    probs = model.predict_proba(X)[:, 1]
    preds = (probs >= 0.5).astype(int)
    in_sample = {
        "auc": float(roc_auc_score(y, probs)),
        "brier": float(brier_score_loss(y, probs)),
        "log_loss": float(log_loss(y, np.clip(probs, 1e-6, 1 - 1e-6))),
        "accuracy": float(accuracy_score(y, preds)),
    }

    out_path = os.path.join(
        MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_v9_polarity.lgb"
    )
    model.booster_.save_model(out_path)
    size_bytes = os.path.getsize(out_path)

    meta_out = {
        "snapshot": snapshot,
        "variant": "v9_polarity",
        "iter": "iter74",
        "polarity_corrected": True,
        "polarity_correction_recipe":
            "At BOTH training AND inference, apply "
            "`pregame_win_prob = 1.0 - pregame_win_prob` before passing the "
            "row to the model. season_games.sim_win_prob is inverted; this "
            "transform converts it to the natural orientation.",
        "feature_cols": feature_cols,
        "categorical_cols": active_cats,
        "n_train_rows": int(len(X)),
        "n_features_in_": int(len(feature_cols)),
        "home_win_rate": float(y.mean()),
        "in_sample": in_sample,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe": "iter74_inplay_polarity_corrected_retrain",
        "parent_meta": f"inplay_winprob_{snapshot.lower()}_v6_hp_meta.json",
        "hyperparams": hp,
        "winning_combo": {
            "learning_rate": hp["learning_rate"],
            "num_leaves": hp["num_leaves"],
            "min_child_samples": hp["min_child_samples"],
        },
        "wf_eval": {
            "v6hp_repro_fold_briers": eval_result["v6hp_repro_fold_briers"],
            "v6hp_repro_mean_brier": eval_result["v6hp_repro_mean_brier"],
            "v9_polarity_fold_briers": eval_result["v9_polarity_fold_briers"],
            "v9_polarity_mean_brier": eval_result["v9_polarity_mean_brier"],
            "delta_vs_v6hp_baseline": eval_result["delta_vs_v6hp_baseline"],
            "delta_vs_v6hp_repro": eval_result["delta_vs_v6hp_repro"],
            "n_folds_improved_vs_repro":
                eval_result["n_folds_improved_vs_repro"],
            "v6hp_baseline_published":
                eval_result["v6hp_baseline_published"],
        },
    }
    meta_out_path = os.path.join(
        MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_v9_polarity_meta.json"
    )
    with open(meta_out_path, "w") as f:
        json.dump(meta_out, f, indent=2)

    # ── pkl integrity check ───────────────────────────────────────────────
    booster = lgb.Booster(model_file=out_path)
    booster_n_features = int(booster.num_feature())
    meta_n_features = int(meta_out["n_features_in_"])
    integrity_ok = booster_n_features == meta_n_features

    print(
        f"    saved {out_path} ({size_bytes} bytes)\n"
        f"    saved {meta_out_path}\n"
        f"    PKL INTEGRITY: booster.num_feature()={booster_n_features} "
        f"vs meta.n_features_in_={meta_n_features} -> "
        f"{'OK' if integrity_ok else 'FAIL'}",
        flush=True,
    )
    if not integrity_ok:
        raise RuntimeError(
            f"PKL integrity check FAILED for {snapshot}: "
            f"booster has {booster_n_features} features, meta says "
            f"{meta_n_features}"
        )

    return {
        "saved_lgb": out_path,
        "saved_meta": meta_out_path,
        "in_sample": in_sample,
        "integrity_ok": integrity_ok,
        "booster_n_features": booster_n_features,
        "meta_n_features": meta_n_features,
        "size_bytes": size_bytes,
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== Iter 74: Inplay polarity-corrected retrain ===", flush=True)
    print(f"  random_state={SEED}, n_folds={N_FOLDS}", flush=True)
    print(f"  ship gate: >=3/4 folds improved AND mean delta <= -0.001 "
          f"vs v6_hp", flush=True)
    print(f"  v6_hp baselines: {V6HP_BRIER_BASELINE}", flush=True)

    print("\n[1] Loading v6_hp metas (READ-ONLY) ...", flush=True)
    metas = {snap: load_v6hp_meta(snap) for snap in SNAPSHOTS}
    for snap, m in metas.items():
        print(f"    {snap}: {len(m['feature_cols'])} features", flush=True)

    print("\n[2] Loading data ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    qf_summaries = load_quarter_features_summaries()
    print(f"    linescores={len(linescores)}, season_games={len(season_games)}",
          flush=True)

    print("\n[3] Building rows ...", flush=True)
    df = build_rows(linescores, season_games, qf_summaries)
    valid_games = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid_games)].copy()
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    print(f"    after endQ3 gate: {len(df)} rows, "
          f"{df['game_id'].nunique()} games", flush=True)

    print("\n[4] Per-snapshot polarity comparison ...", flush=True)
    per_snap: Dict[str, Any] = {}
    for snap in SNAPSHOTS:
        per_snap[snap] = eval_snapshot(df, snap, metas[snap])

    print("\n[5] Retraining shippable snapshots on FULL data ...", flush=True)
    saved: Dict[str, Any] = {}
    for snap in SNAPSHOTS:
        r = per_snap[snap]
        if r["ships"]:
            print(f"\n  Retraining {snap} v9_polarity ...", flush=True)
            saved[snap] = retrain_and_save(df, snap, metas[snap], r)
        else:
            print(f"\n  {snap}: no ship — skip retrain", flush=True)

    elapsed = time.time() - t0

    print("\n" + "=" * 78, flush=True)
    print("ITER 74 — FINAL SUMMARY (polarity-corrected retrain)", flush=True)
    print("=" * 78, flush=True)
    print(f"  {'Snap':<6} {'v6_hp pub':<10} {'v6_hp_repro':<12} "
          f"{'v9_polarity':<12} {'Delta_pub':<10} {'Delta_h2h':<10} "
          f"{'Folds':<7} {'Ship':<5}", flush=True)
    for snap in SNAPSHOTS:
        r = per_snap[snap]
        print(
            f"  {snap:<6} "
            f"{r['v6hp_baseline_published']:<10.4f} "
            f"{r['v6hp_repro_mean_brier']:<12.4f} "
            f"{r['v9_polarity_mean_brier']:<12.4f} "
            f"{r['delta_vs_v6hp_baseline']:<+10.4f} "
            f"{r['delta_vs_v6hp_repro']:<+10.4f} "
            f"{r['n_folds_improved_vs_repro']}/{r['n_folds']:<5} "
            f"{'YES' if r['ships'] else 'no':<5}",
            flush=True,
        )
    print(f"  Elapsed: {elapsed:.1f}s", flush=True)

    out = {
        "iter": "iter74",
        "validation": "inplay_winprob_polarity_corrected_retrain",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "random_seed": SEED,
        "n_folds": N_FOLDS,
        "v6hp_baselines_published": V6HP_BRIER_BASELINE,
        "iter68_hps": ITER68_HPS,
        "ship_gate": {
            "min_folds_improved": SHIP_MIN_FOLDS_IMPROVED,
            "max_mean_delta": SHIP_MEAN_DELTA_MAX,
        },
        "snapshots": per_snap,
        "saved_artifacts": saved,
        "n_games_total": int(df["game_id"].nunique()),
        "elapsed_s": float(elapsed),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  Results saved to: {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
