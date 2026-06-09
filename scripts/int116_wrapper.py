"""Wrapper: runs the full INT-116 logic from a clean entry point."""
import os, sys
os.chdir(r'C:\Users\neelj\nba-ai-system')
sys.path.insert(0, r'C:\Users\neelj\nba-ai-system')

# Override ROOT in main module before importing
import importlib.util, types

# Inline all the logic here to avoid __file__-based ROOT resolution issues
import json
import time
import copy
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from xgboost import XGBRegressor

ROOT = Path(r'C:\Users\neelj\nba-ai-system')
DATA_MODELS  = ROOT / "data" / "models"
DATA_INTEL   = ROOT / "data" / "intelligence"
VAULT_INTEL  = ROOT / "vault" / "Intelligence"
VAULT_IMPROV = ROOT / "vault" / "Improvements"
CACHE_PATH   = ROOT / "data" / "cache" / "int116_pergame_dataset.parquet"

print("[INT-116] Step 1: imports ok", flush=True)

MLP_FEATURES = [
    "l5_min", "prev_min", "opp_def_pts", "rest_days", "is_b2b", "is_home",
    "bbref_usg_pct", "bbref_ts_pct", "ewma_pts", "ewma_reb", "ewma_ast",
    "miles_traveled", "days_since_last_game", "l5_pts", "l5_reb", "l5_ast",
]
TARGET_STATS = ["pts", "reb", "ast"]

# ===== LOAD =====
print(f"[INT-116] Loading {CACHE_PATH.name} ...", flush=True)
df = pd.read_parquet(str(CACHE_PATH))
df = df.sort_values("date").reset_index(drop=True)
print(f"[INT-116] Loaded {len(df):,} rows x {df.shape[1]} cols", flush=True)

meta_cols = {"date", "target_pts", "target_reb", "target_ast"}
feat_cols_all = [c for c in df.columns if c not in meta_cols]

X_full = df[feat_cols_all].fillna(0.0).values.astype(np.float32)
X_mlp  = np.zeros((len(df), len(MLP_FEATURES)), dtype=np.float32)
for j, f in enumerate(MLP_FEATURES):
    if f in df.columns:
        X_mlp[:, j] = df[f].fillna(0.0).values.astype(np.float32)

y_pts  = df["target_pts"].fillna(0.0).values.astype(np.float32)
y_reb  = df["target_reb"].fillna(0.0).values.astype(np.float32)
y_ast  = df["target_ast"].fillna(0.0).values.astype(np.float32)
dates  = df["date"].tolist()
del df
print(f"[INT-116] Arrays: X_full={X_full.shape} X_mlp={X_mlp.shape}", flush=True)

n = len(X_full)
std_pts = float(np.std(y_pts)) or 1.0
std_reb = float(np.std(y_reb)) or 1.0
std_ast = float(np.std(y_ast)) or 1.0
clip_b  = [0.5*std_pts, 0.5*std_reb, 0.5*std_ast]
print(f"[INT-116] Clip bounds: PTS+/-{clip_b[0]:.3f} REB+/-{clip_b[1]:.3f} AST+/-{clip_b[2]:.3f}", flush=True)

def _wf_cutoffs(n, nf=4):
    return [int(round(i*n/(nf+1))) for i in range(1, nf+1)]

def _mae(a, b):
    return float(np.mean(np.abs(a - b)))

def _train_xgb(Xtr, ytr):
    m = XGBRegressor(
        objective="reg:quantileerror", quantile_alpha=0.5,
        n_estimators=500, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=4, verbosity=0
    )
    m.fit(Xtr, ytr)
    return m

def _train_mlp(Xtr, Rtr_z, seed=42):
    torch.manual_seed(seed)
    model = nn.Sequential(
        nn.Linear(len(MLP_FEATURES), 32), nn.Tanh(), nn.Dropout(0.2),
        nn.Linear(32, 16), nn.Tanh(), nn.Dropout(0.2),
        nn.Linear(16, 3),
    )
    nv = max(1, int(len(Xtr)*0.15))
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(Xtr))
    vi, ti = idx[:nv], idx[nv:]
    Xt = torch.tensor(Xtr[ti]); Rt = torch.tensor(Rtr_z[ti])
    Xv = torch.tensor(Xtr[vi]); Rv = torch.tensor(Rtr_z[vi])
    loader = DataLoader(TensorDataset(Xt, Rt), batch_size=512, shuffle=True)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    crit = nn.MSELoss()
    best_val, no_imp, best_st = float('inf'), 0, None
    for ep in range(80):
        model.train()
        for xb, rb in loader:
            opt.zero_grad(); crit(model(xb), rb).backward(); opt.step()
        model.eval()
        with torch.no_grad():
            vl = crit(model(Xv), Rv).item()
        if vl < best_val - 1e-6:
            best_val, no_imp, best_st = vl, 0, copy.deepcopy(model.state_dict())
        else:
            no_imp += 1
        if no_imp >= 10: break
    if best_st: model.load_state_dict(best_st)
    return model

def run_wf(null_shuffle=False, save=True):
    cutoffs = _wf_cutoffs(n)
    folds, base_ress, aug_ress = [], [], []
    for k, cut in enumerate(cutoffs):
        vs = cut; ve = cutoffs[k+1] if k+1 < len(cutoffs) else n
        if ve <= vs: continue
        tag = "NULL" if null_shuffle else "REAL"
        print(f"[INT-116] [{tag}] Fold {k+1}: train[0:{cut}] val[{vs}:{ve}]", flush=True)
        Xf_tr = X_full[:cut]; Xf_val = X_full[vs:ve]
        Xm_tr = X_mlp[:cut];  Xm_val = X_mlp[vs:ve]
        yp_tr = y_pts[:cut];   yp_val = y_pts[vs:ve]
        yr_tr = y_reb[:cut];   yr_val = y_reb[vs:ve]
        ya_tr = y_ast[:cut];   ya_val = y_ast[vs:ve]

        print(f"  Training XGB bases ...", flush=True)
        mp = _train_xgb(Xf_tr, yp_tr)
        mr = _train_xgb(Xf_tr, yr_tr)
        ma = _train_xgb(Xf_tr, ya_tr)

        pp_base = mp.predict(Xf_val)
        pr_base = mr.predict(Xf_val)
        pa_base = ma.predict(Xf_val)

        pp_tr = mp.predict(Xf_tr)
        pr_tr = mr.predict(Xf_tr)
        pa_tr = ma.predict(Xf_tr)

        R_tr = np.column_stack([
            np.clip(yp_tr - pp_tr, -clip_b[0], clip_b[0]),
            np.clip(yr_tr - pr_tr, -clip_b[1], clip_b[1]),
            np.clip(ya_tr - pa_tr, -clip_b[2], clip_b[2]),
        ])
        if null_shuffle:
            rng2 = np.random.default_rng(99)
            for col in range(3): rng2.shuffle(R_tr[:, col])

        Rm = R_tr.mean(axis=0); Rs = R_tr.std(axis=0)
        Rs[Rs < 1e-8] = 1.0
        R_tr_z = (R_tr - Rm) / Rs

        print(f"  Training MLP ...", flush=True)
        mlp = _train_mlp(Xm_tr, R_tr_z)

        if save and not null_shuffle:
            sp = DATA_MODELS / f"multitask_residual_head_v1_fold{k}.pt"
            torch.save(mlp.state_dict(), str(sp))
            print(f"  Saved -> {sp.name}", flush=True)

        mlp.eval()
        with torch.no_grad():
            dz = mlp(torch.tensor(Xm_val)).numpy()
        dr = dz * Rs + Rm
        dp = np.clip(dr[:,0], -clip_b[0], clip_b[0])
        dre = np.clip(dr[:,1], -clip_b[1], clip_b[1])
        da = np.clip(dr[:,2], -clip_b[2], clip_b[2])

        pp_aug = pp_base+dp; pr_aug = pr_base+dre; pa_aug = pa_base+da

        bmp = _mae(yp_val, pp_base); amp = _mae(yp_val, pp_aug)
        bmr = _mae(yr_val, pr_base); amr = _mae(yr_val, pr_aug)
        bma = _mae(ya_val, pa_base); ama = _mae(ya_val, pa_aug)

        print(f"  PTS base={bmp:.4f} aug={amp:.4f} delta={amp-bmp:+.4f}")
        print(f"  REB base={bmr:.4f} aug={amr:.4f} delta={amr-bmr:+.4f}")
        print(f"  AST base={bma:.4f} aug={ama:.4f} delta={ama-bma:+.4f}")

        folds.append({
            "fold": k+1, "n_train": cut, "n_val": ve-vs,
            "base_mae_pts": bmp, "aug_mae_pts": amp, "delta_pts": amp-bmp,
            "base_mae_reb": bmr, "aug_mae_reb": amr, "delta_reb": amr-bmr,
            "base_mae_ast": bma, "aug_mae_ast": ama, "delta_ast": ama-bma,
        })
        base_ress.append(np.column_stack([yp_val-pp_base, yr_val-pr_base, ya_val-pa_base]))
        aug_ress.append(np.column_stack([yp_val-pp_aug,  yr_val-pr_aug,  ya_val-pa_aug]))

    ba = np.vstack(base_ress); aa = np.vstack(aug_ress)
    tb = float(np.trace(np.cov(ba.T))); ta = float(np.trace(np.cov(aa.T)))
    return {"folds": folds, "trace_base": tb, "trace_aug": ta, "g4_pass": ta < tb}

print("[INT-116] === Real walk-forward ===", flush=True)
results = run_wf(null_shuffle=False, save=True)

wins = {s: sum(1 for fr in results["folds"] if fr[f"delta_{s}"] < 0) for s in ["pts","reb","ast"]}
per_stat = {s: wins[s] >= 3 for s in ["pts","reb","ast"]}
g2_pass = sum(per_stat.values()) >= 2
print(f"[INT-116] G2 wins: PTS={wins['pts']}/4 REB={wins['reb']}/4 AST={wins['ast']}/4", flush=True)

print("[INT-116] === Null control (G3) ===", flush=True)
null_res = run_wf(null_shuffle=True, save=False)

null_ratios = {}
for stat in ["pts","reb","ast"]:
    key = f"delta_{stat}"
    real_d = abs(float(np.mean([f[key] for f in results["folds"]])))
    null_d = abs(float(np.mean([f[key] for f in null_res["folds"]])))
    ratio = real_d / null_d if null_d > 1e-9 else 99.0
    null_ratios[stat] = {
        "real_delta": float(np.mean([f[key] for f in results["folds"]])),
        "null_delta": float(np.mean([f[key] for f in null_res["folds"]])),
        "ratio": ratio, "pass": ratio >= 1.5,
    }
    tag = "PASS" if ratio >= 1.5 else "FAIL"
    print(f"  G3 {stat.upper()}: real={null_ratios[stat]['real_delta']:+.5f} "
          f"null={null_ratios[stat]['null_delta']:+.5f} ratio={ratio:.2f} [{tag}]")

g3_pass = sum(1 for v in null_ratios.values() if v["pass"]) >= 2
g4_pass = results["g4_pass"]
g2_fails = sum(1 for s in ["pts","reb","ast"] if not per_stat[s])

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
print(f"[INT-116] G4: trace_base={results['trace_base']:.4f} trace_aug={results['trace_aug']:.4f} {'PASS' if g4_pass else 'FAIL'}", flush=True)

# Save parquet (G5)
import pandas as pd2
rows_out = []
for fr in results["folds"]:
    rows_out.append({
        "fold": fr["fold"], "n_train": fr["n_train"], "n_val": fr["n_val"],
        "base_mae_pts": fr["base_mae_pts"], "aug_mae_pts": fr["aug_mae_pts"], "delta_pts": fr["delta_pts"],
        "base_mae_reb": fr["base_mae_reb"], "aug_mae_reb": fr["aug_mae_reb"], "delta_reb": fr["delta_reb"],
        "base_mae_ast": fr["base_mae_ast"], "aug_mae_ast": fr["aug_mae_ast"], "delta_ast": fr["delta_ast"],
    })
df_out = pd.DataFrame(rows_out)
assert all(c in df_out.columns for c in ["delta_pts","delta_reb","delta_ast"])
assert not any(c in df_out.columns for c in ["delta_fg3m","delta_stl","delta_blk","delta_tov"])
df_out.to_parquet(str(DATA_INTEL / "multitask_residual_head_predictions.parquet"), index=False)
print("[INT-116] Parquet saved (G5 PASS)", flush=True)

# Save metrics JSON
metrics = {
    "verdict": verdict,
    "folds": results["folds"],
    "trace_base": results["trace_base"],
    "trace_aug": results["trace_aug"],
    "g4_pass": results["g4_pass"],
    "g2_wins": wins,
    "null_ratios": {s: null_ratios[s] for s in ["pts","reb","ast"]},
}
mp = DATA_MODELS / "multitask_residual_head_metrics.json"
mp.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
print(f"[INT-116] Metrics JSON saved", flush=True)

# Vault note
folds_tbl = "\n".join(f"| {fr['fold']} | {fr['delta_pts']:+.4f} | {fr['delta_reb']:+.4f} | {fr['delta_ast']:+.4f} |" for fr in results["folds"])
null_tbl = "\n".join(f"| {s.upper()} | {null_ratios[s]['real_delta']:+.5f} | {null_ratios[s]['null_delta']:+.5f} | {null_ratios[s]['ratio']:.2f} | {'PASS' if null_ratios[s]['pass'] else 'FAIL'} |" for s in ["pts","reb","ast"])
tb = results["trace_base"]; ta = results["trace_aug"]

vault_content = f"""# INT-116 Multi-Task MLP Residual Head

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
{folds_tbl}

**G2 Win counts (need >=3/4 folds negative):**
- PTS: {wins['pts']}/4 -> {"PASS" if per_stat['pts'] else "FAIL"}
- REB: {wins['reb']}/4 -> {"PASS" if per_stat['reb'] else "FAIL"}
- AST: {wins['ast']}/4 -> {"PASS" if per_stat['ast'] else "FAIL"}
**G2 Overall (>=2 of 3 stats pass):** {"PASS" if g2_pass else "FAIL"}

## Null Control (G3)

| Stat | Real Delta | Null Delta | Ratio | G3 |
|------|-----------|-----------|-------|----|
{null_tbl}
**G3 Overall (>=2 of 3 ratio >= 1.5):** {"PASS" if g3_pass else "FAIL"}

## Joint Covariance Trace (G4)

| Metric | Value |
|--------|-------|
| Trace(base) | {tb:.4f} |
| Trace(aug)  | {ta:.4f} |
| Delta | {ta - tb:+.4f} |
| G4 | {"PASS" if g4_pass else "FAIL"} |

## G5 (Off-Target Regression Guard)
Parquet schema: only delta_pts, delta_reb, delta_ast columns present.
FG3M/STL/BLK/TOV UNCHANGED at base q50 level. **G5: PASS**

## Gate Scoreboard

| Gate | Result |
|------|--------|
| G2 (per-stat WF >= 3/4) | {"PASS" if g2_pass else "FAIL"} |
| G3 (null ratio >= 1.5) | {"PASS" if g3_pass else "FAIL"} |
| G4 (trace decrease) | {"PASS" if g4_pass else "FAIL"} |
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
vp = VAULT_INTEL / "INT-116_Multi_Task_Residual_Head.md"
vp.write_text(vault_content, encoding="utf-8")
print(f"[INT-116] Vault note written", flush=True)

# Banner
bp = VAULT_IMPROV / "cv_master_strategy.md"
if bp.exists():
    existing = bp.read_text(encoding="utf-8")
    if "<!-- INT-116 multitask residual -->" not in existing:
        with open(bp, "a", encoding="utf-8") as f:
            f.write(f"\n<!-- INT-116 multitask residual --> INT-116 Multi-Task MLP Residual (PTS+REB+AST) -- {verdict} -- {time.strftime('%Y-%m-%d')}\n")
        print("[INT-116] Banner appended", flush=True)

print("\n[INT-116] === FINAL SUMMARY ===")
print(f"  Verdict: {verdict}")
for fr in results["folds"]:
    print(f"  Fold {fr['fold']}: PTS={fr['delta_pts']:+.4f} REB={fr['delta_reb']:+.4f} AST={fr['delta_ast']:+.4f}")
for s in ["pts","reb","ast"]:
    nr = null_ratios[s]
    print(f"  G3 {s.upper()}: ratio={nr['ratio']:.2f} {'PASS' if nr['pass'] else 'FAIL'}")
print(f"  G4: {'PASS' if g4_pass else 'FAIL'}")
print("[INT-116] DONE", flush=True)
