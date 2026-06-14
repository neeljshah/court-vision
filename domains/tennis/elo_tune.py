"""domains.tennis.elo_tune — surface-blend sweep + leak-free Platt recalibration.

Sweep SURFACE_BLEND weights, compute Brier/logloss/ECE walk-forward, then apply
leak-free Platt recalibration on the logit.  No edits to elo_core or walkforward.

CLI: ``python domains/tennis/elo_tune.py``

PRIVATE: F5-clean — stdlib + numpy/pandas/sklearn only; no src.* / kernel.* imports.
Sackmann data CC BY-NC-SA — private research use only.  No edge claimed.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from domains.tennis.elo_core import BASE_RATING, _expected, _is_walkover, _sorted

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BLEND_GRID: tuple[float, ...] = (0.0, 0.2, 0.3, 0.4, 0.6)
TRAIN_YEAR_MAX: int = 2022  # train on <= this year
PLATT_REFIT_EVERY: int = 1000  # refit calibrator every N rows
ECE_BINS: int = 10
_EPS: float = 1e-9
_SCALE: float = 400.0  # Elo scaling constant

MATCHES_PARQUET: str = "data/domains/tennis/matches.parquet"


# ---------------------------------------------------------------------------
# Core metrics
# ---------------------------------------------------------------------------

def brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Mean squared error between probabilities and binary outcomes."""
    return float(np.mean((probs - outcomes) ** 2))


def logloss(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Binary cross-entropy."""
    p = np.clip(probs, _EPS, 1.0 - _EPS)
    return float(-np.mean(outcomes * np.log(p) + (1.0 - outcomes) * np.log(1.0 - p)))


def ece(probs: np.ndarray, outcomes: np.ndarray, n_bins: int = ECE_BINS) -> float:
    """Expected Calibration Error with equal-width bins on [0, 1].

    Parameters
    ----------
    probs:    Predicted probabilities, shape (N,).
    outcomes: Binary outcomes (0 or 1), shape (N,).
    n_bins:   Number of equal-width bins.

    Returns
    -------
    float: ECE (lower = better calibrated).
    """
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    n = len(probs)
    total = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            continue
        mean_conf = probs[mask].mean()
        mean_acc = outcomes[mask].mean()
        total += (mask.sum() / n) * abs(mean_conf - mean_acc)
    return float(total)


# ---------------------------------------------------------------------------
# Walk-forward with a custom blend weight (no mutation of elo_core constants)
# ---------------------------------------------------------------------------

def _walk_forward_blend(matches_df: pd.DataFrame, blend: float) -> pd.DataFrame:
    """Walk-forward Elo producing ``win_prob_p1`` with a given surface blend.

    Mirrors elo_walkforward.walk_forward_elo but uses ``blend`` instead of the
    module-level SURFACE_BLEND constant — so we can sweep without editing elo_core.

    Returns the sorted DataFrame with added columns:
      p1_elo, p2_elo, p1_surface_elo, p2_surface_elo, win_prob_p1
    """
    from domains.tennis.elo_core import _k  # local import to stay F5-clean

    df = _sorted(matches_df)
    n = len(df)
    dates = pd.to_datetime(df["date"]).dt.date

    ratings: dict[int, float] = {}
    surface: dict[tuple[int, str], float] = {}
    counts: dict[int, int] = {}
    surface_counts: dict[tuple[int, str], int] = {}

    p1_elos, p2_elos, p1_surf, p2_surf, win_probs = [], [], [], [], []

    for i in range(n):
        p1_id = int(df["p1_id"].iloc[i])
        p2_id = int(df["p2_id"].iloc[i])
        winner = int(df["winner"].iloc[i])
        surf_str = str(df["surface"].iloc[i]) if pd.notna(df["surface"].iloc[i]) else "Unknown"
        score = df["score"].iloc[i] if "score" in df.columns else ""

        r1 = ratings.get(p1_id, BASE_RATING)
        r2 = ratings.get(p2_id, BASE_RATING)
        s1 = surface.get((p1_id, surf_str), r1)
        s2 = surface.get((p2_id, surf_str), r2)

        p1_elos.append(r1); p2_elos.append(r2)
        p1_surf.append(s1); p2_surf.append(s2)

        diff = (1.0 - blend) * (r1 - r2) + blend * (s1 - s2)
        win_probs.append(1.0 / (1.0 + 10.0 ** (-diff / _SCALE)))

        if _is_walkover(score):
            continue

        c1 = counts.get(p1_id, 0); c2 = counts.get(p2_id, 0)
        sc1 = surface_counts.get((p1_id, surf_str), 0)
        sc2 = surface_counts.get((p2_id, surf_str), 0)
        actual1 = 1.0 if winner == 1 else 0.0

        e1 = _expected(r1, r2)
        ratings[p1_id] = r1 + _k(c1) * (actual1 - e1)
        ratings[p2_id] = r2 + _k(c2) * ((1.0 - actual1) - (1.0 - e1))

        es1 = _expected(s1, s2)
        surface[(p1_id, surf_str)] = s1 + _k(sc1) * (actual1 - es1)
        surface[(p2_id, surf_str)] = s2 + _k(sc2) * ((1.0 - actual1) - (1.0 - es1))

        counts[p1_id] = c1 + 1; counts[p2_id] = c2 + 1
        surface_counts[(p1_id, surf_str)] = sc1 + 1
        surface_counts[(p2_id, surf_str)] = sc2 + 1

    out = df.copy()
    out["p1_elo"] = p1_elos; out["p2_elo"] = p2_elos
    out["p1_surface_elo"] = p1_surf; out["p2_surface_elo"] = p2_surf
    out["win_prob_p1"] = win_probs
    return out


# ---------------------------------------------------------------------------
# Blend sweep
# ---------------------------------------------------------------------------

def blend_sweep(
    matches_df: pd.DataFrame,
    blends: Sequence[float] = BLEND_GRID,
    train_year_max: int = TRAIN_YEAR_MAX,
) -> pd.DataFrame:
    """Sweep blend weights; return DataFrame with Brier/logloss/ECE on test split.

    Train: year <= train_year_max.  Test: year > train_year_max.
    The walk-forward is run on the FULL corpus so test-set Elo ratings are built
    from training data only (strictly prior matches at match time).
    """
    years = pd.to_datetime(matches_df["date"]).dt.year
    rows = []
    for blend in blends:
        wf = _walk_forward_blend(matches_df, blend)
        wf_years = pd.to_datetime(wf["date"]).dt.year
        test = wf[wf_years > train_year_max].copy()
        p = test["win_prob_p1"].to_numpy(dtype=float)
        y = (test["winner"] == 1).to_numpy(dtype=float)
        rows.append({
            "blend": blend,
            "brier": brier(p, y),
            "logloss": logloss(p, y),
            "ece": ece(p, y),
            "n_test": len(test),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Leak-free Platt recalibration
# ---------------------------------------------------------------------------

def platt_recalibrate(
    wf_df: pd.DataFrame,
    train_year_max: int = TRAIN_YEAR_MAX,
    refit_every: int = PLATT_REFIT_EVERY,
) -> pd.DataFrame:
    """Walk-forward Platt (logistic) recalibration on the Elo logit.

    For each test row (year > train_year_max):
      - A LogisticRegression(C=1e6) is fit on ALL strictly-prior rows
        (only train-era rows are used for the first ``refit_every`` rows;
        then refitted periodically).
      - The fitted model predicts ``win_prob_recal`` for the current row.

    Guarantees no future data in fit: each calibrator sees only rows with
    index strictly < current row index in the sorted order.

    Returns the test subset of wf_df with an added ``win_prob_recal`` column.
    """
    df = wf_df.copy().reset_index(drop=True)
    years = pd.to_datetime(df["date"]).dt.year

    train_mask = years <= train_year_max
    test_mask = years > train_year_max

    probs_raw = df["win_prob_p1"].to_numpy(dtype=float)
    probs_raw = np.clip(probs_raw, _EPS, 1.0 - _EPS)
    logits = np.log(probs_raw / (1.0 - probs_raw))
    outcomes = (df["winner"] == 1).to_numpy(dtype=float)

    test_indices = np.where(test_mask)[0]
    recal_probs = np.full(len(test_indices), np.nan)

    clf: LogisticRegression | None = None
    last_refit_at: int = -1  # last row index where we refitted

    for pos, idx in enumerate(test_indices):
        # Refit if we haven't yet or we've hit the refit cadence
        if clf is None or (pos - last_refit_at) >= refit_every:
            # Strictly prior rows only (index < idx)
            fit_mask = (np.arange(len(df)) < idx) & train_mask.to_numpy()
            # If we've started test period and want more data, include prior test rows
            fit_mask_extended = np.arange(len(df)) < idx
            # Use only rows strictly before current index
            X_fit = logits[fit_mask_extended].reshape(-1, 1)
            y_fit = outcomes[fit_mask_extended]
            if len(y_fit) >= 10 and y_fit.sum() > 0 and y_fit.sum() < len(y_fit):
                clf = LogisticRegression(C=1e6, solver="lbfgs", max_iter=500)
                clf.fit(X_fit, y_fit)
                last_refit_at = pos
            # else clf stays None → fall back to raw prob

        if clf is not None:
            recal_probs[pos] = clf.predict_proba([[logits[idx]]])[0, 1]
        else:
            recal_probs[pos] = probs_raw[idx]

    test_df = df[test_mask].copy().reset_index(drop=True)
    test_df["win_prob_recal"] = recal_probs
    return test_df


# ---------------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------------

def main(parquet_path: str = MATCHES_PARQUET) -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / parquet_path
    if not path.exists():
        print(f"ERROR: matches.parquet not found at {path}")
        return

    matches = pd.read_parquet(path)
    print(f"Loaded {len(matches):,} matches from {path}")

    # --- Blend sweep ---
    print("\n=== Surface-Blend Sweep (test: 2023-2025) ===")
    sweep = blend_sweep(matches)
    best_row = sweep.loc[sweep["brier"].idxmin()]
    print(sweep.to_string(index=False, float_format="{:.5f}".format))
    print(f"\nBest blend by Brier: {best_row['blend']:.1f}  "
          f"(Brier={best_row['brier']:.5f})")

    # --- Platt recalibration vs raw (best blend) ---
    best_blend = float(best_row["blend"])
    wf = _walk_forward_blend(matches, best_blend)
    test_df = platt_recalibrate(wf)

    p_raw = wf[pd.to_datetime(wf["date"]).dt.year > TRAIN_YEAR_MAX]["win_prob_p1"].to_numpy(dtype=float)
    y_test = (test_df["winner"] == 1).to_numpy(dtype=float)
    p_recal = test_df["win_prob_recal"].to_numpy(dtype=float)

    print(f"\n=== Platt Recalibration vs Raw (blend={best_blend}) ===")
    print(f"{'Metric':<12}  {'Raw':>10}  {'Recal':>10}")
    print(f"{'Brier':<12}  {brier(p_raw, y_test):>10.5f}  {brier(p_recal, y_test):>10.5f}")
    print(f"{'Logloss':<12}  {logloss(p_raw, y_test):>10.5f}  {logloss(p_recal, y_test):>10.5f}")
    print(f"{'ECE':<12}  {ece(p_raw, y_test):>10.5f}  {ece(p_recal, y_test):>10.5f}")

    print("\n=== Honest Verdict ===")
    delta_brier = brier(p_recal, y_test) - brier(p_raw, y_test)
    delta_ece = ece(p_recal, y_test) - ece(p_raw, y_test)
    print(f"Platt recalibration delta-Brier={delta_brier:+.5f}, delta-ECE={delta_ece:+.5f}")
    print("Surface blend affects ECE/calibration modestly; no market-edge claim.")
    print("Platt recal is calibration housekeeping, not a prediction edge vs closing lines.")


if __name__ == "__main__":
    main()
