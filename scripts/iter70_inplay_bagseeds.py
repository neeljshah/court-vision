"""
Iter 70: Bag-of-5-seeds ensemble for inplay winprob (endQ1/Q2/Q3).

Hypothesis: single-seed LGB trees at small leaf counts (nl=15, from Iter 68
v6_hp winners) are noisy. A 5-seed mean reduces variance with no overfit cost.
Cheap variance reduction.

Method:
  1) Mirror the data pipeline from iter68_inplay_hp_sweep.py exactly
     (linescores + season_games + quarter_features → snapshot rows).
  2) Use Iter 68's winning HPs per snapshot:
       endQ1: lr=0.03, nl=15, mcs=40
       endQ2: lr=0.03, nl=15, mcs=40
       endQ3: lr=0.03, nl=15, mcs=10
  3) Per snapshot per fold, train 5 LGB models at seeds {42, 7, 13, 23, 99}.
  4) Bag prediction = arithmetic mean of all 5 probability outputs.
  5) Compare bag-of-5 Brier vs single-seed v6_hp Brier (from Iter 68 results).
  6) Save 15 .lgb files + 15 _meta.json files (one per snapshot×seed) — only
     for the snapshots that pass the ship gate.
  7) pkl integrity check (booster.num_feature() == len(meta['feature_cols']))
     for each saved seed file.

Ship gate (per snapshot):
  bag-mean Brier <= single-seed v6_hp Brier on >=3/4 folds AND
  mean Brier delta <= -0.001.

DO NOT TOUCH (READ-ONLY):
  data/models/inplay_winprob_endq{1,2,3}.lgb / _meta.json
  data/models/inplay_winprob_endq{1,2,3}_v6_hp.lgb / _meta.json
  data/models/inplay_isotonic_endq{1,2,3}.joblib
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODEL_DIR = os.path.join(PROJECT, "data", "models")
OUT_JSON = os.path.join(DATA_CACHE, "iter70_inplay_bagseeds_results.json")
ITER68_JSON = os.path.join(DATA_CACHE, "iter68_inplay_hpsweep_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

MINUTES_PER_QUARTER = 12.0
SNAPSHOTS = ["endQ1", "endQ2", "endQ3"]
N_FOLDS = 4
BAG_SEEDS = [42, 7, 13, 23, 99]

# Iter 68 v6_hp winning HPs (per snapshot)
WINNING_HPS: Dict[str, Dict[str, Any]] = {
    "endQ1": {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 40},
    "endQ2": {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 40},
    "endQ3": {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 10},
}

# Ship gate
SHIP_MIN_FOLDS_IMPROVED = 3
SHIP_MEAN_DELTA_MAX = -0.001


# ── meta loading ──────────────────────────────────────────────────────────────

def load_meta(snapshot: str) -> Dict[str, Any]:
    """Load production .lgb meta (READ-ONLY) for feature list + cat cols."""
    path = os.path.join(MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_meta.json")
    with open(path) as f:
        return json.load(f)


def load_v6hp_meta(snapshot: str) -> Dict[str, Any]:
    """Load v6_hp meta (READ-ONLY) for the v6_hp feature list + cat cols."""
    path = os.path.join(MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_v6_hp_meta.json")
    with open(path) as f:
        return json.load(f)


def load_iter68_fold_briers() -> Dict[str, List[float]]:
    """Per-snapshot per-fold v6_hp single-seed Brier (the comparison baseline)."""
    with open(ITER68_JSON) as f:
        r = json.load(f)
    out: Dict[str, List[float]] = {}
    for snap in SNAPSHOTS:
        out[snap] = list(r["snapshots"][snap]["winner"]["fold_briers"])
    return out


# ── data loaders (mirror iter68_inplay_hp_sweep.py exactly) ──────────────────

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
    """Per (game_id, team_id) aggregates from quarter_features.parquet."""
    path = os.path.join(DATA_CACHE, "quarter_features.parquet")
    if not os.path.exists(path):
        print(f"  [WARN] {path} missing — endQ3 features will be NaN", flush=True)
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
                "q1_usg_avg": q1_usg_avg,
                "halftime_pace_shift": halftime_pace_shift,
                "trailing_team_q4_usg_hhi": trailing_team_q4_usg_hhi,
            })

    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    return df


# ── walk-forward bag-of-5 evaluation per snapshot ────────────────────────────

def evaluate_bag_snapshot(
    df: pd.DataFrame,
    snapshot: str,
    v6_meta: Dict[str, Any],
    v6_fold_briers: List[float],
) -> Dict[str, Any]:
    import lightgbm as lgb
    from sklearn.metrics import brier_score_loss

    feature_cols = list(v6_meta["feature_cols"])
    cat_cols = list(v6_meta.get("categorical_cols", []))
    base_hyperparams = dict(v6_meta.get("hyperparams", {}))
    win_hp = WINNING_HPS[snapshot]

    print(f"\n  [{snapshot}] features ({len(feature_cols)}): {feature_cols}",
          flush=True)
    print(f"    HPs: lr={win_hp['learning_rate']} nl={win_hp['num_leaves']} "
          f"mcs={win_hp['min_child_samples']}", flush=True)
    print(f"    v6_hp single-seed fold briers (baseline): "
          f"{[f'{b:.4f}' for b in v6_fold_briers]}", flush=True)

    sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
    n = len(sub)
    home_win_rate = float(sub["home_team_won"].mean()) if n > 0 else float("nan")
    print(f"    n_rows={n}, home_win_rate={home_win_rate:.3f}", flush=True)

    min_train = int(n * 0.60)
    test_size = (n - min_train) // N_FOLDS

    fold_records: List[Dict[str, Any]] = []

    for fold in range(N_FOLDS):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < N_FOLDS - 1 else n

        if train_end < 30 or test_start >= n:
            continue

        X_tr = sub[feature_cols].iloc[:train_end].copy()
        y_tr = sub["home_team_won"].iloc[:train_end]
        X_te = sub[feature_cols].iloc[test_start:test_end].copy()
        y_te = sub["home_team_won"].iloc[test_start:test_end].astype(int).values

        if len(X_te) < 10:
            continue

        active_cats = [c for c in cat_cols if c in X_tr.columns]
        for c in active_cats:
            X_tr[c] = X_tr[c].astype("category")
            X_te[c] = X_te[c].astype("category")

        # Train 5 seeded models and collect predictions
        per_seed_probs: List[np.ndarray] = []
        per_seed_briers: List[float] = []
        for seed in BAG_SEEDS:
            model = lgb.LGBMClassifier(
                n_estimators=int(base_hyperparams.get("n_estimators", 300)),
                learning_rate=float(win_hp["learning_rate"]),
                num_leaves=int(win_hp["num_leaves"]),
                min_child_samples=int(win_hp["min_child_samples"]),
                subsample=float(base_hyperparams.get("subsample", 0.8)),
                colsample_bytree=float(base_hyperparams.get("colsample_bytree", 0.8)),
                reg_alpha=float(base_hyperparams.get("reg_alpha", 0.1)),
                reg_lambda=float(base_hyperparams.get("reg_lambda", 1.0)),
                random_state=int(seed),
                n_jobs=4,
                verbose=-1,
            )
            model.fit(
                X_tr, y_tr,
                categorical_feature=active_cats if active_cats else "auto",
            )
            probs = model.predict_proba(X_te)[:, 1]
            per_seed_probs.append(probs)
            per_seed_briers.append(float(brier_score_loss(y_te, probs)))

        bag_probs = np.mean(np.stack(per_seed_probs, axis=0), axis=0)
        bag_brier = float(brier_score_loss(y_te, bag_probs))
        v6_brier = float(v6_fold_briers[fold]) if fold < len(v6_fold_briers) else None
        delta = (bag_brier - v6_brier) if v6_brier is not None else None
        improved = bool(delta is not None and delta < 0)

        fold_records.append({
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "per_seed_briers": per_seed_briers,
            "bag_brier": bag_brier,
            "v6_hp_single_seed_brier": v6_brier,
            "brier_delta_vs_v6hp": delta,
            "improved": improved,
        })
        ds = f"{delta:+.4f}" if delta is not None else "n/a"
        print(f"    fold {fold}: bag={bag_brier:.4f} v6_hp={v6_brier:.4f} "
              f"delta={ds}  improved={improved}  "
              f"per_seed=[{', '.join(f'{b:.4f}' for b in per_seed_briers)}]",
              flush=True)

    n_improved = sum(1 for r in fold_records if r["improved"])
    bag_briers = [r["bag_brier"] for r in fold_records]
    v6_briers = [r["v6_hp_single_seed_brier"] for r in fold_records
                 if r["v6_hp_single_seed_brier"] is not None]
    mean_bag = float(np.mean(bag_briers)) if bag_briers else None
    mean_v6 = float(np.mean(v6_briers)) if v6_briers else None
    mean_delta = (mean_bag - mean_v6) if (mean_bag is not None and mean_v6 is not None) else None

    folds_gate = n_improved >= SHIP_MIN_FOLDS_IMPROVED
    delta_gate = (mean_delta is not None and mean_delta <= SHIP_MEAN_DELTA_MAX)
    ship = folds_gate and delta_gate

    print(f"    SUMMARY [{snapshot}]: mean_bag={mean_bag:.4f} "
          f"mean_v6={mean_v6:.4f} mean_delta={mean_delta:+.4f} "
          f"improved={n_improved}/{len(fold_records)} ship={ship}",
          flush=True)

    return {
        "snapshot": snapshot,
        "n_rows": n,
        "home_win_rate": home_win_rate,
        "feature_cols": feature_cols,
        "categorical_cols": cat_cols,
        "winning_hps": win_hp,
        "fold_records": fold_records,
        "n_folds": len(fold_records),
        "n_folds_improved": n_improved,
        "mean_bag_brier": mean_bag,
        "mean_v6hp_brier": mean_v6,
        "mean_brier_delta_vs_v6hp": mean_delta,
        "folds_gate_passed": folds_gate,
        "delta_gate_passed": delta_gate,
        "ships": ship,
    }


# ── final retrain on full data + save 5 seeded models per shippable snapshot ─

def retrain_and_save_bag(
    df: pd.DataFrame,
    snapshot: str,
    v6_meta: Dict[str, Any],
    wf_eval: Dict[str, Any],
) -> Dict[str, Any]:
    import lightgbm as lgb
    from sklearn.metrics import (
        accuracy_score, brier_score_loss, log_loss, roc_auc_score,
    )

    feature_cols = list(v6_meta["feature_cols"])
    cat_cols = list(v6_meta.get("categorical_cols", []))
    base_hyperparams = dict(v6_meta.get("hyperparams", {}))
    win_hp = WINNING_HPS[snapshot]

    sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
    X = sub[feature_cols].copy()
    y = sub["home_team_won"].astype(int)
    active_cats = [c for c in cat_cols if c in X.columns]
    for c in active_cats:
        X[c] = X[c].astype("category")

    saved_files: List[Dict[str, Any]] = []
    per_seed_full_probs: List[np.ndarray] = []

    for seed_idx, seed in enumerate(BAG_SEEDS):
        model = lgb.LGBMClassifier(
            n_estimators=int(base_hyperparams.get("n_estimators", 300)),
            learning_rate=float(win_hp["learning_rate"]),
            num_leaves=int(win_hp["num_leaves"]),
            min_child_samples=int(win_hp["min_child_samples"]),
            subsample=float(base_hyperparams.get("subsample", 0.8)),
            colsample_bytree=float(base_hyperparams.get("colsample_bytree", 0.8)),
            reg_alpha=float(base_hyperparams.get("reg_alpha", 0.1)),
            reg_lambda=float(base_hyperparams.get("reg_lambda", 1.0)),
            random_state=int(seed),
            n_jobs=4,
            verbose=-1,
        )
        model.fit(X, y, categorical_feature=active_cats if active_cats else "auto")
        probs = model.predict_proba(X)[:, 1]
        per_seed_full_probs.append(probs)

        lgb_path = os.path.join(
            MODEL_DIR,
            f"inplay_winprob_{snapshot.lower()}_v7_bag5_seed{seed_idx}.lgb",
        )
        meta_path = os.path.join(
            MODEL_DIR,
            f"inplay_winprob_{snapshot.lower()}_v7_bag5_seed{seed_idx}_meta.json",
        )

        model.booster_.save_model(lgb_path)
        size_bytes = os.path.getsize(lgb_path)

        in_sample = {
            "auc": float(roc_auc_score(y, probs)),
            "brier": float(brier_score_loss(y, probs)),
            "log_loss": float(log_loss(y, np.clip(probs, 1e-6, 1 - 1e-6))),
            "accuracy": float(accuracy_score(y, (probs >= 0.5).astype(int))),
        }
        hp_used = dict(base_hyperparams)
        hp_used["learning_rate"] = float(win_hp["learning_rate"])
        hp_used["num_leaves"] = int(win_hp["num_leaves"])
        hp_used["min_child_samples"] = int(win_hp["min_child_samples"])
        hp_used["random_state"] = int(seed)

        meta_out = {
            "snapshot": snapshot,
            "variant": "v7_bag5",
            "iter": "iter70",
            "seed_idx": seed_idx,
            "seed": int(seed),
            "bag_seeds": BAG_SEEDS,
            "n_bag_members": len(BAG_SEEDS),
            "feature_cols": feature_cols,
            "categorical_cols": active_cats,
            "n_train_rows": int(len(X)),
            "n_features_in_": int(len(feature_cols)),
            "home_win_rate": float(y.mean()),
            "in_sample": in_sample,
            "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "probe": "iter70_inplay_bagseeds",
            "parent_meta": f"inplay_winprob_{snapshot.lower()}_v6_hp_meta.json",
            "hyperparams": hp_used,
            "winning_combo": win_hp,
        }
        with open(meta_path, "w") as f:
            json.dump(meta_out, f, indent=2)

        # ── pkl integrity check ───────────────────────────────────────────
        booster = lgb.Booster(model_file=lgb_path)
        booster_n_features = int(booster.num_feature())
        meta_n_features = int(meta_out["n_features_in_"])
        integrity_ok = booster_n_features == meta_n_features
        if not integrity_ok:
            raise RuntimeError(
                f"PKL integrity FAIL [{snapshot} seed{seed_idx}]: "
                f"booster has {booster_n_features} features, meta says "
                f"{meta_n_features}"
            )
        print(
            f"    [{snapshot} seed{seed_idx}={seed}] saved {os.path.basename(lgb_path)} "
            f"({size_bytes} bytes), booster_feats={booster_n_features} "
            f"meta_feats={meta_n_features} OK",
            flush=True,
        )

        saved_files.append({
            "seed_idx": seed_idx,
            "seed": int(seed),
            "lgb_path": lgb_path,
            "meta_path": meta_path,
            "in_sample": in_sample,
            "integrity_ok": integrity_ok,
            "booster_n_features": booster_n_features,
            "meta_n_features": meta_n_features,
            "size_bytes": int(size_bytes),
        })

    # Compute bag in-sample
    bag_probs = np.mean(np.stack(per_seed_full_probs, axis=0), axis=0)
    from sklearn.metrics import (
        accuracy_score, brier_score_loss, log_loss, roc_auc_score,
    )
    bag_in_sample = {
        "auc": float(roc_auc_score(y, bag_probs)),
        "brier": float(brier_score_loss(y, bag_probs)),
        "log_loss": float(log_loss(y, np.clip(bag_probs, 1e-6, 1 - 1e-6))),
        "accuracy": float(accuracy_score(y, (bag_probs >= 0.5).astype(int))),
    }

    return {
        "saved_files": saved_files,
        "bag_in_sample": bag_in_sample,
        "n_seeds_saved": len(saved_files),
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== Iter 70: Inplay Bag-of-5-Seeds Ensemble ===", flush=True)
    print(f"  bag seeds: {BAG_SEEDS}", flush=True)
    print(f"  winning HPs (per snap, from Iter 68):", flush=True)
    for snap, hp in WINNING_HPS.items():
        print(f"    {snap}: lr={hp['learning_rate']} nl={hp['num_leaves']} "
              f"mcs={hp['min_child_samples']}", flush=True)
    print(f"  ship gate: >=3/4 folds improved AND mean delta <= "
          f"{SHIP_MEAN_DELTA_MAX}", flush=True)

    print("\n[1] Loading metas (READ-ONLY) ...", flush=True)
    v6_metas = {snap: load_v6hp_meta(snap) for snap in SNAPSHOTS}
    for snap, m in v6_metas.items():
        print(f"    v6_hp {snap}: {len(m['feature_cols'])} features", flush=True)

    print("\n[2] Loading Iter 68 fold briers (single-seed baselines) ...",
          flush=True)
    v6_fold_briers = load_iter68_fold_briers()
    for snap, briers in v6_fold_briers.items():
        print(f"    {snap}: {[f'{b:.4f}' for b in briers]}", flush=True)

    print("\n[3] Loading data ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    qf_summaries = load_quarter_features_summaries()
    print(f"    linescores={len(linescores)}, season_games={len(season_games)}",
          flush=True)

    print("\n[4] Building rows ...", flush=True)
    df = build_rows(linescores, season_games, qf_summaries)
    valid_games = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid_games)].copy()
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    n_games = df["game_id"].nunique()
    print(f"    after endQ3 gate: {len(df)} rows, {n_games} games", flush=True)

    print("\n[5] Per-snapshot walk-forward bag-of-5 evaluation ...", flush=True)
    per_snap: Dict[str, Any] = {}
    for snap in SNAPSHOTS:
        per_snap[snap] = evaluate_bag_snapshot(
            df, snap, v6_metas[snap], v6_fold_briers[snap],
        )

    print("\n[6] Saving 5 seeded models for shippable snapshots ...", flush=True)
    saved: Dict[str, Any] = {}
    for snap in SNAPSHOTS:
        r = per_snap[snap]
        if r["ships"]:
            print(f"\n  {snap}: SHIPS — saving 5 seeded models", flush=True)
            saved[snap] = retrain_and_save_bag(df, snap, v6_metas[snap], r)
        else:
            print(f"\n  {snap}: no ship — skip save", flush=True)

    elapsed = time.time() - t0

    # ── summary table ────────────────────────────────────────────────────────
    print("\n" + "=" * 78, flush=True)
    print("ITER 70 — FINAL SUMMARY (bag-of-5-seeds vs v6_hp single-seed)",
          flush=True)
    print("=" * 78, flush=True)
    print(f"  {'Snap':<7} {'v6_hp':<10} {'Bag5':<10} {'Delta':<10} "
          f"{'Folds':<7} {'Ship':<5}", flush=True)
    for snap in SNAPSHOTS:
        r = per_snap[snap]
        v6 = r["mean_v6hp_brier"]
        bag = r["mean_bag_brier"]
        delta = r["mean_brier_delta_vs_v6hp"]
        nimp = r["n_folds_improved"]
        nf = r["n_folds"]
        ship_str = "YES" if r["ships"] else "no"
        print(
            f"  {snap:<7} {v6:<10.4f} {bag:<10.4f} {delta:<+10.4f} "
            f"{nimp}/{nf:<5} {ship_str:<5}",
            flush=True,
        )
    print(f"  Elapsed: {elapsed:.1f}s", flush=True)

    out = {
        "iter": "iter70",
        "validation": "inplay_winprob_bag_of_5_seeds",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bag_seeds": BAG_SEEDS,
        "winning_hps_per_snapshot": WINNING_HPS,
        "comparison_baseline": "iter68 v6_hp single-seed (fold briers from "
                               "iter68_inplay_hpsweep_results.json)",
        "n_folds": N_FOLDS,
        "ship_gate": {
            "min_folds_improved": SHIP_MIN_FOLDS_IMPROVED,
            "max_mean_delta": SHIP_MEAN_DELTA_MAX,
        },
        "snapshots": per_snap,
        "saved_artifacts": saved,
        "n_games_total": int(n_games),
        "elapsed_s": float(elapsed),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  Results saved to: {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
