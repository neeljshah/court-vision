"""probe_R31_X3_m2_multitask_mlp.py — Multitask MLP for m2_family targets.

R30_W1 recommended target-specific architecture as the next angle. Hypothesis:
the four m2_family targets (total, spread, home_pts, away_pts) are correlated
(total = home+away, spread = home-away) so a SHARED representation should
extract signal beyond independent per-target ensembles. Cycle 23 of the prop
loop validated this exact pattern for AST+STL multitask MLP.

Architecture:
  * Input        : 74 pregame features (same as R30_W1 multi5 ensemble)
  * Shared trunk : Linear(74,128) -> ReLU -> Dropout(0.2)
                   -> Linear(128,64) -> ReLU -> Dropout(0.2)
  * 4 heads      : Linear(64,1) per {total, spread, home_pts, away_pts}
  * Loss         : MSE per head, summed (after target standardization)
  * Optimizer    : Adam(lr=1e-3), early stopping on val loss (patience 20)
  * Seed-ens     : 3 seeds (42, 7, 100), average predictions
  * Standardize  : StandardScaler on features (fit on train) — critical for MLP

Ship gate:
  * new wins on >=3/4 targets by <= -1.5% MAE on 2025-26 holdout
  * no target regresses by more than +1.0%
  * walk-forward 4/4 folds positive across at least 2 targets

LOCAL only.

Usage:
    python scripts/improve_loop/probe_R31_X3_m2_multitask_mlp.py
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)


def _resolve_root() -> str:
    cand = os.environ.get("NBA_AI_ROOT") or r"C:\Users\neelj\nba-ai-system"
    return cand if os.path.isdir(os.path.join(cand, "data", "nba")) else PROJECT_DIR


ROOT_DIR = _resolve_root()
ROOT_DATA_NBA = os.path.join(ROOT_DIR, "data", "nba")
ROOT_MODELS_DIR_OLD = os.path.join(ROOT_DIR, "data", "models", "m2_family")
ROOT_MODELS_DIR_NEW = os.path.join(ROOT_DIR, "data", "models", "m2_family_mlp")
ROOT_CACHE_PATH = os.path.join(ROOT_DIR, "data", "cache", "probe_R31_X3_results.json")

WORKTREE_2526 = os.path.join(PROJECT_DIR, "data", "nba", "season_games_2025-26.json")

# Identical to R30_W1's 74-feature set
FEAT_COLS = [
    "home_off_rtg", "home_def_rtg", "home_net_rtg", "home_pace",
    "home_efg_pct", "home_ts_pct", "home_tov_pct", "home_rest_days",
    "home_back_to_back", "home_last5_wins", "home_season_win_pct",
    "away_off_rtg", "away_def_rtg", "away_net_rtg", "away_pace",
    "away_efg_pct", "away_ts_pct", "away_tov_pct", "away_rest_days",
    "away_back_to_back", "away_last5_wins", "away_season_win_pct",
    "net_rtg_diff", "pace_diff", "home_advantage",
    "home_off_rtg_L10", "home_def_rtg_L10", "home_net_rtg_L10",
    "away_off_rtg_L10", "away_def_rtg_L10", "away_net_rtg_L10",
    "home_efg_L10", "away_efg_L10",
    "home_pace_variance", "away_pace_variance",
    "home_travel_miles", "away_travel_miles",
    "home_top_lineup_net_rtg", "away_top_lineup_net_rtg",
    "iso_matchup_edge", "home_pnr_ppp", "away_pnr_ppp",
    "home_hustle_deflections_pg", "away_hustle_deflections_pg",
    "home_stars_available", "away_stars_available",
    "home_bench_net_rtg", "away_bench_net_rtg",
    "home_tov_pct_L10", "away_tov_pct_L10",
    "home_oreb_pct_L10", "away_oreb_pct_L10",
    "home_ft_rate_L10", "away_ft_rate_L10",
    "home_off_rtg_home_L10", "away_off_rtg_away_L10",
    "home_off_rtg_vs_top_def", "away_off_rtg_vs_top_def",
    "home_srs", "away_srs",
    "home_elo", "away_elo", "elo_differential",
    "home_def_rtg_trend", "away_def_rtg_trend",
    "b2b_diff", "elo_pace_interaction",
    "ref_avg_fouls", "ref_home_win_pct", "ref_fta_tendency",
    "sim_win_prob", "sim_score_diff_mean", "sim_score_diff_std", "sim_pace_adj",
]

# Mirror R30_W1's seed sets so the old-ensemble path is reproducible.
LGB_SEEDS = [42, 7, 100]
XGB_SEEDS = [42, 7]

MLP_SEEDS = [42, 7, 100]

TARGETS = {
    "total":    "total_pts_box",
    "spread":   "score_diff",
    "home_pts": "home_score",
    "away_pts": "away_score",
}
TARGET_ORDER = ["total", "spread", "home_pts", "away_pts"]


# ---------------------------------------------------------------------------
# Data loading (mirrors R30_W1)
# ---------------------------------------------------------------------------
def _load_season(fname: str) -> List[dict]:
    if fname == "season_games_2025-26.json" and os.path.exists(WORKTREE_2526):
        p = WORKTREE_2526
    else:
        p = os.path.join(ROOT_DATA_NBA, fname)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    rows = d.get("rows", d) if isinstance(d, dict) else d
    return rows if isinstance(rows, list) else []


def load_dataset() -> Tuple[pd.DataFrame, List[str]]:
    rows: List[dict] = []
    for fname in ("season_games_2022-23.json", "season_games_2023-24.json",
                  "season_games_2024-25.json", "season_games_2025-26.json"):
        rows.extend(_load_season(fname))
    sg = pd.DataFrame(rows)

    with open(os.path.join(ROOT_DATA_NBA, "linescores_all.json"), encoding="utf-8") as f:
        d = json.load(f)
    ls_rows: List[dict] = []
    for gid, ls in d.items():
        try:
            hq = [float(ls.get(f"home_q{i}", 0) or 0) for i in range(1, 5)]
            aq = [float(ls.get(f"away_q{i}", 0) or 0) for i in range(1, 5)]
        except (TypeError, ValueError):
            continue
        h, a = sum(hq), sum(aq)
        if h <= 0 or a <= 0:
            continue
        ls_rows.append({
            "game_id":       gid,
            "home_score":    h,
            "away_score":    a,
            "score_diff":    h - a,
            "total_pts_box": h + a,
        })
    ls = pd.DataFrame(ls_rows)
    merged = sg.merge(ls, on="game_id", how="inner")
    for col in ("home_off_rtg", "away_off_rtg", "home_pace", "away_pace"):
        merged = merged[merged[col] > 0]
    merged = merged.sort_values("game_date").reset_index(drop=True)
    avail = [c for c in FEAT_COLS if c in merged.columns]
    merged[avail] = merged[avail].fillna(0.0)
    return merged, avail


# ---------------------------------------------------------------------------
# OLD ensemble loader (reuses R30_W1 helpers)
# ---------------------------------------------------------------------------
def load_old_ensembles_from_disk() -> Dict[str, list]:
    import joblib
    out: Dict[str, list] = {}
    for tgt in TARGETS:
        models = []
        ok = True
        for seed in LGB_SEEDS:
            p = os.path.join(ROOT_MODELS_DIR_OLD, f"{tgt}_lgb_s{seed}.joblib")
            if not os.path.exists(p):
                ok = False
                break
            models.append(("lgb", seed, joblib.load(p)))
        if not ok:
            return {}
        for seed in XGB_SEEDS:
            p = os.path.join(ROOT_MODELS_DIR_OLD, f"{tgt}_xgb_s{seed}.joblib")
            if not os.path.exists(p):
                return {}
            models.append(("xgb", seed, joblib.load(p)))
        out[tgt] = models
    return out


def load_old_feature_cols() -> List[str]:
    p = os.path.join(ROOT_MODELS_DIR_OLD, "feature_cols.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def predict_old_ensemble(models: List, X: np.ndarray) -> np.ndarray:
    preds = np.zeros(X.shape[0], dtype=float)
    for _, _, m in models:
        preds += m.predict(X)
    return preds / len(models)


# ---------------------------------------------------------------------------
# MultitaskMLP — PyTorch model
# ---------------------------------------------------------------------------
def _build_torch_model(n_features: int, n_targets: int, dropout: float = 0.2):
    import torch
    import torch.nn as nn

    class MultitaskMLP(nn.Module):
        def __init__(self, n_in: int, n_tgt: int, p_drop: float):
            super().__init__()
            self.trunk = nn.Sequential(
                nn.Linear(n_in, 128),
                nn.ReLU(),
                nn.Dropout(p_drop),
                nn.Linear(128, 64),
                nn.ReLU(),
                nn.Dropout(p_drop),
            )
            self.heads = nn.ModuleList([nn.Linear(64, 1) for _ in range(n_tgt)])

        def forward(self, x):
            h = self.trunk(x)
            outs = [head(h).squeeze(-1) for head in self.heads]
            return torch.stack(outs, dim=1)  # (B, n_tgt)

    return MultitaskMLP(n_features, n_targets, dropout)


def train_multitask_mlp(
    X_train: np.ndarray,
    Y_train: np.ndarray,
    X_val: Optional[np.ndarray] = None,
    Y_val: Optional[np.ndarray] = None,
    seed: int = 42,
    max_epochs: int = 200,
    batch_size: int = 256,
    lr: float = 1e-3,
    patience: int = 20,
    verbose: bool = False,
):
    """Train a single multitask MLP. Returns (model, train_mu_y, train_sd_y).

    Target standardization (z-score) is applied internally so the per-target
    losses are scale-equal (spread has |y| ~ 12, total has |y| ~ 225).
    """
    import torch
    import torch.nn as nn
    import torch.optim as optim

    torch.manual_seed(seed)
    np.random.seed(seed)

    device = torch.device("cpu")  # small model, CPU fine and avoids GPU contention

    n_features = X_train.shape[1]
    n_targets = Y_train.shape[1]
    mu_y = Y_train.mean(axis=0)
    sd_y = Y_train.std(axis=0)
    sd_y = np.where(sd_y < 1e-6, 1.0, sd_y)

    Y_train_z = (Y_train - mu_y) / sd_y

    model = _build_torch_model(n_features, n_targets).to(device)
    opt = optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    X_train_t = torch.from_numpy(X_train.astype(np.float32)).to(device)
    Y_train_t = torch.from_numpy(Y_train_z.astype(np.float32)).to(device)

    do_val = X_val is not None and Y_val is not None and len(X_val) > 0
    if do_val:
        Y_val_z = (Y_val - mu_y) / sd_y
        X_val_t = torch.from_numpy(X_val.astype(np.float32)).to(device)
        Y_val_t = torch.from_numpy(Y_val_z.astype(np.float32)).to(device)

    best_val = float("inf")
    best_state = None
    stale = 0

    n = X_train_t.shape[0]
    for epoch in range(max_epochs):
        model.train()
        perm = torch.randperm(n)
        total = 0.0
        for i in range(0, n, batch_size):
            idx = perm[i:i + batch_size]
            xb = X_train_t[idx]
            yb = Y_train_t[idx]
            opt.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            opt.step()
            total += float(loss.item()) * xb.shape[0]
        train_loss = total / n

        if do_val:
            model.eval()
            with torch.no_grad():
                vp = model(X_val_t)
                vloss = float(loss_fn(vp, Y_val_t).item())
            if vloss + 1e-6 < best_val:
                best_val = vloss
                best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
                stale = 0
            else:
                stale += 1
                if stale >= patience:
                    if verbose:
                        print(f"  [seed {seed}] early stop @ epoch {epoch} val={vloss:.4f}", flush=True)
                    break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return model, mu_y, sd_y


def predict_multitask_mlp(model, X: np.ndarray, mu_y: np.ndarray, sd_y: np.ndarray) -> np.ndarray:
    """Returns (N, n_targets) unstandardized predictions."""
    import torch
    with torch.no_grad():
        xt = torch.from_numpy(X.astype(np.float32))
        pz = model(xt).cpu().numpy()
    return pz * sd_y + mu_y


def train_mlp_seed_ensemble(
    X_train: np.ndarray,
    Y_train: np.ndarray,
    X_val: Optional[np.ndarray] = None,
    Y_val: Optional[np.ndarray] = None,
    seeds: List[int] = MLP_SEEDS,
    verbose: bool = False,
) -> List:
    """Train one model per seed, return list of (model, mu_y, sd_y) tuples."""
    out = []
    for s in seeds:
        m, mu, sd = train_multitask_mlp(
            X_train, Y_train, X_val=X_val, Y_val=Y_val, seed=s, verbose=verbose
        )
        out.append((s, m, mu, sd))
    return out


def predict_mlp_ensemble(ensemble: List, X: np.ndarray) -> np.ndarray:
    """Average predictions across seed-ensemble. Returns (N, n_targets)."""
    preds = None
    for _, model, mu_y, sd_y in ensemble:
        p = predict_multitask_mlp(model, X, mu_y, sd_y)
        preds = p if preds is None else preds + p
    return preds / len(ensemble)


# ---------------------------------------------------------------------------
# Walk-forward evaluation
# ---------------------------------------------------------------------------
def _season_for_row(gid: str) -> str:
    if gid.startswith("00222"):
        return "2022-23"
    if gid.startswith("00223"):
        return "2023-24"
    if gid.startswith("00224"):
        return "2024-25"
    if gid.startswith("00225"):
        return "2025-26"
    return "unknown"


def _build_y_matrix(df: pd.DataFrame) -> np.ndarray:
    return np.column_stack([
        df[TARGETS[t]].astype(float).values for t in TARGET_ORDER
    ])


def walk_forward_eval(
    df: pd.DataFrame,
    feat_cols: List[str],
    old_ensembles: Dict[str, list],
    old_feats: List[str],
) -> Dict[str, dict]:
    """Same 4 expanding folds as R30_W1.
    Returns per-target {folds, mae_old, mae_new, n_train, n_val}.
    """
    from sklearn.preprocessing import StandardScaler

    df = df.copy()
    df["season"] = df["game_id"].apply(_season_for_row)
    s2526 = df[df["season"] == "2025-26"].sort_values("game_date").reset_index(drop=True)
    if len(s2526) >= 2:
        mid = len(s2526) // 2
        first_half_ids = set(s2526.iloc[:mid]["game_id"])
        second_half_ids = set(s2526.iloc[mid:]["game_id"])
    else:
        first_half_ids, second_half_ids = set(), set()

    folds = [
        {"name": "F1_train22_val23",
         "train_mask": df["season"].isin(["2022-23"]),
         "val_mask":   df["season"] == "2023-24",
         "score_old":  False},
        {"name": "F2_train22-23_val24",
         "train_mask": df["season"].isin(["2022-23", "2023-24"]),
         "val_mask":   df["season"] == "2024-25",
         "score_old":  False},
        {"name": "F3_train22-24_val2526H1",
         "train_mask": df["season"].isin(["2022-23", "2023-24", "2024-25"]),
         "val_mask":   df["game_id"].isin(first_half_ids),
         "score_old":  True},
        {"name": "F4_train22-25_val2526H2",
         "train_mask": (df["season"].isin(["2022-23", "2023-24", "2024-25"])
                       | df["game_id"].isin(first_half_ids)),
         "val_mask":   df["game_id"].isin(second_half_ids),
         "score_old":  True},
    ]

    per_target: Dict[str, dict] = {
        t: {"folds": [], "mae_old": [], "mae_new": [], "n_train": [], "n_val": []}
        for t in TARGET_ORDER
    }

    for fold_idx, fold in enumerate(folds, 1):
        train_df = df[fold["train_mask"]].copy()
        val_df = df[fold["val_mask"]].copy()
        n_train, n_val = len(train_df), len(val_df)
        print(f"[WF fold {fold_idx} {fold['name']}] n_train={n_train} n_val={n_val}", flush=True)
        if n_train < 100 or n_val < 10:
            for t in TARGET_ORDER:
                per_target[t]["folds"].append(fold["name"])
                per_target[t]["mae_old"].append(None)
                per_target[t]["mae_new"].append(None)
                per_target[t]["n_train"].append(n_train)
                per_target[t]["n_val"].append(n_val)
            continue

        scaler = StandardScaler()
        X_train_raw = train_df[feat_cols].values
        X_val_raw = val_df[feat_cols].values
        X_train = scaler.fit_transform(X_train_raw)
        X_val = scaler.transform(X_val_raw)
        Y_train = _build_y_matrix(train_df)
        Y_val = _build_y_matrix(val_df)

        # split a small internal val for early stopping (last 10% of train, time-ordered)
        cut = int(len(X_train) * 0.9)
        Xtr, Xes = X_train[:cut], X_train[cut:]
        Ytr, Yes = Y_train[:cut], Y_train[cut:]
        ensemble = train_mlp_seed_ensemble(Xtr, Ytr, X_val=Xes, Y_val=Yes)
        pred_new_all = predict_mlp_ensemble(ensemble, X_val)  # (N, 4)

        # OLD ensembles use ORIGINAL feature ordering, NOT scaled
        X_val_old_order = None
        if fold.get("score_old", False) and old_ensembles and old_feats:
            X_val_old_order = val_df[[c for c in old_feats if c in val_df.columns]].copy()
            for c in old_feats:
                if c not in X_val_old_order.columns:
                    X_val_old_order[c] = 0.0
            X_val_old_order = X_val_old_order[old_feats].values

        for ti, t in enumerate(TARGET_ORDER):
            y_val = Y_val[:, ti]
            pred_new = pred_new_all[:, ti]
            mae_new = float(np.mean(np.abs(pred_new - y_val)))
            if X_val_old_order is not None and old_ensembles.get(t):
                pred_old = predict_old_ensemble(old_ensembles[t], X_val_old_order)
                mae_old = float(np.mean(np.abs(pred_old - y_val)))
            else:
                mae_old = None
            per_target[t]["folds"].append(fold["name"])
            per_target[t]["mae_old"].append(mae_old)
            per_target[t]["mae_new"].append(mae_new)
            per_target[t]["n_train"].append(n_train)
            per_target[t]["n_val"].append(n_val)
            old_str = f"{mae_old:.4f}" if mae_old is not None else "skipped (leak)"
            print(f"  {t:9s}: mae_old={old_str}  mae_new={mae_new:.4f}", flush=True)

    return per_target


def holdout_2025_26_eval(
    df: pd.DataFrame,
    feat_cols: List[str],
    old_ensembles: Dict[str, list],
    old_feats: List[str],
) -> Tuple[Dict[str, dict], Dict[str, np.ndarray]]:
    from sklearn.preprocessing import StandardScaler

    df = df.copy()
    df["season"] = df["game_id"].apply(_season_for_row)
    train_df = df[df["season"].isin(["2022-23", "2023-24", "2024-25"])]
    val_df = df[df["season"] == "2025-26"]
    n_train, n_val = len(train_df), len(val_df)
    print(f"[holdout 2025-26] n_train={n_train} n_val={n_val}", flush=True)

    scaler = StandardScaler()
    X_train_raw = train_df[feat_cols].values
    X_val_raw = val_df[feat_cols].values
    X_train = scaler.fit_transform(X_train_raw)
    X_val_new = scaler.transform(X_val_raw)
    Y_train = _build_y_matrix(train_df)
    Y_val = _build_y_matrix(val_df)

    cut = int(len(X_train) * 0.9)
    Xtr, Xes = X_train[:cut], X_train[cut:]
    Ytr, Yes = Y_train[:cut], Y_train[cut:]
    ensemble = train_mlp_seed_ensemble(Xtr, Ytr, X_val=Xes, Y_val=Yes)
    pred_new_all = predict_mlp_ensemble(ensemble, X_val_new)

    X_val_old = None
    if old_ensembles and old_feats:
        X_val_old = val_df[[c for c in old_feats if c in val_df.columns]].copy()
        for c in old_feats:
            if c not in X_val_old.columns:
                X_val_old[c] = 0.0
        X_val_old = X_val_old[old_feats].values

    out: Dict[str, dict] = {}
    for ti, t in enumerate(TARGET_ORDER):
        y_val = Y_val[:, ti]
        pred_new = pred_new_all[:, ti]
        mae_new = float(np.mean(np.abs(pred_new - y_val)))
        if X_val_old is not None and old_ensembles.get(t):
            pred_old = predict_old_ensemble(old_ensembles[t], X_val_old)
            mae_old = float(np.mean(np.abs(pred_old - y_val)))
        else:
            mae_old = None
        delta_pct = ((mae_new - mae_old) / mae_old * 100.0) if mae_old else None
        out[t] = {
            "mae_old":   mae_old,
            "mae_new":   mae_new,
            "delta_pct": delta_pct,
            "n_train":   int(n_train),
            "n_val":     int(n_val),
        }
        old_str = f"{mae_old:.4f}" if mae_old is not None else "n/a "
        dpct = f"{delta_pct:+.2f}%" if delta_pct is not None else "n/a"
        print(f"  {t:9s}: old={old_str}  new={mae_new:.4f}  delta={dpct}", flush=True)

    debug = {"pred_holdout": pred_new_all, "scaler_mean": scaler.mean_, "scaler_scale": scaler.scale_}
    return out, debug


# ---------------------------------------------------------------------------
# Ship gate
# ---------------------------------------------------------------------------
def evaluate_ship_gate(holdout: Dict[str, dict], per_target_wf: Dict[str, dict]) -> Dict:
    targets_improving = 0
    worst_regress_pct = 0.0
    wf_folds_passing = 0
    wf_full_pass_targets = 0
    n_targets_with_old = 0

    for t in TARGET_ORDER:
        h = holdout[t]
        if h.get("mae_old") is None:
            continue
        n_targets_with_old += 1
        dp = h["delta_pct"]
        if dp is not None and dp <= -1.5:
            targets_improving += 1
        if dp is not None and dp > worst_regress_pct:
            worst_regress_pct = dp
        wf = per_target_wf[t]
        # Only head-to-head folds (both old + new present) count. Folds where
        # OLD wasn't scored (F1/F2 — old saw the data) are skipped, not failed.
        head_to_head = [(mo, mn) for mo, mn in zip(wf["mae_old"], wf["mae_new"])
                        if mo is not None and mn is not None]
        per_fold_pass = sum(1 for mo, mn in head_to_head if mn <= mo)
        wf_folds_passing += per_fold_pass
        if head_to_head and per_fold_pass == len(head_to_head):
            wf_full_pass_targets += 1

    cond_3_of_4 = targets_improving >= 3
    cond_no_regress = worst_regress_pct <= 1.0
    cond_wf_2tgt = wf_full_pass_targets >= 2

    decision = "SHIP" if (cond_3_of_4 and cond_no_regress and cond_wf_2tgt) else "REJECT"
    reasons = []
    if not cond_3_of_4:
        reasons.append(f"only {targets_improving}/4 targets improve by >=1.5% on 2025-26 holdout")
    if not cond_no_regress:
        reasons.append(f"worst regression {worst_regress_pct:+.2f}% exceeds +1% cap")
    if not cond_wf_2tgt:
        reasons.append(f"only {wf_full_pass_targets} targets pass all WF folds (need >=2)")
    return {
        "decision":              decision,
        "n_targets_improving":   targets_improving,
        "worst_regress_pct":     worst_regress_pct,
        "wf_folds_passing":      wf_folds_passing,
        "wf_full_pass_targets":  wf_full_pass_targets,
        "n_targets_with_old":    n_targets_with_old,
        "reasons":               reasons,
    }


# ---------------------------------------------------------------------------
# Persistence (SHIP path) — saves to m2_family_mlp/, does NOT touch m2_family/
# ---------------------------------------------------------------------------
def persist_artifacts(df: pd.DataFrame, feat_cols: List[str]) -> None:
    """Train on FULL dataset and save model + scaler artifacts to disk."""
    import torch
    import joblib
    from sklearn.preprocessing import StandardScaler

    os.makedirs(ROOT_MODELS_DIR_NEW, exist_ok=True)
    scaler = StandardScaler()
    X = scaler.fit_transform(df[feat_cols].values)
    Y = _build_y_matrix(df)
    # full-dataset training: no external val split, use last 10% time-ordered for early stop
    cut = int(len(X) * 0.9)
    Xtr, Xes = X[:cut], X[cut:]
    Ytr, Yes = Y[:cut], Y[cut:]
    ensemble = train_mlp_seed_ensemble(Xtr, Ytr, X_val=Xes, Y_val=Yes)

    seed_labels = []
    for seed, model, mu_y, sd_y in ensemble:
        lab = f"mlp_s{seed}"
        torch.save({
            "state_dict": model.state_dict(),
            "mu_y": mu_y.tolist(),
            "sd_y": sd_y.tolist(),
            "n_features": len(feat_cols),
            "n_targets": len(TARGET_ORDER),
            "target_order": TARGET_ORDER,
        }, os.path.join(ROOT_MODELS_DIR_NEW, f"{lab}.pt"))
        seed_labels.append(lab)

    joblib.dump(scaler, os.path.join(ROOT_MODELS_DIR_NEW, "feature_scaler.joblib"))
    with open(os.path.join(ROOT_MODELS_DIR_NEW, "feature_cols.json"), "w") as f:
        json.dump(feat_cols, f, indent=2)

    manifest = {
        "version":         "M2_family_mlp_v1_R31_X3",
        "trained_at":      time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_games":         int(len(df)),
        "n_features":      int(len(feat_cols)),
        "n_targets":       len(TARGET_ORDER),
        "target_order":    TARGET_ORDER,
        "mlp_seeds":       MLP_SEEDS,
        "architecture":    "Linear(74,128)->ReLU->Dropout(0.2)->Linear(128,64)->ReLU->Dropout(0.2)->4xLinear(64,1)",
        "loss":            "summed-MSE on z-scored targets",
        "optimizer":       "Adam(lr=1e-3)",
        "early_stop":      "patience=20 on 10% time-ordered val split",
        "seed_models":     seed_labels,
        "scaler":          "feature_scaler.joblib (sklearn StandardScaler on features)",
        "probe_ancestry":  {
            "round": "R31_X3",
            "predecessor": "R30_W1 multi5 ensemble (REJECT, +0.30% home_pts regress)",
            "hypothesis": "shared trunk across correlated targets extracts signal beyond per-target ensembles",
        },
        "usage": "Load each .pt via torch.load, restore state_dict into _build_torch_model, "
                 "scale features with feature_scaler.joblib, average predictions across seeds.",
    }
    with open(os.path.join(ROOT_MODELS_DIR_NEW, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Skip writing artifacts on SHIP — just print decision.")
    args = ap.parse_args()

    t0 = time.time()
    print(f"[R31_X3] root={ROOT_DIR}", flush=True)
    print(f"[R31_X3] new_models_dir={ROOT_MODELS_DIR_NEW}", flush=True)

    try:
        import torch  # noqa: F401
    except ImportError as exc:
        print(f"[R31_X3] BLOCKED: torch missing — {exc}", flush=True)
        return 2

    print("[1] loading dataset ...", flush=True)
    df, feat_cols = load_dataset()
    print(f"  merged: n={len(df)}  n_features={len(feat_cols)}", flush=True)
    seasons_count = df["game_id"].apply(_season_for_row).value_counts().to_dict()
    print(f"  by season: {seasons_count}", flush=True)

    print("[2] loading OLD m2_family multi5 artifacts ...", flush=True)
    old_ensembles = load_old_ensembles_from_disk()
    old_feats = load_old_feature_cols()
    if not old_ensembles:
        print("  [warn] OLD m2_family artifacts missing", flush=True)
    else:
        print(f"  OLD loaded: {len(old_ensembles)} targets, {len(old_feats)} feature cols", flush=True)

    print("\n[3] HOLDOUT 2025-26 evaluation ...", flush=True)
    holdout, _debug = holdout_2025_26_eval(df, feat_cols, old_ensembles, old_feats)

    print("\n[4] WALK-FORWARD 4 folds ...", flush=True)
    wf = walk_forward_eval(df, feat_cols, old_ensembles, old_feats)

    print("\n[5] evaluating SHIP gate ...", flush=True)
    gate = evaluate_ship_gate(holdout, wf)
    print(f"  decision: {gate['decision']}", flush=True)
    print(f"  targets_improving:  {gate['n_targets_improving']}/4", flush=True)
    print(f"  worst_regress_pct:  {gate['worst_regress_pct']:+.2f}%", flush=True)
    print(f"  wf_folds_passing:   {gate['wf_folds_passing']}/16", flush=True)
    print(f"  wf_full_pass_tgts:  {gate['wf_full_pass_targets']}/4", flush=True)
    if gate["reasons"]:
        for r in gate["reasons"]:
            print(f"  reason: {r}", flush=True)

    if gate["decision"] == "SHIP" and not args.dry_run:
        print("\n[6] persisting MLP artifacts to m2_family_mlp/ ...", flush=True)
        persist_artifacts(df, feat_cols)

    runtime_min = (time.time() - t0) / 60.0
    n_train_rows = int(holdout[TARGET_ORDER[0]]["n_train"])
    n_val_rows = int(holdout[TARGET_ORDER[0]]["n_val"])
    payload = {
        "probe":                 "R31_X3_m2_multitask_mlp",
        "computed_at":           time.strftime("%Y-%m-%dT%H:%M:%S"),
        "decision":              gate["decision"],
        "runtime_min":           round(runtime_min, 2),
        "n_train_rows":          n_train_rows,
        "n_val_rows_2025_26":    n_val_rows,
        "architecture":          "Linear(74,128)->ReLU->Dropout(0.2)->Linear(128,64)->ReLU->Dropout(0.2)->4xLinear(64,1), MLP_SEEDS=[42,7,100], Adam(lr=1e-3), MSE on z-scored y, early stop patience=20",
        "per_target_mae_old":    {t: holdout[t]["mae_old"] for t in TARGET_ORDER},
        "per_target_mae_new":    {t: holdout[t]["mae_new"] for t in TARGET_ORDER},
        "per_target_delta_pct":  {t: holdout[t]["delta_pct"] for t in TARGET_ORDER},
        "per_target_wf_folds":   {t: wf[t]["folds"] for t in TARGET_ORDER},
        "per_target_wf_mae_old": {t: wf[t]["mae_old"] for t in TARGET_ORDER},
        "per_target_wf_mae_new": {t: wf[t]["mae_new"] for t in TARGET_ORDER},
        "per_target_wf_folds_positive": {
            t: sum(
                1 for mo, mn in zip(wf[t]["mae_old"], wf[t]["mae_new"])
                if mo is not None and mn is not None and mn <= mo
            )
            for t in TARGET_ORDER
        },
        "n_targets_improving":   gate["n_targets_improving"],
        "worst_regress_pct":     gate["worst_regress_pct"],
        "wf_folds_passing":      gate["wf_folds_passing"],
        "wf_full_pass_targets":  gate["wf_full_pass_targets"],
        "reasons":               gate["reasons"],
        "seasons_count":         {k: int(v) for k, v in seasons_count.items()},
        "feat_cols_count":       len(feat_cols),
    }
    os.makedirs(os.path.dirname(ROOT_CACHE_PATH), exist_ok=True)
    with open(ROOT_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\n[R31_X3] wrote -> {ROOT_CACHE_PATH}", flush=True)
    print(f"[R31_X3] runtime: {runtime_min:.2f} min", flush=True)
    return 0 if gate["decision"] in ("SHIP", "REJECT") else 1


if __name__ == "__main__":
    sys.exit(main())
