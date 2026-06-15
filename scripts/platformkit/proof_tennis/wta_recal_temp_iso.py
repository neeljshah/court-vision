"""scripts.platformkit.proof_tennis.wta_recal_temp_iso — WTA temperature + isotonic recal.

W128 REFUTED the thin-prior hypothesis and found WTA Elo is OVERCONFIDENT ON FAVOURITES
(women's-tour upset variance), and that walk-forward PLATT does NOT fix the ECE 0.043/0.073
FAIL — Platt's single logit slope cannot pull the over-confident extremes toward 0.5.

This tries the two recalibrators that CAN target over-confidence, WTA-native + walk-forward:
  * TEMPERATURE scaling: p = sigmoid(logit / T), T fit by min-logloss on strictly-prior
    rows. T>1 shrinks every probability toward 0.5 — the direct over-confidence fix.
  * ISOTONIC regression: a free monotone p_raw->p_cal map fit on strictly-prior rows —
    corrects an arbitrary monotone miscalibration shape (more flexible than Platt's slope).
ECE is reported per eval window (2023-2024 and 2025+) to match the two documented FAIL
numbers directly.

HONEST: calibration metric only, NOT a market edge; markets efficient. A persistent FAIL
is an honest data-limited result (a SUCCESS in the discipline sense — we learn which fix
the structure does/doesn't admit), never a defect to paper over.
INVARIANTS: never edit src/ or kernel/; reuse corpus-agnostic elo_tune; <=300 LOC.

Run:
    python -m scripts.platformkit.proof_tennis.wta_recal_temp_iso
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.tennis import elo_tune as et  # noqa: E402

_WTA_PARQUET = _REPO / "data" / "domains" / "tennis" / "wta" / "matches.parquet"
_ECE_THRESHOLD = 0.025
_EPS = 1e-6
_REFIT_EVERY = 200
_WINDOWS: Tuple[Tuple[str, int, int], ...] = (
    ("2023-2024", 2023, 2024),
    ("2025+", 2025, 9999),
)


# ---------------------------------------------------------------------------
# Walk-forward recalibrators (strictly-prior fit; no future leak)
# ---------------------------------------------------------------------------

def _logits_outcomes(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    p = np.clip(df["win_prob_p1"].to_numpy(dtype=float), _EPS, 1.0 - _EPS)
    return np.log(p / (1.0 - p)), (df["winner"] == 1).to_numpy(dtype=float)


def _fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """T>0 minimising logloss of sigmoid(logit/T).  T>1 == shrink toward 0.5."""
    from scipy.optimize import minimize_scalar

    def nll(t: float) -> float:
        p = 1.0 / (1.0 + np.exp(-logits / t))
        p = np.clip(p, _EPS, 1.0 - _EPS)
        return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))

    res = minimize_scalar(nll, bounds=(0.25, 5.0), method="bounded")
    return float(res.x)


def _walk_forward_recal(wf_df: pd.DataFrame, method: str,
                        train_year_max: int = et.TRAIN_YEAR_MAX,
                        refit_every: int = _REFIT_EVERY) -> pd.DataFrame:
    """Generic walk-forward recalibration. method in {'temperature','isotonic'}.

    For each test row (year > train_year_max) the calibrator is fit ONLY on rows with
    index strictly < the current row (train-era + earlier test rows), refit every
    ``refit_every`` test rows. Returns the test subset with a 'win_prob_recal' column.
    """
    from sklearn.isotonic import IsotonicRegression

    df = wf_df.copy().reset_index(drop=True)
    years = pd.to_datetime(df["date"]).dt.year
    train_max_mask = (years <= train_year_max).to_numpy()
    test_mask = (years > train_year_max).to_numpy()
    logits, outcomes = _logits_outcomes(df)
    probs_raw = np.clip(df["win_prob_p1"].to_numpy(dtype=float), _EPS, 1.0 - _EPS)

    test_indices = np.where(test_mask)[0]
    recal = np.full(len(test_indices), np.nan)
    model = None
    last_refit = -10 ** 9

    for pos, idx in enumerate(test_indices):
        if model is None or (pos - last_refit) >= refit_every:
            prior = np.arange(len(df)) < idx        # strictly-prior rows only
            yf = outcomes[prior]
            if len(yf) >= 50 and 0 < yf.sum() < len(yf):
                if method == "temperature":
                    model = ("T", _fit_temperature(logits[prior], yf))
                else:  # isotonic
                    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
                    iso.fit(probs_raw[prior], yf)
                    model = ("ISO", iso)
                last_refit = pos
        if model is None:
            recal[pos] = probs_raw[idx]
        elif model[0] == "T":
            recal[pos] = 1.0 / (1.0 + np.exp(-logits[idx] / model[1]))
        else:
            recal[pos] = float(model[1].predict([probs_raw[idx]])[0])

    test_df = df[test_mask].copy().reset_index(drop=True)
    test_df["win_prob_recal"] = np.clip(recal, _EPS, 1.0 - _EPS)
    return test_df


# ---------------------------------------------------------------------------
# Per-window metrics
# ---------------------------------------------------------------------------

def _window_metrics(test_df: pd.DataFrame, prob_col: str) -> List[Dict]:
    yrs = pd.to_datetime(test_df["date"]).dt.year.to_numpy()
    y = (test_df["winner"] == 1).to_numpy(dtype=float)
    p = test_df[prob_col].to_numpy(dtype=float)
    out: List[Dict] = []
    for label, lo, hi in _WINDOWS:
        m = (yrs >= lo) & (yrs <= hi)
        if m.sum() < 100:
            continue
        out.append({"window": label, "n": int(m.sum()),
                    "ece": round(et.ece(p[m], y[m]), 5),
                    "brier": round(et.brier(p[m], y[m]), 5)})
    return out


def run(parquet_path: Path = _WTA_PARQUET) -> Dict:
    if not parquet_path.is_file():
        return {"error": f"WTA corpus not found: {parquet_path}"}
    matches = pd.read_parquet(parquet_path)
    best_blend = float(et.blend_sweep(matches).sort_values("brier").iloc[0]["blend"])
    wf = et._sorted(et._walk_forward_blend(matches, best_blend)).reset_index(drop=True)

    # Raw (no recal) baseline on the same test split.
    yrs = pd.to_datetime(wf["date"]).dt.year
    raw_test = wf[yrs > et.TRAIN_YEAR_MAX].copy().reset_index(drop=True)
    raw_test["win_prob_recal"] = raw_test["win_prob_p1"]

    platt = et.platt_recalibrate(wf, refit_every=_REFIT_EVERY)
    temp = _walk_forward_recal(wf, "temperature")
    iso = _walk_forward_recal(wf, "isotonic")

    methods = {
        "raw": _window_metrics(raw_test, "win_prob_recal"),
        "platt": _window_metrics(platt, "win_prob_recal"),
        "temperature": _window_metrics(temp, "win_prob_recal"),
        "isotonic": _window_metrics(iso, "win_prob_recal"),
    }
    # The decisive test: does ANY method get ECE < threshold on BOTH eval windows?
    passed = []
    for name, rows in methods.items():
        if rows and all(r["ece"] < _ECE_THRESHOLD for r in rows):
            passed.append(name)
    # Report the temperature value actually fit (last refit) for transparency.
    final_T = _fit_temperature(*_logits_outcomes(wf[yrs <= et.TRAIN_YEAR_MAX]))
    return {
        "corpus": "WTA", "n_total": len(matches), "best_blend": best_blend,
        "ece_threshold": _ECE_THRESHOLD, "train_year_max": et.TRAIN_YEAR_MAX,
        "methods": methods, "passed_both_windows": passed,
        "train_era_temperature": round(final_T, 3),
        "verdict": (f"CALIBRATED via {passed}" if passed else
                    "HONEST FAIL — no recalibrator brings WTA ECE<thr on both windows; "
                    "structural over-confidence is data-limited (NOT an edge)"),
        "note": "Calibration metric only; not a market edge. Markets efficient.",
    }


def _main() -> int:
    rep = run()
    if "error" in rep:
        print(rep["error"]); return 1
    print(f"=== WTA Temperature/Isotonic Recal (blend={rep['best_blend']}, "
          f"train<={rep['train_year_max']}, ECE thr<{rep['ece_threshold']}) ===")
    print(f"corpus n={rep['n_total']}  train-era fitted T={rep['train_era_temperature']} "
          f"(T>1 => over-confident Elo)")
    print(f"{'method':>12} {'window':>10} {'n':>6} {'ece':>9} {'brier':>9}")
    for name, rows in rep["methods"].items():
        for r in rows:
            flag = "  <-- PASS" if r["ece"] < rep["ece_threshold"] else ""
            print(f"{name:>12} {r['window']:>10} {r['n']:>6} {r['ece']:>9} {r['brier']:>9}{flag}")
    print(f"\npassed both windows: {rep['passed_both_windows'] or 'NONE'}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
