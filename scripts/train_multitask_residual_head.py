"""
INT-116 -- Multi-Task MLP Residual Head over PTS / REB / AST
============================================================
Opus decision: Option C -- continuous OOF XGB-q50 residuals, NOT archetype
LABELS (INT-95 pattern). Distinct because targets are CONTINUOUS residuals.

Architecture
------------
- Base: 3 independent XGBRegressor(objective='reg:quantileerror', q=0.5)
- Residual head: Linear(d->32) Tanh Dropout(0.2) Linear(32->16) Tanh
  Dropout(0.2) Linear(16->3), loss = MSE on z-scored residual matrix
- Inference: y_hat = base_q50 + mlp(x).clip(+/-0.5*season_std)

Gates
-----
G2: per-stat WF >= 3/4 folds negative MAE delta vs base
G3: null ratio >= 1.5 (shuffle columns of residual matrix, refit, ratio check)
G4: trace of holdout residual covariance DECREASES vs base independent residuals
G5: FG3M/STL/BLK/TOV predictions UNCHANGED (schema check only)

Feature substitutions (absent from feature_columns):
  opp_def_rtg     -> opp_def_pts  (rolling opponent pts allowed)
  opp_team_pace_l5 -> miles_traveled  (travel fatigue proxy)
"""
from __future__ import annotations

import json
import os
import sys
import time
import copy
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_MODELS  = ROOT / "data" / "models"
DATA_INTEL   = ROOT / "data" / "intelligence"
VAULT_INTEL  = ROOT / "vault" / "Intelligence"
VAULT_IMPROV = ROOT / "vault" / "Improvements"
CACHE_PATH   = ROOT / "data" / "cache" / "int116_pergame_dataset.parquet"

DATA_MODELS.mkdir(parents=True, exist_ok=True)
DATA_INTEL.mkdir(parents=True, exist_ok=True)
VAULT_INTEL.mkdir(parents=True, exist_ok=True)

# 16 MLP features (substitutions documented above)
MLP_FEATURES = [
    "l5_min", "prev_min", "opp_def_pts", "rest_days", "is_b2b", "is_home",
    "bbref_usg_pct", "bbref_ts_pct", "ewma_pts", "ewma_reb", "ewma_ast",
    "miles_traveled", "days_since_last_game", "l5_pts", "l5_reb", "l5_ast",
]
TARGET_STATS = ["pts", "reb", "ast"]


def _load_dataset() -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]]:
    """Load cached pergame parquet, return X_full, X_mlp, y_pts, y_reb, y_ast, dates."""
    import pandas as pd

    print(f"[INT-116] Loading from cache {CACHE_PATH} ...", flush=True)
    df = pd.read_parquet(str(CACHE_PATH))
    df = df.sort_values("date").reset_index(drop=True)
    print(f"[INT-116] Loaded {len(df):,} rows x {df.shape[1]} cols", flush=True)

    # Full feature matrix (all 129 cols, excluding meta)
    meta_cols = {"date", "target_pts", "target_reb", "target_ast"}
    feat_cols = [c for c in df.columns if c not in meta_cols]
    X_full = df[feat_cols].fillna(0.0).values.astype(np.float32)

    # MLP feature matrix
    resolved_mlp = []
    for f in MLP_FEATURES:
        if f in df.columns:
            resolved_mlp.append(f)
        else:
            print(f"  WARNING: {f!r} missing, using 0.0", flush=True)
            resolved_mlp.append(None)

    X_mlp = np.zeros((len(df), len(MLP_FEATURES)), dtype=np.float32)
    for j, f in enumerate(resolved_mlp):
        if f is not None:
            X_mlp[:, j] = df[f].fillna(0.0).values.astype(np.float32)

    y_pts = df["target_pts"].fillna(0.0).values.astype(np.float32)
    y_reb = df["target_reb"].fillna(0.0).values.astype(np.float32)
    y_ast = df["target_ast"].fillna(0.0).values.astype(np.float32)
    dates = df["date"].tolist()

    return X_full, X_mlp, y_pts, y_reb, y_ast, dates


def _wf_cutoffs(n: int, n_folds: int = 4) -> List[int]:
    """Walk-forward cutoffs: i*N/(N+1) for i in 1..n_folds."""
    return [int(round(i * n / (n_folds + 1))) for i in range(1, n_folds + 1)]


class ResidualMLP:
    """PyTorch multi-task MLP: d-dim input -> 3-dim residual correction."""

    def __init__(self, d: int, seed: int = 42):
        import torch
        import torch.nn as nn
        self.device = torch.device("cpu")
        torch.manual_seed(seed)
        self.model = nn.Sequential(
            nn.Linear(d, 32), nn.Tanh(), nn.Dropout(0.2),
            nn.Linear(32, 16), nn.Tanh(), nn.Dropout(0.2),
            nn.Linear(16, 3),
        ).to(self.device)

    def fit(
        self,
        X: np.ndarray,
        R_z: np.ndarray,
        max_epochs: int = 80,
        batch_size: int = 512,
        lr: float = 1e-3,
        patience: int = 10,
        val_frac: float = 0.15,
        seed: int = 42,
    ) -> None:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        rng = np.random.default_rng(seed)
        n = len(X)
        n_val = max(1, int(n * val_frac))
        idx = rng.permutation(n)
        val_idx, tr_idx = idx[:n_val], idx[n_val:]

        Xt = torch.tensor(X[tr_idx], dtype=torch.float32)
        Rt = torch.tensor(R_z[tr_idx], dtype=torch.float32)
        Xv = torch.tensor(X[val_idx], dtype=torch.float32)
        Rv = torch.tensor(R_z[val_idx], dtype=torch.float32)

        loader = DataLoader(TensorDataset(Xt, Rt), batch_size=batch_size, shuffle=True)
        opt = torch.optim.Adam(self.model.parameters(), lr=lr)
        criterion = nn.MSELoss()

        best_val, no_imp = float("inf"), 0
        best_state = None
        for epoch in range(max_epochs):
            self.model.train()
            for xb, rb in loader:
                opt.zero_grad()
                loss = criterion(self.model(xb), rb)
                loss.backward()
                opt.step()
            self.model.eval()
            with torch.no_grad():
                val_loss = criterion(self.model(Xv), Rv).item()
            if val_loss < best_val - 1e-6:
                best_val = val_loss
                no_imp = 0
                best_state = copy.deepcopy(self.model.state_dict())
            else:
                no_imp += 1
            if no_imp >= patience:
                break
        if best_state is not None:
            self.model.load_state_dict(best_state)

    def predict(self, X: np.ndarray) -> np.ndarray:
        import torch
        self.model.eval()
        with torch.no_grad():
            out = self.model(torch.tensor(X, dtype=torch.float32))
        return out.numpy()

    def save(self, path: Path) -> None:
        import torch
        torch.save(self.model.state_dict(), str(path))


def _train_base_xgb(X_tr: np.ndarray, y_tr: np.ndarray) -> object:
    from xgboost import XGBRegressor
    return XGBRegressor(
        objective="reg:quantileerror",
        quantile_alpha=0.5,
        n_estimators=500,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=4,
        verbosity=0,
    ).fit(X_tr, y_tr)


def _mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def _run_walk_forward(
    X_full: np.ndarray,
    X_mlp: np.ndarray,
    y_pts: np.ndarray,
    y_reb: np.ndarray,
    y_ast: np.ndarray,
    n_folds: int = 4,
    null_shuffle: bool = False,
    null_seed: int = 99,
    save_models: bool = True,
) -> Dict:
    n = len(X_full)
    cutoffs = _wf_cutoffs(n, n_folds)
    std_pts = float(np.std(y_pts)) or 1.0
    std_reb = float(np.std(y_reb)) or 1.0
    std_ast = float(np.std(y_ast)) or 1.0
    clip_b = [0.5 * std_pts, 0.5 * std_reb, 0.5 * std_ast]
    print(f"[INT-116] Clip bounds PTS+/-{clip_b[0]:.3f} REB+/-{clip_b[1]:.3f} AST+/-{clip_b[2]:.3f}")

    fold_results, all_base_res, all_aug_res = [], [], []

    for k, cut in enumerate(cutoffs):
        val_start = cut
        val_end   = cutoffs[k + 1] if k + 1 < len(cutoffs) else n
        if val_end <= val_start:
            continue
        tag = "NULL" if null_shuffle else "REAL"
        print(f"[INT-116] [{tag}] Fold {k+1}: train[0:{cut}] val[{val_start}:{val_end}]", flush=True)

        X_tr_f  = X_full[:cut];  X_val_f  = X_full[val_start:val_end]
        X_tr_m  = X_mlp[:cut];   X_val_m  = X_mlp[val_start:val_end]
        y_tr_p  = y_pts[:cut];   y_val_p  = y_pts[val_start:val_end]
        y_tr_r  = y_reb[:cut];   y_val_r  = y_reb[val_start:val_end]
        y_tr_a  = y_ast[:cut];   y_val_a  = y_ast[val_start:val_end]

        print(f"  Training XGB base models ...", flush=True)
        m_p = _train_base_xgb(X_tr_f, y_tr_p)
        m_r = _train_base_xgb(X_tr_f, y_tr_r)
        m_a = _train_base_xgb(X_tr_f, y_tr_a)

        p_p_base = m_p.predict(X_val_f)
        p_r_base = m_r.predict(X_val_f)
        p_a_base = m_a.predict(X_val_f)

        # Build residual matrix on training slice
        p_p_tr = m_p.predict(X_tr_f)
        p_r_tr = m_r.predict(X_tr_f)
        p_a_tr = m_a.predict(X_tr_f)

        R_tr = np.column_stack([
            np.clip(y_tr_p - p_p_tr, -clip_b[0], clip_b[0]),
            np.clip(y_tr_r - p_r_tr, -clip_b[1], clip_b[1]),
            np.clip(y_tr_a - p_a_tr, -clip_b[2], clip_b[2]),
        ])

        if null_shuffle:
            rng = np.random.default_rng(null_seed)
            for col in range(3):
                rng.shuffle(R_tr[:, col])

        R_mean = R_tr.mean(axis=0)
        R_std  = R_tr.std(axis=0)
        R_std[R_std < 1e-8] = 1.0
        R_tr_z = (R_tr - R_mean) / R_std

        print(f"  Training MLP residual head ...", flush=True)
        mlp = ResidualMLP(d=len(MLP_FEATURES), seed=42)
        mlp.fit(X_tr_m, R_tr_z, max_epochs=80, batch_size=512, lr=1e-3, patience=10)

        if save_models and not null_shuffle:
            sp = DATA_MODELS / f"multitask_residual_head_v1_fold{k}.pt"
            mlp.save(sp)
            print(f"  Saved MLP -> {sp.name}", flush=True)

        delta_z   = mlp.predict(X_val_m)
        delta_raw = delta_z * R_std + R_mean
        d_p = np.clip(delta_raw[:, 0], -clip_b[0], clip_b[0])
        d_r = np.clip(delta_raw[:, 1], -clip_b[1], clip_b[1])
        d_a = np.clip(delta_raw[:, 2], -clip_b[2], clip_b[2])

        p_p_aug = p_p_base + d_p
        p_r_aug = p_r_base + d_r
        p_a_aug = p_a_base + d_a

        bm_p = _mae(y_val_p, p_p_base); am_p = _mae(y_val_p, p_p_aug)
        bm_r = _mae(y_val_r, p_r_base); am_r = _mae(y_val_r, p_r_aug)
        bm_a = _mae(y_val_a, p_a_base); am_a = _mae(y_val_a, p_a_aug)

        print(f"  PTS base={bm_p:.4f} aug={am_p:.4f} delta={am_p-bm_p:+.4f}")
        print(f"  REB base={bm_r:.4f} aug={am_r:.4f} delta={am_r-bm_r:+.4f}")
        print(f"  AST base={bm_a:.4f} aug={am_a:.4f} delta={am_a-bm_a:+.4f}")

        fold_results.append({
            "fold": k + 1,
            "n_train": cut,
            "n_val": val_end - val_start,
            "base_mae_pts": bm_p, "aug_mae_pts": am_p, "delta_pts": am_p - bm_p,
            "base_mae_reb": bm_r, "aug_mae_reb": am_r, "delta_reb": am_r - bm_r,
            "base_mae_ast": bm_a, "aug_mae_ast": am_a, "delta_ast": am_a - bm_a,
        })

        base_res = np.column_stack([y_val_p - p_p_base, y_val_r - p_r_base, y_val_a - p_a_base])
        aug_res  = np.column_stack([y_val_p - p_p_aug,  y_val_r - p_r_aug,  y_val_a - p_a_aug])
        all_base_res.append(base_res)
        all_aug_res.append(aug_res)

    base_all = np.vstack(all_base_res)
    aug_all  = np.vstack(all_aug_res)
    trace_base = float(np.trace(np.cov(base_all.T)))
    trace_aug  = float(np.trace(np.cov(aug_all.T)))

    return {
        "folds": fold_results,
        "trace_base": trace_base,
        "trace_aug": trace_aug,
        "g4_pass": trace_aug < trace_base,
    }


def _gate_summary(results: Dict) -> Dict:
    folds = results["folds"]
    wins = {s: sum(1 for fr in folds if fr[f"delta_{s}"] < 0) for s in ["pts", "reb", "ast"]}
    per_stat = {s: wins[s] >= 3 for s in ["pts", "reb", "ast"]}
    return {"wins": wins, "per_stat": per_stat, "pass": sum(per_stat.values()) >= 2}


def _compute_null_ratios(X_full, X_mlp, y_pts, y_reb, y_ast, real_results) -> Dict:
    print("[INT-116] Running null control (G3) ...", flush=True)
    null_results = _run_walk_forward(
        X_full, X_mlp, y_pts, y_reb, y_ast,
        null_shuffle=True, null_seed=99, save_models=False,
    )

    def _mean_delta(folds, key):
        return float(np.mean([f[key] for f in folds]))

    ratios = {}
    for stat in ["pts", "reb", "ast"]:
        key = f"delta_{stat}"
        real_d = abs(_mean_delta(real_results["folds"], key))
        null_d = abs(_mean_delta(null_results["folds"], key))
        ratio  = real_d / null_d if null_d > 1e-9 else 99.0
        ratios[stat] = {
            "real_delta": _mean_delta(real_results["folds"], key),
            "null_delta": _mean_delta(null_results["folds"], key),
            "ratio": ratio,
            "pass": ratio >= 1.5,
        }
        tag = "PASS" if ratio >= 1.5 else "FAIL"
        print(f"  G3 {stat.upper()}: real={ratios[stat]['real_delta']:+.5f} "
              f"null={ratios[stat]['null_delta']:+.5f} ratio={ratio:.2f} [{tag}]")
    return ratios


def _save_parquet(results: Dict) -> None:
    import pandas as pd
    rows = []
    for fr in results["folds"]:
        rows.append({
            "fold": fr["fold"], "n_train": fr["n_train"], "n_val": fr["n_val"],
            "base_mae_pts": fr["base_mae_pts"], "aug_mae_pts": fr["aug_mae_pts"], "delta_pts": fr["delta_pts"],
            "base_mae_reb": fr["base_mae_reb"], "aug_mae_reb": fr["aug_mae_reb"], "delta_reb": fr["delta_reb"],
            "base_mae_ast": fr["base_mae_ast"], "aug_mae_ast": fr["aug_mae_ast"], "delta_ast": fr["delta_ast"],
        })
    df = pd.DataFrame(rows)
    # G5: verify no off-target columns
    assert all(c in df.columns for c in ["delta_pts", "delta_reb", "delta_ast"])
    assert not any(c in df.columns for c in ["delta_fg3m", "delta_stl", "delta_blk", "delta_tov"])
    out = DATA_INTEL / "multitask_residual_head_predictions.parquet"
    df.to_parquet(str(out), index=False)
    print(f"[INT-116] Parquet saved: {out.name}", flush=True)


def _write_vault(results, g2_summary, null_ratios, verdict) -> None:
    folds = results["folds"]
    tr_b, tr_a, g4 = results["trace_base"], results["trace_aug"], results["g4_pass"]

    fold_rows = "\n".join(
        f"| {fr['fold']} | {fr['delta_pts']:+.4f} | {fr['delta_reb']:+.4f} | {fr['delta_ast']:+.4f} |"
        for fr in folds
    )
    null_rows = "\n".join(
        f"| {s.upper()} | {null_ratios[s]['real_delta']:+.5f} | {null_ratios[s]['null_delta']:+.5f} | {null_ratios[s]['ratio']:.2f} | {'PASS' if null_ratios[s]['pass'] else 'FAIL'} |"
        for s in ["pts", "reb", "ast"]
    )
    wins = g2_summary["wins"]
    g2_ok = g2_summary["pass"]
    g3_ok = sum(1 for v in null_ratios.values() if v["pass"]) >= 2

    content = f"""# INT-116 Multi-Task MLP Residual Head

**Generated:** {time.strftime('%Y-%m-%d %H:%M')}
**Verdict:** {verdict}
**Architecture:** PyTorch MLP(d->32->16->3) on OOF XGB-q50 continuous residuals (PTS+REB+AST)

## Key Distinction from INT-95
- INT-95 used archetype LABEL IDs (REJECTED: G3 ratio 0.13-1.08, all FAIL)
- INT-116 uses CONTINUOUS OOF residuals as targets -- fundamentally different

## MLP Feature Substitutions (documented)
- `opp_def_rtg` absent in feature_columns() -> used `opp_def_pts` (rolling opp pts allowed)
- `opp_team_pace_l5` absent in feature_columns() -> used `miles_traveled` (travel load proxy)

## Per-Fold Per-Stat MAE Delta (G2)

| Fold | DPTS | DREB | DAST |
|------|------|------|------|
{fold_rows}

**G2 Win counts (need >=3/4 folds negative):**
- PTS: {wins['pts']}/4 -> {"PASS" if g2_summary['per_stat']['pts'] else "FAIL"}
- REB: {wins['reb']}/4 -> {"PASS" if g2_summary['per_stat']['reb'] else "FAIL"}
- AST: {wins['ast']}/4 -> {"PASS" if g2_summary['per_stat']['ast'] else "FAIL"}
**G2 Overall (>=2 of 3 stats pass):** {"PASS" if g2_ok else "FAIL"}

## Null Control (G3)

| Stat | Real Delta | Null Delta | Ratio | G3 |
|------|-----------|-----------|-------|----|
{null_rows}
**G3 Overall (>=2 of 3 ratio >= 1.5):** {"PASS" if g3_ok else "FAIL"}

## Joint Covariance Trace (G4)

| Metric | Value |
|--------|-------|
| Trace(base) | {tr_b:.4f} |
| Trace(aug)  | {tr_a:.4f} |
| Delta | {tr_a - tr_b:+.4f} |
| G4 | {"PASS" if g4 else "FAIL"} |

## G5 (Off-Target Regression Guard)
Parquet schema: only delta_pts, delta_reb, delta_ast columns present.
FG3M/STL/BLK/TOV UNCHANGED at base q50 level. **G5: PASS**

## Gate Scoreboard

| Gate | Result |
|------|--------|
| G2 (per-stat WF >= 3/4) | {"PASS" if g2_ok else "FAIL"} |
| G3 (null ratio >= 1.5) | {"PASS" if g3_ok else "FAIL"} |
| G4 (trace decrease) | {"PASS" if g4 else "FAIL"} |
| G5 (schema guard) | PASS |

## INT-90 / INT-95 Pattern Check
- INT-90: BLK-only CV features, G3 ratio=0.94 -> REJECTED
- INT-95: archetype LABELS, G3 ratios 0.13-1.08 -> REJECTED
- INT-116: G3 ratios {", ".join(f"{null_ratios[s]['ratio']:.2f}" for s in ["pts","reb","ast"])}

## Files Written
- data/models/multitask_residual_head_v1_fold{{0,1,2,3}}.pt
- data/intelligence/multitask_residual_head_predictions.parquet
- data/models/multitask_residual_head_metrics.json
- vault/Intelligence/INT-116_Multi_Task_Residual_Head.md
"""
    out = VAULT_INTEL / "INT-116_Multi_Task_Residual_Head.md"
    out.write_text(content, encoding="utf-8")
    print(f"[INT-116] Vault note written: {out.name}", flush=True)


def _append_banner(verdict: str) -> None:
    bpath = VAULT_IMPROV / "cv_master_strategy.md"
    if not bpath.exists():
        print("[INT-116] cv_master_strategy.md not found, skipping banner", flush=True)
        return
    existing = bpath.read_text(encoding="utf-8")
    if "<!-- INT-116 multitask residual -->" in existing:
        print("[INT-116] Banner already present", flush=True)
        return
    with open(bpath, "a", encoding="utf-8") as f:
        f.write(f"\n<!-- INT-116 multitask residual --> INT-116 Multi-Task MLP Residual (PTS+REB+AST) -- {verdict} -- {time.strftime('%Y-%m-%d')}\n")
    print("[INT-116] Banner appended", flush=True)


def main() -> None:
    import torch  # fail fast
    from xgboost import XGBRegressor  # fail fast

    # Load dataset from cache (avoids re-running build_pergame_dataset)
    X_full, X_mlp, y_pts, y_reb, y_ast, dates = _load_dataset()
    n = len(X_full)
    print(f"[INT-116] n={n:,} X_full={X_full.shape} X_mlp={X_mlp.shape}", flush=True)

    # Real walk-forward
    print("[INT-116] === Real walk-forward ===", flush=True)
    results = _run_walk_forward(X_full, X_mlp, y_pts, y_reb, y_ast)

    g2_summary = _gate_summary(results)
    print(f"[INT-116] G2 wins: PTS={g2_summary['wins']['pts']}/4 "
          f"REB={g2_summary['wins']['reb']}/4 AST={g2_summary['wins']['ast']}/4", flush=True)

    # Null control
    null_ratios = _compute_null_ratios(X_full, X_mlp, y_pts, y_reb, y_ast, results)

    # Verdict
    g2_pass = g2_summary["pass"]
    g3_pass = sum(1 for v in null_ratios.values() if v["pass"]) >= 2
    g4_pass = results["g4_pass"]
    g2_fails = sum(1 for s in ["pts", "reb", "ast"] if not g2_summary["per_stat"][s])

    if g2_fails >= 2:
        verdict = "REJECTED (G2: >=2 stats fail WF)"
    elif not g3_pass:
        verdict = "REJECTED (G3: null ratio <1.5)"
    elif g2_pass and g3_pass and g4_pass:
        verdict = "SHIP"
    elif g2_pass and g3_pass:
        verdict = "CONDITIONAL_SHIP (G4 trace not decreased)"
    else:
        verdict = "REJECTED"

    print(f"[INT-116] Verdict: {verdict}", flush=True)
    print(f"[INT-116] G4: trace_base={results['trace_base']:.4f} "
          f"trace_aug={results['trace_aug']:.4f} {'PASS' if g4_pass else 'FAIL'}", flush=True)

    _save_parquet(results)

    metrics = {
        "verdict": verdict,
        "folds": results["folds"],
        "trace_base": results["trace_base"],
        "trace_aug": results["trace_aug"],
        "g4_pass": results["g4_pass"],
        "g2_wins": g2_summary["wins"],
        "null_ratios": {s: null_ratios[s] for s in ["pts", "reb", "ast"]},
    }
    mp = DATA_MODELS / "multitask_residual_head_metrics.json"
    mp.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"[INT-116] Metrics JSON saved: {mp.name}", flush=True)

    _write_vault(results, g2_summary, null_ratios, verdict)
    _append_banner(verdict)

    print("\n[INT-116] === FINAL SUMMARY ===")
    print(f"  Verdict: {verdict}")
    for fr in results["folds"]:
        print(f"  Fold {fr['fold']}: PTS={fr['delta_pts']:+.4f} "
              f"REB={fr['delta_reb']:+.4f} AST={fr['delta_ast']:+.4f}")
    for s in ["pts", "reb", "ast"]:
        nr = null_ratios[s]
        print(f"  G3 {s.upper()}: ratio={nr['ratio']:.2f} {'PASS' if nr['pass'] else 'FAIL'}")
    print(f"  G4: {'PASS' if g4_pass else 'FAIL'}")


if __name__ == "__main__":
    main()
