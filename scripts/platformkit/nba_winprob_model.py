"""scripts/platformkit/nba_winprob_model.py — Multi-feature NBA win-prob walk-forward model.

Trains a LogisticRegression on the 8-col leak-free feature matrix from
NBAAdapter.feature_bundle() using a strictly expanding-window walk-forward
loop.  No future information is used at prediction time.

HONESTY: calibration/accuracy != edge.  Improved Brier/ECE vs the solo-Elo
recalibrated baseline does NOT imply beating the closing line or positive EV.
See: feedback_accuracy_is_not_edge.md.

CLI: python -m scripts.platformkit.nba_winprob_model
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WARMUP: int = 50          # rows before the model has enough history
REFIT_EVERY: int = 10     # refit every K rows (expanding window, strictly prior)

HONEST_NOTE = (
    "DISCIPLINE: calibration != edge. Improved Brier/ECE vs solo-Elo does NOT "
    "imply beating the closing line or positive expected value. NO edge claimed."
)

# ---------------------------------------------------------------------------
# Core walk-forward fitter
# ---------------------------------------------------------------------------


def fit_winprob(
    base: np.ndarray,
    target: np.ndarray,
    signal_col: np.ndarray,
    *,
    min_history: int = WARMUP,
    refit_every: int = REFIT_EVERY,
) -> np.ndarray:
    """Strictly leak-free expanding-window walk-forward LogisticRegression.

    For event i:
      - Train on base[:i] / target[:i] (strictly prior).
      - StandardScaler fitted on the same prior rows only.
      - Fall back to signal_col[i] (solo-Elo prob) during warmup or if the
        prior window has only one class.

    Returns (N,) array of OOS probabilities clipped to [0, 1].

    Parameters
    ----------
    base        : (N, 8) float array — leak-free pre-game features.
    target      : (N,)   float array — home_win {0.0, 1.0}.
    signal_col  : (N,)   float array — fallback 1-D Elo probability.
    min_history : rows before the model activates (default 50).
    refit_every : refit interval in rows (default 10, expanding window).
    """
    base = np.asarray(base, dtype=float)
    target = np.asarray(target, dtype=float)
    signal_col = np.asarray(signal_col, dtype=float)
    n = len(target)
    if base.shape[0] != n or len(signal_col) != n:
        raise ValueError(
            f"base ({base.shape[0]}), target ({n}), signal_col ({len(signal_col)}) "
            "must all have the same length."
        )

    out = np.empty(n, dtype=float)
    lr: Optional[LogisticRegression] = None
    scaler: Optional[StandardScaler] = None
    next_fit: int = min_history

    for i in range(n):
        # ── Warmup: fall back to solo-Elo ──────────────────────────────────
        if i < min_history:
            out[i] = float(signal_col[i]) if np.isfinite(signal_col[i]) else 0.5
            continue

        # ── Refit on strictly prior rows ───────────────────────────────────
        if i >= next_fit:
            valid = (
                np.all(np.isfinite(base[:i]), axis=1)
                & np.isfinite(target[:i])
            )
            X_tr = base[:i][valid]
            y_tr = target[:i][valid]
            if X_tr.shape[0] >= 2 and len(np.unique(y_tr)) >= 2:
                scaler = StandardScaler()
                X_scaled = scaler.fit_transform(X_tr)  # fit on prior only
                lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500)
                lr.fit(X_scaled, y_tr)
            next_fit = i + refit_every

        # ── Predict row i ──────────────────────────────────────────────────
        if lr is not None and scaler is not None and np.all(np.isfinite(base[i])):
            x_i = scaler.transform(base[i : i + 1])
            out[i] = float(lr.predict_proba(x_i)[0, 1])
        else:
            # Fall back to solo-Elo if model not yet ready or bad features
            out[i] = float(signal_col[i]) if np.isfinite(signal_col[i]) else 0.5

    return np.clip(out, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Metric helpers (re-use scoreboard's implementations)
# ---------------------------------------------------------------------------


def _metrics(p: np.ndarray, y: np.ndarray) -> dict:
    """Compute brier/logloss/ece on finite pairs."""
    from scripts.platformkit.scoreboard import (
        _brier,
        _log_loss,
        _ece,
        score_forecaster,
    )
    return score_forecaster(p, y)


# ---------------------------------------------------------------------------
# CLI — comparison table
# ---------------------------------------------------------------------------


def main() -> None:
    """Load real NBA bundle and print a comparison table."""
    import importlib

    print("Loading NBAAdapter …")
    mod = importlib.import_module("domains.basketball_nba.adapter")
    adapter = mod.NBAAdapter()

    print("Building feature bundle …")
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[])

    base = np.asarray(bundle.base, dtype=float)
    target = np.asarray(bundle.target, dtype=float)
    signal_col = np.asarray(bundle.signal_col, dtype=float)
    closing = (
        np.asarray(bundle.closing, dtype=float)
        if bundle.closing is not None
        else np.full(len(target), float("nan"))
    )

    print(f"Corpus: n={len(target)} rows, "
          f"closing-line subset: n={int(np.isfinite(closing).sum())} rows")

    # Walk-forward recal (existing solo-Elo)
    from scripts.platformkit.recalibration import walk_forward_recalibrate
    model_recal = walk_forward_recalibrate(signal_col, target, refit_every=20)

    # Multi-feature walk-forward
    print("Fitting multi-feature walk-forward model …")
    multi_wf = fit_winprob(base, target, signal_col)

    close_mask = np.isfinite(closing)

    from scripts.platformkit.scoreboard import score_forecaster

    def _row(name: str, p: np.ndarray, subset: Optional[np.ndarray] = None) -> dict:
        if subset is not None:
            p_eval = p[subset]
            y_eval = target[subset]
        else:
            p_eval = p
            y_eval = target
        s = score_forecaster(p_eval, y_eval)
        return {"name": name, "n": s["n"], "brier": s["brier"],
                "logloss": s["log_loss"], "ece": s["ece"]}

    rows_full = [
        _row("solo_elo_raw",       signal_col),
        _row("solo_elo_recal",     model_recal),
        _row("multi_feature_wf",   multi_wf),
        _row("naive_coin",         np.full(len(target), 0.5)),
    ]
    rows_close = [
        _row("solo_elo_raw",       signal_col,   close_mask),
        _row("solo_elo_recal",     model_recal,  close_mask),
        _row("multi_feature_wf",   multi_wf,     close_mask),
        _row("naive_coin",         np.full(len(target), 0.5), close_mask),
    ]
    if close_mask.sum() > 0:
        rows_close.append(_row("market_close", closing, close_mask))

    def _print_table(title: str, rows: list) -> None:
        print(f"\n{'=' * 68}")
        print(f"  {title}")
        print(f"{'=' * 68}")
        print(f"  {'Forecaster':<22}  {'N':>6}  {'Brier':>8}  {'LogLoss':>8}  {'ECE':>7}")
        print(f"  {'-' * 60}")
        for r in rows:
            print(f"  {r['name']:<22}  {r['n']:>6}  {r['brier']:>8.5f}  "
                  f"{r['logloss']:>8.5f}  {r['ece']:>7.5f}")
        print(f"{'=' * 68}")

    _print_table("FULL CORPUS", rows_full)
    _print_table("CLOSING-LINE SUBSET", rows_close)

    # Verdict
    recal_brier = next(r["brier"] for r in rows_close if r["name"] == "solo_elo_recal")
    multi_brier = next(r["brier"] for r in rows_close if r["name"] == "multi_feature_wf")
    recal_ece   = next(r["ece"]   for r in rows_close if r["name"] == "solo_elo_recal")
    multi_ece   = next(r["ece"]   for r in rows_close if r["name"] == "multi_feature_wf")

    delta_brier = multi_brier - recal_brier
    delta_ece   = multi_ece   - recal_ece

    if delta_brier < -0.001 and delta_ece < 0.0:
        verdict = (
            f"IMPROVEMENT: multi-feature model beats solo-Elo recal on closing-line subset "
            f"(dBrier={delta_brier:+.5f}, dECE={delta_ece:+.5f}). "
            "Accuracy/calibration only -- no edge claimed."
        )
    elif delta_brier > 0.001 or delta_ece > 0.005:
        verdict = (
            f"NULL/WORSE: multi-feature model does not beat solo-Elo recal on closing-line subset "
            f"(dBrier={delta_brier:+.5f}, dECE={delta_ece:+.5f}). "
            "Honest null result -- extra features add no value here."
        )
    else:
        verdict = (
            f"MARGINAL: multi-feature model is within noise of solo-Elo recal "
            f"(dBrier={delta_brier:+.5f}, dECE={delta_ece:+.5f}). "
            "No meaningful improvement; no edge claimed."
        )

    print(f"\nVERDICT: {verdict}")
    print(f"\n{HONEST_NOTE}\n")


if __name__ == "__main__":
    main()
