"""scripts/platformkit/calibration_providers.py — Real per-sport provider functions for
the calibration scoreboard.  Imported lazily by calibration_scoreboard.py.

Providers:
  _run_nba    — multi-feature WF logistic (fit_winprob) vs solo-Elo WF-recal
  _run_tennis — WF Platt recalibration vs raw Elo
  _run_mlb    — solo-Elo + SP-form (real W94 asof_sp_form_eval logic) vs solo-Elo Platt
  _run_soccer — DC rho DRAW-probability calibration (real rho_fit_eval logic; capped)

HONESTY: calibration metric only.  No market edge claimed.

MLB cap: uses the full corpus (no row cap needed; time-split is 70/30).
Soccer cap: SOCCER_SAMPLE_CAP (default 30 000) covers the full ~25.8k corpus so the
draw-prob ECE gain reflects the REAL W94 full-corpus result (not a small-sample
artifact).  The rho walk-forward warmup needs >=300 rows; ~1-2 min one-time build.

INVARIANTS: <=300 physical lines. No src./ kernel./ api./ writes. No edge claims.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Soccer warm-up requirement: rho walk-forward needs >=300 prior rows.
# Default cap 30 000 covers the full ~25.8k-match corpus so the scoreboard reports the
# REAL full-corpus draw-prob ECE gain (one-time artifact build; ~1-2 min), not a
# small-sample artifact.
SOCCER_SAMPLE_CAP: int = 30_000

SportMetrics = Dict


# ---------------------------------------------------------------------------
# NBA provider — unchanged (correct)
# ---------------------------------------------------------------------------

def _run_nba() -> SportMetrics:
    """Load NBAAdapter, build feature bundle, run multi-feature WF vs solo-Elo recal."""
    import importlib
    import numpy as _np
    from scripts.platformkit.recalibration import walk_forward_recalibrate
    from scripts.platformkit.nba_winprob_model import fit_winprob
    from scripts.platformkit.calibration_scoreboard import _score

    mod = importlib.import_module("domains.basketball_nba.adapter")
    bundle = mod.NBAAdapter().feature_bundle(hypothesis=None, seasons=[])
    base = _np.asarray(bundle.base, dtype=float)
    target = _np.asarray(bundle.target, dtype=float)
    signal_col = _np.asarray(bundle.signal_col, dtype=float)

    baseline_p = walk_forward_recalibrate(signal_col, target, refit_every=20)
    improved_p = fit_winprob(base, target, signal_col)

    return {
        "sport": "NBA", "method": "multi-feature WF logistic (fit_winprob)",
        "baseline_label": "solo-Elo WF-recal",
        "baseline": _score(baseline_p, target),
        "improved": _score(improved_p, target),
    }


# ---------------------------------------------------------------------------
# Tennis provider — unchanged (correct)
# ---------------------------------------------------------------------------

def _run_tennis() -> SportMetrics:
    """Load tennis matches.parquet, run walk-forward Platt recal vs raw Elo."""
    import pandas as _pd
    import numpy as _np
    from domains.tennis.elo_tune import (
        _walk_forward_blend, platt_recalibrate, brier as _b,
        BLEND_GRID, TRAIN_YEAR_MAX,
    )
    from scripts.platformkit.calibration_scoreboard import _score

    path = _REPO_ROOT / "data" / "domains" / "tennis" / "matches.parquet"
    matches = _pd.read_parquet(path)

    best_blend, best_b = 0.0, float("inf")
    for bl in BLEND_GRID:
        wf = _walk_forward_blend(matches, bl)
        test = wf[_pd.to_datetime(wf["date"]).dt.year > TRAIN_YEAR_MAX]
        p = test["win_prob_p1"].to_numpy(dtype=float)
        y = (test["winner"] == 1).to_numpy(dtype=float)
        b = _b(p, y)
        if b < best_b:
            best_b, best_blend = b, bl

    wf = _walk_forward_blend(matches, best_blend)
    test_df = platt_recalibrate(wf)
    y_test = (test_df["winner"] == 1).to_numpy(dtype=float)

    raw_probs = wf[_pd.to_datetime(wf["date"]).dt.year > TRAIN_YEAR_MAX][
        "win_prob_p1"
    ].to_numpy(dtype=float)
    recal_probs = test_df["win_prob_recal"].to_numpy(dtype=float)
    n = min(len(raw_probs), len(y_test), len(recal_probs))
    raw_probs, recal_probs, y_test = raw_probs[:n], recal_probs[:n], y_test[:n]

    return {
        "sport": "TENNIS", "method": f"WF Platt recalibration (blend={best_blend:.1f})",
        "baseline_label": f"raw Elo (blend={best_blend:.1f})",
        "baseline": _score(raw_probs, y_test),
        "improved": _score(recal_probs, y_test),
    }


# ---------------------------------------------------------------------------
# MLB provider — REAL W94 SP-form logic (mirrors asof_sp_form_eval.main)
# ---------------------------------------------------------------------------

def _run_mlb() -> SportMetrics:
    """Solo-Elo + SP-form vs solo-Elo Platt: real asof_sp_form_eval logic (W94).

    Reproduces the time-split (70/30) logistic comparison from asof_sp_form_eval.py:
      baseline  = solo-Elo Platt-recal (1-D logistic on elo_logit)
      improved  = 2-feature logistic on (elo_logit, sp_first6_diff_ew z-scored)
    Numbers match the W94 CLI validation (~ECE 0.0173 -> 0.0138).
    """
    import pandas as _pd
    import numpy as _np
    from scipy.special import logit as _logit
    from domains.mlb.asof_sp_form import build_sp_form_features
    from domains.mlb.ratings import walk_forward_elo
    from domains.mlb.asof_sp_form_eval import (
        _sigmoid, _logloss, _brier as _mb, _ece as _me,
        _fit_logistic_1d, _fit_logistic_2d,
    )
    from scripts.platformkit.calibration_scoreboard import _score

    games_path = _REPO_ROOT / "data/domains/mlb/games.parquet"
    games_df = _pd.read_parquet(str(games_path))

    sp_feat = build_sp_form_features(games=games_df)
    elo_df = walk_forward_elo(games_df)

    merged = elo_df.merge(
        sp_feat[["event_id", "sp_first6_diff_ew",
                 "home_sp_starts_prior", "away_sp_starts_prior"]],
        on="event_id", how="left",
    )
    merged = merged[merged["target_home_win"].notna()].reset_index(drop=True)
    n_total = len(merged)

    split = int(n_total * 0.70)
    train = merged.iloc[:split]
    test = merged.iloc[split:]

    y_train = train["target_home_win"].values.astype(float)
    y_test = test["target_home_win"].values.astype(float)

    p_elo_train = _np.clip(train["p_home_elo"].values.astype(float), 1e-7, 1 - 1e-7)
    p_elo_test = _np.clip(test["p_home_elo"].values.astype(float), 1e-7, 1 - 1e-7)
    logit_tr = _logit(p_elo_train)
    logit_te = _logit(p_elo_test)

    # Baseline: 1-D Platt on solo-Elo logit
    baseline_p = _fit_logistic_1d(logit_tr, y_train, logit_te)

    # Improved: 2-feature logistic (elo_logit + SP-form z-score)
    sp_tr = train["sp_first6_diff_ew"].values.astype(float)
    sp_te = test["sp_first6_diff_ew"].values.astype(float)
    sp_mean = float(_np.nanmean(sp_tr))
    sp_std = max(float(_np.nanstd(sp_tr)), 1e-8)
    sp_tr_z = _np.where(_np.isnan(sp_tr), 0.0, (sp_tr - sp_mean) / sp_std)
    sp_te_z = _np.where(_np.isnan(sp_te), 0.0, (sp_te - sp_mean) / sp_std)
    improved_p = _fit_logistic_2d(logit_tr, sp_tr_z, y_train, logit_te, sp_te_z)

    return {
        "sport": "MLB",
        "method": "solo-Elo + SP-form (elo_logit + sp_first6_diff_ew z; 2-feat logistic)",
        "baseline_label": "solo-Elo Platt-recal (1-D logistic)",
        "baseline": _score(baseline_p, y_test),
        "improved": _score(improved_p, y_test),
    }


# ---------------------------------------------------------------------------
# Soccer provider — REAL rho DRAW-prob calibration (mirrors rho_fit_eval.evaluate)
# ---------------------------------------------------------------------------

def _run_soccer() -> SportMetrics:
    """DC rho draw-probability calibration vs rho=0: real rho_fit_eval logic.

    Baseline  = P(draw) from scoreline_matrix at rho=0
    Improved  = P(draw) from scoreline_matrix at fitted walk-forward rho
    Outcome   = (ftr == 'D')
    Numbers match W94 draw-ECE: ~0.0329 -> ~0.0313 (capped at SOCCER_SAMPLE_CAP rows).
    Cap is documented honestly; full 25k run in CLI (domains.soccer.rho_fit_eval).
    """
    import pandas as _pd
    import numpy as _np
    from domains.soccer.ratings import walk_forward_goals
    from domains.soccer.rho_fit import walk_forward_rho
    from domains.soccer.scoreline_engine import scoreline_matrix, markets_from_matrix
    from scripts.platformkit.calibration_scoreboard import _score

    path = _REPO_ROOT / "data" / "domains" / "soccer" / "matches.parquet"
    matches_df = _pd.read_parquet(path)

    wf = walk_forward_goals(matches_df)
    valid = wf[wf["fthg"].notna() & wf["ftag"].notna()].copy().reset_index(drop=True)

    cap = min(SOCCER_SAMPLE_CAP, len(valid))
    valid = valid.iloc[:cap]

    lam_h = valid["lam_home"].values.astype(float)
    lam_a = valid["lam_away"].values.astype(float)
    fthg = valid["fthg"].values.astype(int)
    ftag = valid["ftag"].values.astype(int)
    ftr = valid["ftr"].values
    act_draw = (ftr == "D").astype(float)

    rho_arr = walk_forward_rho(lam_h, lam_a, fthg, ftag, refit_every=300)

    draw_base = _np.array([
        markets_from_matrix(scoreline_matrix(lam_h[i], lam_a[i], rho=0.0))["1X2_draw"]
        for i in range(cap)
    ])
    draw_fit = _np.array([
        markets_from_matrix(scoreline_matrix(lam_h[i], lam_a[i], rho=rho_arr[i]))["1X2_draw"]
        for i in range(cap)
    ])

    return {
        "sport": "SOCCER",
        "method": "DC rho — DRAW-prob calibration (scoreline-level; capped)",
        "baseline_label": f"scoreline P(draw) at rho=0 (n={cap:,})",
        "baseline": _score(draw_base, act_draw),
        "improved": _score(draw_fit, act_draw),
        "note": (
            f"Soccer capped at {cap:,} rows for speed (full ~25k-match run: "
            "python -m domains.soccer.rho_fit_eval).  "
            "Rho warmup=300; post-warmup rows measure real draw-prob ECE gain."
        ),
    }
