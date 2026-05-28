"""
Iter 68: Per-snapshot HP sweep for inplay winprob (endQ1/Q2/Q3).

Existing global HPs (lr=0.05, num_leaves=31, min_child_samples=20) per the
production _meta.json files are not snapshot-tuned. endQ1 has the noisiest
signal — tighter regularization may help endQ1 specifically.

Grid (27 combos per snapshot):
  learning_rate    ∈ {0.03, 0.05, 0.08}
  num_leaves       ∈ {15, 31, 63}
  min_child_samples∈ {10, 20, 40}
All other HPs frozen at existing meta values. random_state=42.

Method:
  1) Build the same feature matrix as oos_validate_inplay_2026_05_27.py
     (and train_inplay_winprob_endq3.py) — linescores + season_games +
     quarter_features parquet.
  2) For each snapshot, for each of 27 HP combos, run the same 4-fold
     expanding-window WF as the OOS validator (random_state=42).
  3) Pick the combo with lowest mean WF Brier AND >=3/4 folds improved vs
     production baseline (endQ1 0.2221, endQ2 0.1860, endQ3 0.1354).
  4) Ship gate per snapshot:
       >=3/4 folds improved AND mean Brier delta <= -0.002 vs prod baseline.
  5) If a snapshot passes the ship gate, retrain on ALL data with winning HPs
     and save as inplay_winprob_endq{N}_v6_hp.lgb + _meta.json. The existing
     .lgb STAYS UNTOUCHED.
  6) pkl integrity check (booster n_features matches _meta.json) for every
     saved model.

DO NOT TOUCH:
  data/models/inplay_winprob_endq{1,2,3}.lgb and _meta.json (READ ONLY)
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
OUT_JSON = os.path.join(DATA_CACHE, "iter68_inplay_hpsweep_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

MINUTES_PER_QUARTER = 12.0
SNAPSHOTS = ["endQ1", "endQ2", "endQ3"]
N_FOLDS = 4
SEED = 42

# Production baseline Brier (from data/cache/inplay_oos_validation_2026_05_27.json)
PROD_BRIER_BASELINE: Dict[str, float] = {
    "endQ1": 0.2221,
    "endQ2": 0.1860,
    "endQ3": 0.1354,
}

# Ship gate
SHIP_MIN_FOLDS_IMPROVED = 3
SHIP_MEAN_DELTA_MAX = -0.002  # mean Brier delta must be <= -0.002

# HP grid
HP_GRID = {
    "learning_rate": [0.03, 0.05, 0.08],
    "num_leaves": [15, 31, 63],
    "min_child_samples": [10, 20, 40],
}


# ── meta loading ─────────────────────────────────────────────────────────────

def load_meta(snapshot: str) -> Dict[str, Any]:
    path = os.path.join(MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_meta.json")
    with open(path) as f:
        return json.load(f)


# ── data loaders (mirror oos validator + trainer exactly) ────────────────────

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
    """Per (game_id, team_id) team-level aggregates from quarter_features.parquet."""
    path = os.path.join(DATA_CACHE, "quarter_features.parquet")
    if not os.path.exists(path):
        print(f"  [WARN] {path} missing — endQ3 quarter features will be NaN",
              flush=True)
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


# ── pregame WP fallback ───────────────────────────────────────────────────────

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


# ── row construction (matches OOS validator exactly) ─────────────────────────

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


# ── walk-forward CV for a single HP combo ────────────────────────────────────

_GLOBAL_TRAIN_COUNTER = [0]


def walk_forward_for_hp(
    df_snap: pd.DataFrame,
    feature_cols: List[str],
    cat_cols: List[str],
    hyperparams: Dict[str, Any],
    n_folds: int = N_FOLDS,
) -> List[float]:
    """Returns list of per-fold Brier scores."""
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

        _GLOBAL_TRAIN_COUNTER[0] += 1
        if _GLOBAL_TRAIN_COUNTER[0] % 30 == 0:
            print(f"    ... trained {_GLOBAL_TRAIN_COUNTER[0]} fold-models",
                  flush=True)

    return fold_briers


# ── HP sweep driver per snapshot ─────────────────────────────────────────────

def sweep_snapshot(
    df: pd.DataFrame, snapshot: str, meta: Dict[str, Any],
) -> Dict[str, Any]:
    feature_cols = list(meta["feature_cols"])
    cat_cols = list(meta.get("categorical_cols", []))
    base_hyperparams = dict(meta.get("hyperparams", {}))

    sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
    n = len(sub)
    home_win_rate = float(sub["home_team_won"].mean()) if n > 0 else float("nan")
    print(f"\n  [{snapshot}] n_rows={n}, home_win_rate={home_win_rate:.3f}",
          flush=True)
    print(f"    features ({len(feature_cols)}): {feature_cols}", flush=True)
    print(f"    base hyperparams: {base_hyperparams}", flush=True)
    print(f"    prod WF Brier baseline: {PROD_BRIER_BASELINE[snapshot]}",
          flush=True)

    baseline = PROD_BRIER_BASELINE[snapshot]
    combo_results: List[Dict[str, Any]] = []

    combo_idx = 0
    n_combos = (len(HP_GRID["learning_rate"])
                * len(HP_GRID["num_leaves"])
                * len(HP_GRID["min_child_samples"]))
    for lr in HP_GRID["learning_rate"]:
        for nl in HP_GRID["num_leaves"]:
            for mcs in HP_GRID["min_child_samples"]:
                combo_idx += 1
                hp = dict(base_hyperparams)
                hp["learning_rate"] = lr
                hp["num_leaves"] = nl
                hp["min_child_samples"] = mcs

                fold_briers = walk_forward_for_hp(
                    sub, feature_cols, cat_cols, hp,
                )
                if not fold_briers:
                    continue
                mean_b = float(np.mean(fold_briers))
                std_b = float(np.std(fold_briers))
                n_improved = sum(1 for b in fold_briers if b < baseline)
                delta = mean_b - baseline

                combo_results.append({
                    "combo_idx": combo_idx,
                    "learning_rate": lr,
                    "num_leaves": nl,
                    "min_child_samples": mcs,
                    "fold_briers": fold_briers,
                    "mean_brier": mean_b,
                    "std_brier": std_b,
                    "mean_brier_delta_vs_prod": delta,
                    "n_folds_improved_vs_baseline": n_improved,
                    "n_folds": len(fold_briers),
                })
                print(
                    f"    [{combo_idx}/{n_combos}] lr={lr} nl={nl} mcs={mcs}: "
                    f"mean Brier={mean_b:.4f} ({std_b:.4f}) "
                    f"delta={delta:+.4f} improved={n_improved}/{len(fold_briers)}",
                    flush=True,
                )

    # Pick winner: lowest mean Brier among combos that pass ship gate
    eligible = [
        c for c in combo_results
        if c["n_folds_improved_vs_baseline"] >= SHIP_MIN_FOLDS_IMPROVED
        and c["mean_brier_delta_vs_prod"] <= SHIP_MEAN_DELTA_MAX
    ]
    if eligible:
        winner = min(eligible, key=lambda c: c["mean_brier"])
        ship = True
        print(f"\n    WINNER (passes ship gate): lr={winner['learning_rate']} "
              f"nl={winner['num_leaves']} mcs={winner['min_child_samples']} "
              f"mean Brier={winner['mean_brier']:.4f} "
              f"delta={winner['mean_brier_delta_vs_prod']:+.4f} "
              f"improved={winner['n_folds_improved_vs_baseline']}/4", flush=True)
    else:
        # Report best-by-Brier even if it doesn't pass gate
        winner = min(combo_results, key=lambda c: c["mean_brier"]) if combo_results else None
        ship = False
        if winner:
            print(f"\n    NO COMBO PASSED SHIP GATE. Best mean Brier: "
                  f"lr={winner['learning_rate']} nl={winner['num_leaves']} "
                  f"mcs={winner['min_child_samples']} "
                  f"mean Brier={winner['mean_brier']:.4f} "
                  f"delta={winner['mean_brier_delta_vs_prod']:+.4f} "
                  f"improved={winner['n_folds_improved_vs_baseline']}/4",
                  flush=True)

    return {
        "snapshot": snapshot,
        "n_rows": n,
        "home_win_rate": home_win_rate,
        "feature_cols": feature_cols,
        "categorical_cols": cat_cols,
        "base_hyperparams": base_hyperparams,
        "prod_brier_baseline": baseline,
        "ship_min_folds_improved": SHIP_MIN_FOLDS_IMPROVED,
        "ship_mean_delta_max": SHIP_MEAN_DELTA_MAX,
        "combo_results": combo_results,
        "winner": winner,
        "ships": ship,
    }


# ── final retrain + save for shippable snapshots ─────────────────────────────

def retrain_and_save(
    df: pd.DataFrame, snapshot: str, meta: Dict[str, Any],
    winning_hp: Dict[str, Any], in_sample_brier_baseline: float,
) -> Dict[str, Any]:
    """Retrain on ALL data with winning HPs, save as _v6_hp.lgb + _meta.json.

    Includes pkl integrity check: booster.num_feature() must match
    len(feature_cols) in the saved meta.
    """
    import lightgbm as lgb
    from sklearn.metrics import (
        accuracy_score, brier_score_loss, log_loss, roc_auc_score,
    )

    feature_cols = list(meta["feature_cols"])
    cat_cols = list(meta.get("categorical_cols", []))
    base_hyperparams = dict(meta.get("hyperparams", {}))
    hp = dict(base_hyperparams)
    hp["learning_rate"] = float(winning_hp["learning_rate"])
    hp["num_leaves"] = int(winning_hp["num_leaves"])
    hp["min_child_samples"] = int(winning_hp["min_child_samples"])

    sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
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
        MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_v6_hp.lgb"
    )
    model.booster_.save_model(out_path)
    size_bytes = os.path.getsize(out_path)

    meta_out = {
        "snapshot": snapshot,
        "variant": "v6_hp",
        "iter": "iter68",
        "feature_cols": feature_cols,
        "categorical_cols": active_cats,
        "n_train_rows": int(len(X)),
        "n_features_in_": int(len(feature_cols)),
        "home_win_rate": float(y.mean()),
        "in_sample": in_sample,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe": "iter68_inplay_hp_sweep",
        "parent_meta": f"inplay_winprob_{snapshot.lower()}_meta.json",
        "hyperparams": hp,
        "winning_combo": {
            "learning_rate": winning_hp["learning_rate"],
            "num_leaves": winning_hp["num_leaves"],
            "min_child_samples": winning_hp["min_child_samples"],
        },
        "wf_eval": {
            "fold_briers": winning_hp["fold_briers"],
            "mean_brier": winning_hp["mean_brier"],
            "std_brier": winning_hp["std_brier"],
            "mean_brier_delta_vs_prod_baseline":
                winning_hp["mean_brier_delta_vs_prod"],
            "n_folds_improved": winning_hp["n_folds_improved_vs_baseline"],
            "prod_baseline_brier": in_sample_brier_baseline,
        },
    }
    meta_out_path = os.path.join(
        MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_v6_hp_meta.json"
    )
    with open(meta_out_path, "w") as f:
        json.dump(meta_out, f, indent=2)

    # ── pkl integrity check ───────────────────────────────────────────────
    # Reload the saved booster and verify feature count matches meta.
    booster = lgb.Booster(model_file=out_path)
    booster_n_features = int(booster.num_feature())
    meta_n_features = int(meta_out["n_features_in_"])
    integrity_ok = booster_n_features == meta_n_features

    print(
        f"    saved {out_path} ({size_bytes} bytes)\n"
        f"    saved {meta_out_path}\n"
        f"    PKL INTEGRITY CHECK: booster.num_feature()={booster_n_features} "
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
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== Iter 68: Inplay HP Sweep (per-snapshot) ===", flush=True)
    print(f"  random_state={SEED}", flush=True)
    print(f"  grid: lr={HP_GRID['learning_rate']} "
          f"nl={HP_GRID['num_leaves']} mcs={HP_GRID['min_child_samples']}",
          flush=True)
    print(f"  ship gate: >=3/4 folds improved AND mean delta <= -0.002",
          flush=True)

    print("\n[1] Loading metas (READ-ONLY) ...", flush=True)
    metas = {snap: load_meta(snap) for snap in SNAPSHOTS}
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

    print("\n[4] Running HP sweep per snapshot ...", flush=True)
    per_snap: Dict[str, Any] = {}
    for snap in SNAPSHOTS:
        per_snap[snap] = sweep_snapshot(df, snap, metas[snap])
    print(f"\n  Total fold-trainings: {_GLOBAL_TRAIN_COUNTER[0]}", flush=True)

    print("\n[5] Retraining shippable snapshots on FULL data ...", flush=True)
    saved: Dict[str, Any] = {}
    for snap in SNAPSHOTS:
        r = per_snap[snap]
        if r["ships"] and r["winner"]:
            print(f"\n  Retraining {snap} with winning HPs ...", flush=True)
            saved[snap] = retrain_and_save(
                df, snap, metas[snap], r["winner"],
                in_sample_brier_baseline=PROD_BRIER_BASELINE[snap],
            )
        else:
            print(f"\n  {snap}: no ship — skip retrain", flush=True)

    elapsed = time.time() - t0

    # ── summary table ────────────────────────────────────────────────────────
    print("\n" + "=" * 70, flush=True)
    print("ITER 68 — FINAL SUMMARY (per-snapshot HP sweep)", flush=True)
    print("=" * 70, flush=True)
    print(f"  {'Snap':<7} {'Baseline':<10} {'Winner Brier':<14} "
          f"{'Delta':<10} {'Folds':<7} {'HP':<28} {'Ship':<5}",
          flush=True)
    for snap in SNAPSHOTS:
        r = per_snap[snap]
        w = r["winner"]
        if w:
            hp_str = (f"lr={w['learning_rate']} nl={w['num_leaves']} "
                      f"mcs={w['min_child_samples']}")
            print(
                f"  {snap:<7} {r['prod_brier_baseline']:<10.4f} "
                f"{w['mean_brier']:<14.4f} "
                f"{w['mean_brier_delta_vs_prod']:<+10.4f} "
                f"{w['n_folds_improved_vs_baseline']}/{w['n_folds']:<5} "
                f"{hp_str:<28} {'YES' if r['ships'] else 'no':<5}",
                flush=True,
            )
        else:
            print(f"  {snap:<7} {r['prod_brier_baseline']:<10.4f}  no combo",
                  flush=True)
    print(f"  Elapsed: {elapsed:.1f}s", flush=True)

    out = {
        "iter": "iter68",
        "validation": "inplay_winprob_hp_sweep_per_snapshot",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "random_seed": SEED,
        "n_folds": N_FOLDS,
        "hp_grid": HP_GRID,
        "prod_brier_baselines": PROD_BRIER_BASELINE,
        "ship_gate": {
            "min_folds_improved": SHIP_MIN_FOLDS_IMPROVED,
            "max_mean_delta": SHIP_MEAN_DELTA_MAX,
        },
        "snapshots": per_snap,
        "saved_artifacts": saved,
        "n_games_total": int(df["game_id"].nunique()),
        "n_fold_trainings": int(_GLOBAL_TRAIN_COUNTER[0]),
        "elapsed_s": float(elapsed),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  Results saved to: {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
