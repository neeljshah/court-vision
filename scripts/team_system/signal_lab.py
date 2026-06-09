"""SIGNAL LAB -- the reusable SURGICAL validator + registry that the agentic layer calls.

Every signal this project ships passes the same gates (learned the hard way: kitchen-sink overfits, single-
window peaks lie, accuracy != edge). This encodes those gates as ONE function an agent can call on any
candidate signal, at any grain (possession / player-game / team-game), and a registry so a verdict is
recorded once and never re-litigated.

THE GATES (a signal is VALIDATED only if all hold):
  1. OOS LIFT      adding the signal to the baseline lowers held-out error (group-split by game = leak-free),
                   on the RIGHT metric (rmse for continuous, logloss for binary) -- never in-sample, never MAE-only.
  2. STABILITY     the signal's effect replicates split-half (sign-consistent across game-parity halves).
  3. ORTHOGONAL    not redundant with the baseline (|corr| with baseline features below a cap) -- else it
                   double-counts what the model already has.
  4. MATERIAL      the OOS lift clears a noise floor (so we don't ship a 0.0% mirage).

Usage (importable or CLI):
  from signal_lab import validate_signal
  v = validate_signal(panel_df, name="minutes_competitiveness", baseline=["m_ewma","m_season"],
                      feature=["proj_compet"], target="a_min", group="gid", metric="rmse", asof="2026-04-03")

  python scripts/team_system/signal_lab.py --list          # show the registry
"""
from __future__ import annotations
import json, math, os, sys
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.metrics import log_loss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REG = os.path.join(ROOT, "data", "registry", "signal_lab_registry.parquet")
NOISE_FLOOR = 0.002      # min relative OOS improvement to count as material
ORTHO_CAP = 0.92         # |corr| with any baseline feature above this = redundant


def _oos_error(panel, feats, target, group, metric, seed=0):
    gids = panel[group].unique()
    rng = np.random.default_rng(seed); g = gids.copy(); rng.shuffle(g)
    folds = np.array_split(g, 5)
    errs = []
    for fold in folds:
        te = panel[panel[group].isin(fold)]; tr = panel[~panel[group].isin(fold)]
        if metric == "rmse":
            m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=250,
                                              min_samples_leaf=40, random_state=seed)
            m.fit(tr[feats], tr[target]); p = m.predict(te[feats])
            errs.append(math.sqrt(np.mean((p - te[target].values) ** 2)))
        else:
            m = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=250,
                                               min_samples_leaf=40, random_state=seed)
            m.fit(tr[feats], tr[target]); p = np.clip(m.predict_proba(te[feats])[:, 1], 1e-6, 1 - 1e-6)
            errs.append(log_loss(te[target], p, labels=[0, 1]))
    return float(np.mean(errs))


def validate_signal(panel, name, baseline, feature, target, group="gid", metric="rmse",
                    asof="", note="", grain="", record=True):
    """Run the 4 gates on a candidate signal. panel: DataFrame with baseline+feature+target+group."""
    panel = panel.dropna(subset=baseline + feature + [target, group]).copy()
    n = len(panel)
    base_err = _oos_error(panel, baseline, target, group, metric)
    full_err = _oos_error(panel, baseline + feature, target, group, metric)
    oos_delta = full_err - base_err
    rel = oos_delta / base_err if base_err else 0.0
    # stability: feature's correlation with the residual, split-half by group parity
    gsorted = sorted(panel[group].unique())
    h1 = panel[panel[group].isin(gsorted[::2])]; h2 = panel[panel[group].isin(gsorted[1::2])]
    # univariate proxy: corr(feature, target) in each half (sign-consistent => stable)
    f0 = feature[0]
    c1 = h1[f0].corr(h1[target]) if len(h1) > 20 else np.nan
    c2 = h2[f0].corr(h2[target]) if len(h2) > 20 else np.nan
    stable = bool(np.isfinite(c1) and np.isfinite(c2) and np.sign(c1) == np.sign(c2) and min(abs(c1), abs(c2)) > 0.03)
    # orthogonality: max |corr| of feature with any baseline col
    ortho = max([abs(panel[f0].corr(panel[b])) for b in baseline] + [0.0])
    material = rel < -NOISE_FLOOR
    verdict = "VALIDATED" if (material and stable and ortho < ORTHO_CAP) else "REJECTED"
    reason = []
    if not material: reason.append(f"no OOS lift (rel {rel:+.3%})")
    if not stable: reason.append(f"unstable split-half (corr {c1:+.2f}/{c2:+.2f})")
    if ortho >= ORTHO_CAP: reason.append(f"redundant (ortho {ortho:.2f})")
    row = dict(name=name, grain=grain or group, target=target, metric=metric, n=n,
               base_err=round(base_err, 4), full_err=round(full_err, 4), oos_rel=round(rel, 4),
               split_half=f"{c1:+.2f}/{c2:+.2f}", ortho=round(ortho, 3), verdict=verdict,
               reason="; ".join(reason) or "all gates pass", asof=asof, note=note)
    if record:
        os.makedirs(os.path.dirname(REG), exist_ok=True)
        old = pd.read_parquet(REG) if os.path.exists(REG) else pd.DataFrame()
        old = old[old.name != name] if len(old) else old           # one row per signal (latest)
        pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_parquet(REG, index=False)
    print(f"[{verdict}] {name}: {metric} {base_err:.4f}->{full_err:.4f} (rel {rel:+.3%}), "
          f"split-half {c1:+.2f}/{c2:+.2f}, ortho {ortho:.2f} -- {row['reason']}")
    return row


def show():
    if not os.path.exists(REG):
        print("registry empty"); return
    df = pd.read_parquet(REG)
    print(f"=== SIGNAL LAB REGISTRY ({len(df)} signals, {sum(df.verdict=='VALIDATED')} validated) ===")
    print(df[["name", "grain", "target", "n", "oos_rel", "split_half", "ortho", "verdict", "reason"]].to_string(index=False))


if __name__ == "__main__":
    if "--list" in sys.argv:
        show()
    else:
        print("import validate_signal(panel, name, baseline, feature, target, ...); --list to view registry")
