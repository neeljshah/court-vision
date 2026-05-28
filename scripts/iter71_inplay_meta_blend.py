"""
Iter 71: Inplay Meta-Blend (NNLS over surviving Wave 1-3 components).

Capstone iteration — does a non-negative least-squares blend over per-snapshot
components beat the best single component?

Per snapshot, components are:
  endQ1:
    1. v6_hp raw (Iter 68 winning HPs: lr=0.03, nl=15, mcs=40)
    2. v6_hp + isotonic-transformed (Iter 62 cross-fold isotonic)
    3. sigmoid(score_margin / 6.0)
    4. polarity-corrected pregame = (1 - sim_win_prob)
  endQ2:
    1. v6_hp raw (mcs=40)
    2. v6_hp + isotonic
    3. v7_bag5 mean (bag of 5 seeds over v6_hp HPs)
    4. sigmoid(score_margin / 6.0)
    5. polarity-corrected pregame
  endQ3:
    1. v6_hp raw (mcs=10)
    2. v6_hp + isotonic
    3. v4_fouls raw (adds 7 foul features; subset of games — restrict eval here too)
    4. sigmoid(score_margin / 6.0)
    5. polarity-corrected pregame

Walk-forward (4 folds, same expanding split as Iter 62/65/68/70):
  fold k: train on rows [0, train_end_k), test on [test_start_k, test_end_k)
  For each fold k:
    - Train every component on the train slice (fresh per fold).
    - Compute OOS predictions on the test slice.
    - For k=0, no prior OOS history → blend = best single (no NNLS yet).
    - For k>=1, fit NNLS on accumulated prior-fold OOS predictions → labels,
      apply weights to current fold OOS, report blend Brier.
  Final saved NNLS weights = NNLS fit on folds 0-2 OOS pooled (3-fold stack train),
  evaluated as a separate single-pass on fold 3.

Ship gate per snapshot:
  Meta-blend Brier ≤ best single component Brier on ≥3/4 folds AND
  mean Brier delta ≤ -0.001 vs best single.

DO NOT TOUCH (READ-ONLY):
  data/models/inplay_winprob_endq{1,2,3}.lgb / _meta.json
  data/models/inplay_winprob_endq{1,2,3}_v6_hp.lgb / _meta.json
  data/models/inplay_winprob_endq3_v4_fouls.lgb / _meta.json
  data/models/inplay_winprob_endq2_v7_bag5_*.lgb / _meta.json
  data/models/inplay_isotonic_endq{1,2,3}.joblib
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODEL_DIR = os.path.join(PROJECT, "data", "models")
FOUL_PARQUET = os.path.join(DATA_CACHE, "inplay_foul_state.parquet")
OUT_JSON = os.path.join(DATA_CACHE, "iter71_inplay_meta_blend_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

MINUTES_PER_QUARTER = 12.0
SNAPSHOTS = ["endQ1", "endQ2", "endQ3"]
N_FOLDS = 4
SEED = 42
BAG_SEEDS = [42, 7, 13, 23, 99]

# Iter 68 winning HPs per snapshot
WINNING_HPS: Dict[str, Dict[str, Any]] = {
    "endQ1": {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 40},
    "endQ2": {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 40},
    "endQ3": {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 10},
}

BASE_HP_DEFAULTS = {
    "n_estimators": 300,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": SEED,
}

# Best single per snapshot (from prior iters — used for the ship comparison)
BEST_SINGLE = {
    "endQ1": "v6_hp",       # Iter 68 — 0.2120
    "endQ2": "v7_bag5",     # Iter 70 — 0.1760
    "endQ3": "v4_fouls",    # Iter 65 — 0.1193 (on 2505-game subset)
}

# Snap → list of component keys (order = NNLS weight order)
SNAP_COMPONENTS: Dict[str, List[str]] = {
    "endQ1": ["v6_hp", "iso", "sigmoid_margin", "polarity_pregame"],
    "endQ2": ["v6_hp", "iso", "v7_bag5", "sigmoid_margin", "polarity_pregame"],
    "endQ3": ["v6_hp", "iso", "v4_fouls", "sigmoid_margin", "polarity_pregame"],
}

# Snap → feature list for v6_hp (matches Iter 68 winner meta exactly)
V6_HP_FEATURES: Dict[str, List[str]] = {
    "endQ1": ["score_margin", "total_pts", "pace_so_far", "q1_delta",
              "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
    "endQ2": ["score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
              "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
    "endQ3": ["score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
              "q3_delta", "last_q_margin", "pregame_win_prob", "home_team_id",
              "season", "q1_usg_avg", "halftime_pace_shift",
              "trailing_team_q4_usg_hhi"],
}

V4_FOULS_EXTRA = [
    "home_team_pfs_cum", "away_team_pfs_cum",
    "home_max_player_pfs", "away_max_player_pfs",
    "home_starter_fouled_out_indicator",
    "away_starter_fouled_out_indicator", "pf_imbalance",
]

CAT_COLS = ["home_team_id", "season"]


# ── data loaders (mirror iter62/iter65/iter70) ─────────────────────────────────

def load_linescores() -> Dict[str, Dict]:
    with open(os.path.join(NBA_CACHE, "linescores_all.json")) as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    seasons = ["2022-23", "2023-24", "2024-25"]
    rows: Dict[str, Dict] = {}
    for s in seasons:
        p = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(p):
            continue
        with open(p) as f:
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


def load_foul_state() -> Dict[Tuple[str, int], Dict[str, float]]:
    if not os.path.exists(FOUL_PARQUET):
        return {}
    df = pd.read_parquet(FOUL_PARQUET)
    out: Dict[Tuple[str, int], Dict[str, float]] = {}
    for _, r in df.iterrows():
        key = (str(r["game_id"]), int(r["period"]))
        out[key] = {c: float(r[c]) for c in V4_FOULS_EXTRA}
    return out


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
    foul_state: Dict[Tuple[str, int], Dict[str, float]],
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
            rec = {
                "game_id": gid,
                "game_date": game_date,
                "snapshot": snapshot,
                "home_team_id": home_team_id,
                "season": season,
                "score_margin": h_cum - a_cum,
                "total_pts": total_pts,
                "pace_so_far": total_pts / minutes_played,
                "q1_delta": hq[0] - aq[0],
                "q2_delta": (hq[1] - aq[1]) if n_qtrs >= 2 else np.nan,
                "q3_delta": (hq[2] - aq[2]) if n_qtrs >= 3 else np.nan,
                "last_q_margin": hq[n_qtrs - 1] - aq[n_qtrs - 1],
                "pregame_win_prob": pregame_wp,  # for v6_hp etc. (model uses raw)
                "polarity_pregame": float(1.0 - pregame_wp),  # for meta-blend
                "home_team_won": home_team_won,
                "q1_usg_avg": q1_usg_avg,
                "halftime_pace_shift": halftime_pace_shift,
                "trailing_team_q4_usg_hhi": trailing_team_q4_usg_hhi,
            }
            # Foul features attached when available (endQ2/endQ3 only;
            # n_qtrs = period for the parquet lookup).
            foul = foul_state.get((str(gid), n_qtrs), {})
            rec["has_fouls"] = int(bool(foul))
            for c in V4_FOULS_EXTRA:
                rec[c] = foul.get(c, np.nan)
            records.append(rec)
    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    return df


# ── walk-forward splits (matches Iter 62/65/68/70 expanding) ──────────────────

def wf_splits(n: int) -> List[Tuple[int, int, int]]:
    min_train = int(n * 0.60)
    test_size = (n - min_train) // N_FOLDS
    splits = []
    for fold in range(N_FOLDS):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < N_FOLDS - 1 else n
        splits.append((train_end, test_start, test_end))
    return splits


# ── component trainers ────────────────────────────────────────────────────────

def _make_lgb(snapshot: str, seed: int):
    import lightgbm as lgb
    win = WINNING_HPS[snapshot]
    hp = dict(BASE_HP_DEFAULTS)
    hp["learning_rate"] = float(win["learning_rate"])
    hp["num_leaves"] = int(win["num_leaves"])
    hp["min_child_samples"] = int(win["min_child_samples"])
    hp["random_state"] = int(seed)
    return lgb.LGBMClassifier(n_jobs=4, verbose=-1, **hp)


def _fit_predict(snapshot: str, X_tr, y_tr, X_te, feature_cols, seed: int) -> np.ndarray:
    X_tr_l = X_tr[feature_cols].copy()
    X_te_l = X_te[feature_cols].copy()
    active_cats = [c for c in CAT_COLS if c in X_tr_l.columns]
    for c in active_cats:
        X_tr_l[c] = X_tr_l[c].astype("category")
        X_te_l[c] = X_te_l[c].astype("category")
    model = _make_lgb(snapshot, seed)
    model.fit(X_tr_l, y_tr,
              categorical_feature=active_cats if active_cats else "auto")
    return model.predict_proba(X_te_l)[:, 1]


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


# ── NNLS solver ───────────────────────────────────────────────────────────────

def fit_nnls_weights(P: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fit non-negative weights w >= 0, sum(w) = 1, minimising (Pw - y)^2.

    Uses scipy NNLS then renormalises to sum 1. If the unconstrained NNLS
    solution is the zero vector (extremely rare), falls back to a uniform mix.
    """
    from scipy.optimize import nnls
    w, _ = nnls(P, y)
    s = w.sum()
    if s <= 1e-12:
        # Degenerate — uniform fallback so we still report something interpretable.
        return np.ones(P.shape[1]) / P.shape[1]
    return w / s


# ── per-snapshot evaluation ───────────────────────────────────────────────────

def evaluate_snapshot(snapshot: str, df: pd.DataFrame) -> Dict[str, Any]:
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import brier_score_loss

    print(f"\n=== Snapshot: {snapshot} ===", flush=True)

    sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
    # For endQ3 we restrict to the v4_fouls-eligible subset so that all
    # components are evaluated on the same row set (apples-to-apples).
    # (Iter 65 also did this restriction for its v4_fouls vs rebaseline comparison.)
    if snapshot == "endQ3":
        sub = sub[sub["has_fouls"] == 1].copy().reset_index(drop=True)
        print(f"  endQ3 restricted to v4_fouls-eligible games: {len(sub)} rows",
              flush=True)

    y_all = sub["home_team_won"].astype(int).values
    n = len(sub)
    print(f"  rows: {n}, home_win_rate: {y_all.mean():.4f}", flush=True)

    splits = wf_splits(n)
    print(f"  WF splits: {[(s[0], s[1], s[2]) for s in splits]}", flush=True)

    components = SNAP_COMPONENTS[snapshot]
    best_single = BEST_SINGLE[snapshot]

    # Per-fold storage: each fold stores OOS preds per component + labels.
    fold_data: List[Dict[str, Any]] = []

    feats_v6 = V6_HP_FEATURES[snapshot]
    feats_v4 = feats_v6 + V4_FOULS_EXTRA  # only used for endQ3

    for fold, (train_end, test_start, test_end) in enumerate(splits):
        if train_end < 30 or test_start >= n:
            print(f"  fold {fold}: skip (insufficient data)", flush=True)
            continue
        X_tr = sub.iloc[:train_end]
        y_tr = sub["home_team_won"].iloc[:train_end]
        X_te = sub.iloc[test_start:test_end]
        y_te = X_te["home_team_won"].astype(int).values
        if len(X_te) < 10:
            print(f"  fold {fold}: skip (test n={len(X_te)})", flush=True)
            continue

        # Component 1: v6_hp raw
        p_v6 = _fit_predict(snapshot, X_tr, y_tr, X_te, feats_v6, SEED)
        # Component 2: v6_hp + isotonic (cross-fold)
        # Component 3 (endQ3 only): v4_fouls raw
        p_v4 = None
        if snapshot == "endQ3":
            p_v4 = _fit_predict(snapshot, X_tr, y_tr, X_te, feats_v4, SEED)
        # Component 3 (endQ2 only): v7_bag5 mean
        p_bag5 = None
        if snapshot == "endQ2":
            bag = [
                _fit_predict(snapshot, X_tr, y_tr, X_te, feats_v6, s)
                for s in BAG_SEEDS
            ]
            p_bag5 = np.mean(np.stack(bag, axis=0), axis=0)
        # Component sigmoid(score_margin/6) and polarity_pregame
        sm = X_te["score_margin"].astype(float).values
        p_sig = sigmoid(sm / 6.0)
        p_poly = X_te["polarity_pregame"].astype(float).values
        p_poly = np.clip(p_poly, 1e-6, 1 - 1e-6)

        per_fold_preds: Dict[str, np.ndarray] = {
            "v6_hp": p_v6,
            "sigmoid_margin": p_sig,
            "polarity_pregame": p_poly,
        }
        if p_v4 is not None:
            per_fold_preds["v4_fouls"] = p_v4
        if p_bag5 is not None:
            per_fold_preds["v7_bag5"] = p_bag5

        fold_data.append({
            "fold": fold,
            "train_n": int(train_end),
            "test_n": int(len(X_te)),
            "y_te": y_te,
            "preds_raw": per_fold_preds,  # 'iso' added after we have prior OOS
        })

    # Now compute isotonic preds (cross-fold over v6_hp raw).
    # Fold 0 — no calibration possible → iso = v6_hp raw (treated as identity).
    # Fold k >=1 — fit isotonic on concatenated prior-fold v6_hp + labels.
    iso_all_p_so_far: List[np.ndarray] = []
    iso_all_y_so_far: List[np.ndarray] = []
    for fd in fold_data:
        v6 = fd["preds_raw"]["v6_hp"]
        if iso_all_p_so_far:
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(np.concatenate(iso_all_p_so_far),
                    np.concatenate(iso_all_y_so_far))
            p_iso = np.clip(iso.transform(v6), 1e-7, 1 - 1e-7)
        else:
            p_iso = v6.copy()
        fd["preds_raw"]["iso"] = p_iso
        iso_all_p_so_far.append(v6)
        iso_all_y_so_far.append(fd["y_te"])

    # Now do cross-fold NNLS blend.
    # Per-fold blend: weights fit on accumulated prior-fold OOS preds → labels.
    # Fold 0: no prior data → blend prediction = best-single prediction.
    cum_P_rows: List[np.ndarray] = []
    cum_y: List[np.ndarray] = []

    per_fold_records: List[Dict[str, Any]] = []
    for fd in fold_data:
        # Stack per-fold preds in canonical component order.
        P_fold = np.stack([fd["preds_raw"][c] for c in components], axis=1)
        y_fold = fd["y_te"]
        single_briers = {
            c: float(brier_score_loss(y_fold, fd["preds_raw"][c]))
            for c in components
        }
        best_brier = single_briers[best_single]

        if cum_P_rows:
            P_train = np.concatenate(cum_P_rows, axis=0)
            y_train = np.concatenate(cum_y, axis=0)
            w = fit_nnls_weights(P_train, y_train)
            blend = np.clip(P_fold @ w, 1e-7, 1 - 1e-7)
            blend_brier = float(brier_score_loss(y_fold, blend))
            blend_applied = True
            w_list = [float(x) for x in w]
        else:
            blend = fd["preds_raw"][best_single]
            blend_brier = best_brier
            blend_applied = False
            w_list = None

        improved = bool(blend_brier <= best_brier)
        per_fold_records.append({
            "fold": fd["fold"],
            "train_n": fd["train_n"],
            "test_n": fd["test_n"],
            "single_briers": single_briers,
            "best_single_brier": best_brier,
            "blend_brier": blend_brier,
            "brier_delta_vs_best": blend_brier - best_brier,
            "blend_applied": blend_applied,
            "improved_or_tied": improved,
            "weights_cross_fold": (
                dict(zip(components, w_list)) if w_list else None
            ),
        })
        cum_P_rows.append(P_fold)
        cum_y.append(y_fold)
        print(f"  fold {fd['fold']}: best_single({best_single})="
              f"{best_brier:.4f}  blend={blend_brier:.4f}  "
              f"delta={blend_brier - best_brier:+.4f}  "
              f"applied={blend_applied}  improved={improved}", flush=True)

    # Final saved weights: fit on folds 0..N-2 OOS, evaluated on the final fold.
    # This is the spec-mandated "fit on folds 0-2, evaluate on fold 3" check.
    final_weights: Optional[Dict[str, float]] = None
    final_eval: Optional[Dict[str, float]] = None
    if len(fold_data) >= 2:
        train_folds = fold_data[:-1]
        last_fold = fold_data[-1]
        P_tr = np.concatenate([
            np.stack([fd["preds_raw"][c] for c in components], axis=1)
            for fd in train_folds
        ], axis=0)
        y_tr_final = np.concatenate([fd["y_te"] for fd in train_folds], axis=0)
        w_final = fit_nnls_weights(P_tr, y_tr_final)
        final_weights = {c: float(w_final[i]) for i, c in enumerate(components)}

        P_last = np.stack([last_fold["preds_raw"][c] for c in components], axis=1)
        y_last = last_fold["y_te"]
        blend_last = np.clip(P_last @ w_final, 1e-7, 1 - 1e-7)
        blend_brier_last = float(brier_score_loss(y_last, blend_last))
        best_last = float(brier_score_loss(y_last, last_fold["preds_raw"][best_single]))
        final_eval = {
            "fold": int(last_fold["fold"]),
            "test_n": int(last_fold["test_n"]),
            "blend_brier": blend_brier_last,
            "best_single_brier": best_last,
            "brier_delta_vs_best": blend_brier_last - best_last,
            "improved_or_tied": bool(blend_brier_last <= best_last),
        }

    # Ship gate
    blend_briers = [r["blend_brier"] for r in per_fold_records]
    best_briers = [r["best_single_brier"] for r in per_fold_records]
    mean_blend = float(np.mean(blend_briers)) if blend_briers else None
    mean_best = float(np.mean(best_briers)) if best_briers else None
    mean_delta = (
        mean_blend - mean_best
        if (mean_blend is not None and mean_best is not None)
        else None
    )
    n_improved = int(sum(r["improved_or_tied"] for r in per_fold_records))
    n_folds = len(per_fold_records)
    folds_gate = n_improved >= 3
    delta_gate = (mean_delta is not None and mean_delta <= -0.001)
    ship = folds_gate and delta_gate

    print(f"  SUMMARY [{snapshot}]: "
          f"mean_blend={mean_blend:.4f}  mean_best({best_single})={mean_best:.4f}  "
          f"delta={mean_delta:+.4f}  "
          f"folds_improved_or_tied={n_improved}/{n_folds}  ship={ship}",
          flush=True)

    return {
        "snapshot": snapshot,
        "n_rows": int(n),
        "best_single_component": best_single,
        "components": components,
        "per_fold_records": [{
            k: (
                {kk: float(vv) for kk, vv in v.items()}
                if isinstance(v, dict) and all(isinstance(x, float) or x is None for x in v.values())
                else v
            )
            for k, v in r.items()
        } for r in per_fold_records],
        "mean_blend_brier": mean_blend,
        "mean_best_single_brier": mean_best,
        "mean_brier_delta_vs_best": mean_delta,
        "n_folds_improved_or_tied": n_improved,
        "n_folds": n_folds,
        "final_nnls_weights": final_weights,
        "final_holdout_eval": final_eval,
        "folds_gate_passed": folds_gate,
        "delta_gate_passed": delta_gate,
        "ships": ship,
    }


def save_blend_json(snapshot: str, eval_result: Dict[str, Any]) -> str:
    """Write data/models/inplay_meta_blend_endq{N}.json (NNLS weights)."""
    out_path = os.path.join(
        MODEL_DIR, f"inplay_meta_blend_{snapshot.lower()}.json"
    )
    payload = {
        "snapshot": snapshot,
        "iter": "iter71",
        "components": eval_result["components"],
        "weights": eval_result["final_nnls_weights"],
        "fold_briers_blend": [r["blend_brier"]
                              for r in eval_result["per_fold_records"]],
        "fold_briers_best_single": [r["best_single_brier"]
                                    for r in eval_result["per_fold_records"]],
        "best_single_component": eval_result["best_single_component"],
        "baseline_brier": eval_result["mean_best_single_brier"],
        "blend_brier": eval_result["mean_blend_brier"],
        "delta": eval_result["mean_brier_delta_vs_best"],
        "n_folds_improved_or_tied": eval_result["n_folds_improved_or_tied"],
        "n_folds": eval_result["n_folds"],
        "final_holdout_eval": eval_result["final_holdout_eval"],
        "trained_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": ("NNLS-fit non-negative weights (renormalised sum=1) over "
                 "per-snapshot Wave 1-3 components. Cross-fold blend "
                 "evaluation; final weights fit on folds [0,N-2], single-pass "
                 "evaluation on fold N-1 in 'final_holdout_eval'."),
        "ships": eval_result["ships"],
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    return out_path


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== Iter 71: Inplay Meta-Blend (NNLS over Wave 1-3 components) ===",
          flush=True)
    print(f"  random_seed={SEED}", flush=True)

    print("\n[1] Loading data ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    qf_summaries = load_quarter_features_summaries()
    foul_state = load_foul_state()
    print(f"  linescores={len(linescores)}, season_games={len(season_games)}, "
          f"qf_summaries={len(qf_summaries)}, foul_state={len(foul_state)}",
          flush=True)

    print("\n[2] Building rows ...", flush=True)
    df = build_rows(linescores, season_games, qf_summaries, foul_state)
    print(f"  total rows: {len(df)}", flush=True)

    print("\n[3] Per-snapshot evaluation ...", flush=True)
    snap_results: Dict[str, Any] = {}
    for snap in SNAPSHOTS:
        snap_results[snap] = evaluate_snapshot(snap, df)

    print("\n[4] Saving NNLS weights JSON per snapshot ...", flush=True)
    saved_paths: Dict[str, str] = {}
    for snap, res in snap_results.items():
        path = save_blend_json(snap, res)
        saved_paths[snap] = path
        print(f"  {snap}: {path}", flush=True)

    ship_summary = {
        snap: {
            "ships": res["ships"],
            "mean_blend_brier": res["mean_blend_brier"],
            "mean_best_single_brier": res["mean_best_single_brier"],
            "mean_delta": res["mean_brier_delta_vs_best"],
            "n_improved_or_tied": res["n_folds_improved_or_tied"],
            "n_folds": res["n_folds"],
            "best_single_component": res["best_single_component"],
            "final_weights": res["final_nnls_weights"],
        }
        for snap, res in snap_results.items()
    }

    any_ships = any(r["ships"] for r in snap_results.values())

    result = {
        "iter": "71",
        "name": "inplay_meta_blend_nnls",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_folds": N_FOLDS,
        "random_seed": SEED,
        "snapshots": snap_results,
        "ship_summary": ship_summary,
        "any_snap_ships": any_ships,
        "saved_blend_paths": saved_paths,
        "elapsed_s": float(time.time() - t0),
    }

    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n[5] Results written to {OUT_JSON}", flush=True)
    print(f"  any snap ships: {any_ships}", flush=True)
    print(f"  elapsed: {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
