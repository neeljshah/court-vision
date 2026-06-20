"""domains.tennis.pregame_feature_gate -- gate deeper pregame features vs plain Elo.

QUESTION: does adding a candidate pregame feature (recent-form / H2H / rest /
fatigue) to the Elo win-prob beat the Elo-only prediction on held-out OOS Brier,
REPLICATED across BOTH corpora (ATP and WTA)?

DESIGN (leak-free, walk-forward, honest):
  BASE     = walk-forward logistic on [elo_logit] only (Platt recal of plain Elo).
  +FEATURE = walk-forward logistic on [elo_logit, feature].
  Both calibrators are refit on STRICTLY-PRIOR rows only (index < current), so no
  test row ever informs its own prediction -> leak-free by construction.

GATING:
  * Test split = year > TRAIN_YEAR_MAX, scored per corpus.
  * DM clustered by match event_id (1 state per match here, so clustering is a
    no-op vs iid, but we keep the SAME clustered DM the in-game gate uses).
  * SHIP a feature iff it LOWERS Brier in BOTH corpora AND DM p < eps in BOTH.
  * DEGENERATE-BASE GUARD: the BASE Elo must itself beat a constant-0.5 predictor
    by a real margin (BSS > MIN_BSS); else there is no real base to improve and the
    verdict is INVALID_BASE.
  * Honest REJECT otherwise -- a feature that helps one corpus only is PARTIAL.

PRIVATE: F5-clean -- stdlib + numpy/pandas/sklearn + domains.tennis.* + the shared
eval_gate DM. No edge claim; calibration (Brier) only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from domains.tennis.elo_tune import brier
from domains.tennis.pregame_features import build_features, elo_logit, FEATURE_COLS

TRAIN_YEAR_MAX: int = 2022
REFIT_EVERY: int = 1000
MIN_BSS: float = 0.02      # BASE must beat const-0.5 by >=2% BSS (degenerate guard)
_EPS: float = 1e-9

ATP_PARQUET = "data/domains/tennis/matches.parquet"
WTA_PARQUET = "data/domains/tennis/wta_matches.parquet"


def _walkforward_logistic(X: np.ndarray, y: np.ndarray, test_mask: np.ndarray,
                          train_mask: np.ndarray, refit_every: int = REFIT_EVERY) -> np.ndarray:
    """Walk-forward logistic predictions for test rows, fit on strictly-prior rows.

    X is (N, k). For each test row i, the calibrator is fit on ALL rows with
    index < i (refit every ``refit_every`` test rows for speed). Returns an array
    aligned to test_mask positions.
    """
    n = len(y)
    test_idx = np.where(test_mask)[0]
    preds = np.full(len(test_idx), np.nan)
    clf: Optional[LogisticRegression] = None
    last_refit = -10 ** 9
    for pos, idx in enumerate(test_idx):
        if clf is None or (pos - last_refit) >= refit_every:
            prior = np.arange(n) < idx
            Xf, yf = X[prior], y[prior]
            if len(yf) >= 50 and 0 < yf.sum() < len(yf):
                clf = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500)
                clf.fit(Xf, yf)
                last_refit = pos
        if clf is not None:
            preds[pos] = clf.predict_proba(X[idx:idx + 1])[0, 1]
        else:
            # fall back to raw elo prob (first column is elo_logit -> sigmoid)
            preds[pos] = 1.0 / (1.0 + np.exp(-X[idx, 0]))
    return preds


def _bss(p: np.ndarray, y: np.ndarray) -> float:
    """Brier skill score vs a constant 0.5 predictor."""
    b = brier(p, y)
    b0 = brier(np.full_like(p, 0.5), y)
    return 1.0 - b / b0 if b0 > 0 else 0.0


def gate_feature_on_corpus(df_feat: pd.DataFrame, feature: str,
                           train_year_max: int = TRAIN_YEAR_MAX) -> dict:
    """Gate one feature on one corpus. Returns Brier(base/feat), DM, guard flags."""
    years = pd.to_datetime(df_feat["date"]).dt.year.to_numpy()
    test_mask = years > train_year_max
    train_mask = years <= train_year_max
    y = (df_feat["winner"] == 1).to_numpy(dtype=float)
    lg = elo_logit(df_feat)

    X_base = lg.reshape(-1, 1)
    fcol = df_feat[feature].to_numpy(dtype=float)
    fcol = np.nan_to_num(fcol, nan=0.0)
    X_feat = np.column_stack([lg, fcol])

    p_base = _walkforward_logistic(X_base, y, test_mask, train_mask)
    p_feat = _walkforward_logistic(X_feat, y, test_mask, train_mask)
    y_test = y[test_mask]
    gids = df_feat.loc[test_mask, "event_id"].astype(str).to_numpy()

    b_base = float(brier(p_base, y_test))
    b_feat = float(brier(p_feat, y_test))
    d = (p_base - y_test) ** 2 - (p_feat - y_test) ** 2   # +ve => feature better
    dm = diebold_mariano(d, gids)
    bss_base = _bss(p_base, y_test)
    return {
        "n_test": int(test_mask.sum()),
        "brier_base": round(b_base, 5),
        "brier_feat": round(b_feat, 5),
        "brier_delta": round(b_base - b_feat, 5),
        "dm_stat": round(dm.dm_stat, 4),
        "dm_p": round(dm.p_value, 6),
        "feat_better": bool(b_feat < b_base),
        "base_bss_vs_half": round(bss_base, 5),
        "base_degenerate": bool(bss_base < MIN_BSS),
    }


def gate_feature(atp_feat: pd.DataFrame, wta_feat: pd.DataFrame, feature: str,
                 eps: float = 0.05) -> dict:
    """Cross-corpus verdict for one feature over ATP + WTA."""
    a = gate_feature_on_corpus(atp_feat, feature)
    w = gate_feature_on_corpus(wta_feat, feature)
    degen = a["base_degenerate"] or w["base_degenerate"]
    both_better = a["feat_better"] and w["feat_better"]
    both_sig = a["dm_p"] < eps and w["dm_p"] < eps
    if degen:
        verdict = "INVALID_BASE"
    elif both_better and both_sig:
        verdict = "SHIP"
    elif (a["feat_better"] and a["dm_p"] < eps) or (w["feat_better"] and w["dm_p"] < eps):
        verdict = "PARTIAL"
    else:
        verdict = "REJECT"
    return {"feature": feature, "verdict": verdict, "atp": a, "wta": w}


def run_all(train_year_max: int = TRAIN_YEAR_MAX) -> list[dict]:
    """Build features for both corpora once and gate every candidate feature."""
    root = Path(__file__).resolve().parents[2]
    atp = pd.read_parquet(root / ATP_PARQUET)
    wta = pd.read_parquet(root / WTA_PARQUET)
    atp_feat = build_features(atp)
    wta_feat = build_features(wta)
    return [gate_feature(atp_feat, wta_feat, f) for f in FEATURE_COLS]


def _report(results: list[dict]) -> str:
    lines = ["=" * 74, "TENNIS PREGAME FEATURE GATE: Elo+feature vs Elo-only (ATP & WTA)",
             "=" * 74]
    for r in results:
        a, w = r["atp"], r["wta"]
        lines.append(f"\nFEATURE {r['feature']:<18} VERDICT: {r['verdict']}")
        lines.append(f"  ATP  Brier base {a['brier_base']:.5f} -> feat {a['brier_feat']:.5f}"
                     f"  (delta {a['brier_delta']:+.5f})  DM p={a['dm_p']:.4f}"
                     f"  base_BSS={a['base_bss_vs_half']:.4f}")
        lines.append(f"  WTA  Brier base {w['brier_base']:.5f} -> feat {w['brier_feat']:.5f}"
                     f"  (delta {w['brier_delta']:+.5f})  DM p={w['dm_p']:.4f}"
                     f"  base_BSS={w['base_bss_vs_half']:.4f}")
    lines.append("\n" + "=" * 74)
    lines.append("Calibration (Brier) only; no market-edge claim. DM clustered by event_id.")
    return "\n".join(lines)


def main() -> None:
    results = run_all()
    print(_report(results))


if __name__ == "__main__":
    main()
