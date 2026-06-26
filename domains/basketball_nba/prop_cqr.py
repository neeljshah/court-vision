"""domains.basketball_nba.prop_cqr -- Conformalized Quantile Regression (CQR)
for NBA prop intervals. Leak-free walk-forward gate vs the incumbent
constant-width split-conformal band.

Adaptive-width predictive interval: train lower/upper quantile LightGBM on a
chronological TRAIN fold, conformalize the residual E_i = max(q_lo(x_i)-y_i,
y_i-q_hi(x_i)) on a held-out CALIB fold, evaluate empirical coverage + pinball
loss on a held-out TEST fold vs the incumbent split-conformal (one residual
quantile for all x).

HONEST: calibration only. No $ / ROI / edge field anywhere. An honest REJECT
(CQR fails to beat the incumbent on >=2 stats) is a SUCCESS, not a failure.

INVARIANTS: <=300 LOC; ASCII only; no src/ imports; no network I/O; read-only.
Default-OFF: measurement script, not wired into pricing.

Public API::
    from domains.basketball_nba.prop_cqr import run_cqr_gate, INSUFFICIENT_DATA
    verdict = run_cqr_gate()  # {stat: dict | INSUFFICIENT_DATA}
"""
from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Dict, Tuple, Union

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_OOF_PATH = Path("data/cache/pregame_oof.parquet")
_ALPHA = 0.10
_MIN_N = 200
_TRAIN_FRAC = 0.50
_CALIB_FRAC = 0.25
_TEST_FRAC = 0.25
_RNG_SEED = 42
_LGBM_PARAMS = {
    "n_estimators": 100, "learning_rate": 0.05, "num_leaves": 31,
    "min_data_in_leaf": 50, "verbose": -1, "random_state": 42, "force_col_wise": True,
}
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
_HONEST_NOTE = "CQR (adaptive-width) vs split-conformal (constant-width). Calibration only -- no $ edge."
_FEATURE_COLS = ["oof_pred", "rolling_mean_15", "rolling_std_15", "rolling_median_15",
                 "n_prior", "season_avg_to_date"]


def _build_leak_free_features(df_stat: pd.DataFrame) -> pd.DataFrame:
    """Leak-free features from strictly prior player games. Drops n_prior < 5 rows."""
    df = df_stat[["player_id", "game_date", "season", "actual", "oof_pred"]].copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["player_id", "game_date"], kind="stable").reset_index(drop=True)

    def _player_feats(grp: pd.DataFrame) -> pd.DataFrame:
        shifted = grp["actual"].shift(1)
        roll = shifted.rolling(window=15, min_periods=1)
        grp = grp.copy()
        grp["rolling_mean_15"] = roll.mean()
        grp["rolling_std_15"] = roll.std(ddof=1).fillna(0.0)
        grp["rolling_median_15"] = roll.median()
        grp["n_prior"] = np.arange(len(grp), dtype=float)
        grp["season_avg_to_date"] = shifted.expanding(min_periods=1).mean()
        return grp

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        df = df.groupby("player_id", sort=False, group_keys=False).apply(_player_feats)
    df["n_prior"] = df["n_prior"].clip(upper=50.0)
    df["season_avg_to_date"] = df["season_avg_to_date"].fillna(df["rolling_mean_15"]).fillna(0.0)
    df["rolling_mean_15"] = df["rolling_mean_15"].fillna(0.0)
    df["rolling_median_15"] = df["rolling_median_15"].fillna(0.0)
    df = df[df["n_prior"] >= 5.0].reset_index(drop=True)
    return df[["player_id", "game_date", "season", "actual", "oof_pred"] + _FEATURE_COLS[1:]]


def _chrono_split(
    df_feat: pd.DataFrame,
    train_frac: float = _TRAIN_FRAC,
    calib_frac: float = _CALIB_FRAC,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Chronological split; push tie dates fully into the later split."""
    df = df_feat.sort_values("game_date", kind="stable").reset_index(drop=True)
    n = len(df)
    t_date = df.iloc[int(np.floor(n * train_frac))]["game_date"]
    c_date = df.iloc[min(int(np.floor(n * (train_frac + calib_frac))), n - 1)]["game_date"]
    return (
        df[df["game_date"] < t_date].copy(),
        df[(df["game_date"] >= t_date) & (df["game_date"] < c_date)].copy(),
        df[df["game_date"] >= c_date].copy(),
    )


def _train_quantile_lgbm(X: np.ndarray, y: np.ndarray, alpha: float):
    """Train a LightGBM quantile booster at level alpha."""
    import lightgbm as lgb
    params = {k: v for k, v in _LGBM_PARAMS.items() if k != "n_estimators"}
    params.update({"objective": "quantile", "alpha": alpha, "metric": "quantile"})
    return lgb.train(params=params, train_set=lgb.Dataset(X, y, free_raw_data=False),
                     num_boost_round=_LGBM_PARAMS["n_estimators"])


def _predict(booster, X: np.ndarray) -> np.ndarray:
    return booster.predict(X)


def _enforce_non_crossing(q_lo: np.ndarray, q_hi: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Where q_lo > q_hi, set both to their midpoint."""
    mid = (q_lo + q_hi) / 2.0
    crossed = q_lo > q_hi
    return np.where(crossed, mid, q_lo), np.where(crossed, mid, q_hi)


def _conformity_scores(q_lo: np.ndarray, q_hi: np.ndarray, y: np.ndarray) -> np.ndarray:
    """CQR conformity score E = max(q_lo - y, y - q_hi). Negative when y inside band."""
    return np.maximum(q_lo - y, y - q_hi)


def _cqr_band(
    q_lo_test: np.ndarray, q_hi_test: np.ndarray, E_calib: np.ndarray, alpha: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Finite-sample CQR conformal correction."""
    level = min(1.0, np.ceil((1.0 - alpha) * (len(E_calib) + 1)) / len(E_calib))
    Q = float(np.quantile(E_calib, level))
    return q_lo_test - Q, q_hi_test + Q


def _split_conformal_band(
    point_test: np.ndarray, residuals_calib: np.ndarray, alpha: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Incumbent constant-width split-conformal band."""
    level = min(1.0, np.ceil((1.0 - alpha) * (len(residuals_calib) + 1)) / len(residuals_calib))
    Q = float(np.quantile(residuals_calib, level))
    return point_test - Q, point_test + Q


def _pinball_loss(y: np.ndarray, q_pred: np.ndarray, q: float) -> float:
    diff = y - q_pred
    return float(np.mean(np.maximum(q * diff, (q - 1.0) * diff)))


def _score(y: np.ndarray, lo: np.ndarray, hi: np.ndarray, alpha: float) -> dict:
    """Coverage, width stats, and symmetric pinball loss."""
    width = hi - lo
    pb = (_pinball_loss(y, lo, alpha / 2.0) + _pinball_loss(y, hi, 1.0 - alpha / 2.0)) / 2.0
    return {
        "coverage": round(float(np.mean((y >= lo) & (y <= hi))), 5),
        "width_mean": round(float(np.mean(width)), 4),
        "width_std": round(float(np.std(width)), 4),
        "pinball": round(pb, 5),
    }


def _planted_null_features(df_feat: pd.DataFrame, rng_seed: int) -> pd.DataFrame:
    """Joint-shuffle features to break row<->label alignment (planted null)."""
    rng = np.random.default_rng(rng_seed)
    df = df_feat.copy()
    df[_FEATURE_COLS] = df[_FEATURE_COLS].to_numpy()[rng.permutation(len(df))]
    return df


def _run_cqr_on_splits(
    df_train: pd.DataFrame, df_calib: pd.DataFrame, df_test: pd.DataFrame, alpha: float,
) -> Tuple[dict, dict]:
    """Fit CQR + split-conformal; return (cqr_scores, sc_scores)."""
    Xtr = df_train[_FEATURE_COLS].to_numpy(dtype=float)
    ytr = df_train["actual"].to_numpy(dtype=float)
    Xcal = df_calib[_FEATURE_COLS].to_numpy(dtype=float)
    ycal = df_calib["actual"].to_numpy(dtype=float)
    Xte = df_test[_FEATURE_COLS].to_numpy(dtype=float)
    yte = df_test["actual"].to_numpy(dtype=float)

    blo = _train_quantile_lgbm(Xtr, ytr, alpha / 2.0)
    bhi = _train_quantile_lgbm(Xtr, ytr, 1.0 - alpha / 2.0)

    qlo_cal, qhi_cal = _enforce_non_crossing(_predict(blo, Xcal), _predict(bhi, Xcal))
    E_calib = _conformity_scores(qlo_cal, qhi_cal, ycal)

    qlo_te, qhi_te = _enforce_non_crossing(_predict(blo, Xte), _predict(bhi, Xte))
    lo_cqr, hi_cqr = _cqr_band(qlo_te, qhi_te, E_calib, alpha)

    res_cal = np.abs(df_calib["oof_pred"].to_numpy(dtype=float) - ycal)
    lo_sc, hi_sc = _split_conformal_band(df_test["oof_pred"].to_numpy(dtype=float), res_cal, alpha)

    return _score(yte, lo_cqr, hi_cqr, alpha), _score(yte, lo_sc, hi_sc, alpha)


def _per_stat(df_stat: pd.DataFrame, alpha: float) -> Union[str, dict]:
    """Full CQR gate for one stat. Returns verdict dict or INSUFFICIENT_DATA."""
    df_feat = _build_leak_free_features(df_stat)
    df_train, df_calib, df_test = _chrono_split(df_feat)
    if len(df_test) < _MIN_N:
        return INSUFFICIENT_DATA

    cqr_s, sc_s = _run_cqr_on_splits(df_train, df_calib, df_test, alpha)

    df_null = _planted_null_features(df_feat, _RNG_SEED)
    cqr_null, _ = _run_cqr_on_splits(*_chrono_split(df_null), alpha)

    nominal = 1.0 - alpha
    cqr_gap = round(cqr_s["coverage"] - nominal, 5)
    sc_gap = round(sc_s["coverage"] - nominal, 5)
    cqr_beats_cov = bool(abs(cqr_gap) <= abs(sc_gap))
    cqr_beats_pb = bool(cqr_s["pinball"] <= sc_s["pinball"])
    # When features are shuffled the model loses signal -> conformal correction
    # inflates band mean significantly (null_mean > 1.5x real = real signal present).
    null_collapses = bool(cqr_null["width_mean"] > 1.5 * cqr_s["width_mean"])

    checks_failed = (
        (["coverage"] if not cqr_beats_cov else []) +
        (["pinball"] if not cqr_beats_pb else []) +
        (["planted_null"] if not null_collapses else [])
    )
    ship = "SHIP" if not checks_failed else "REJECT:" + "+".join(checks_failed)

    return {
        "stat": str(df_stat["stat"].iloc[0]),
        "n_train": len(df_train), "n_calib": len(df_calib), "n_test": len(df_test),
        "alpha": alpha, "nominal": nominal,
        "cqr_coverage": cqr_s["coverage"], "cqr_width_mean": cqr_s["width_mean"],
        "cqr_width_std": cqr_s["width_std"], "cqr_pinball": cqr_s["pinball"],
        "sc_coverage": sc_s["coverage"], "sc_width_mean": sc_s["width_mean"],
        "sc_width_std": sc_s["width_std"], "sc_pinball": sc_s["pinball"],
        "cqr_coverage_gap": cqr_gap, "sc_coverage_gap": sc_gap,
        "cqr_beats_sc_coverage": cqr_beats_cov, "cqr_beats_sc_pinball": cqr_beats_pb,
        "cqr_width_mean_planted": cqr_null["width_mean"],
        "cqr_width_std_planted": cqr_null["width_std"],
        "planted_null_collapses": null_collapses,
        "ship_recommendation": ship, "honest_note": _HONEST_NOTE,
    }


def run_cqr_gate(
    oof_path: Path = _OOF_PATH, alpha: float = _ALPHA,
) -> Dict[str, Union[str, dict]]:
    """Run the CQR gate over all stats. Returns {stat: verdict | INSUFFICIENT_DATA}.

    Never raises. Never writes files. No $ fields.
    """
    oof_path = Path(oof_path)
    if not oof_path.exists():
        log.warning("prop_cqr: OOF not found at %s", oof_path)
        return {}
    try:
        df = pd.read_parquet(oof_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("prop_cqr: failed to read OOF: %s", exc)
        return {}
    required = {"player_id", "stat", "oof_pred", "actual", "game_date", "season"}
    if not required.issubset(df.columns):
        log.warning("prop_cqr: OOF missing columns %s", required - set(df.columns))
        return {}
    return {stat: _per_stat(df[df["stat"] == stat].copy(), alpha)
            for stat in sorted(df["stat"].unique())}


def _main() -> None:
    import logging as _lg
    _lg.basicConfig(level=_lg.WARNING, format="%(levelname)s %(message)s")
    results = run_cqr_gate()
    if not results:
        print("No results (OOF absent or missing columns).")
        return
    hdr = (f"  {'stat':<6} {'n_test':>7}  {'cqr_cov':>8} {'sc_cov':>7}"
           f"  {'cqr_wid':>8} {'sc_wid':>7}  {'cqr_pb':>7} {'sc_pb':>7}  verdict")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    ship_n = reject_n = 0
    for stat in sorted(results):
        r = results[stat]
        if r == INSUFFICIENT_DATA:
            print(f"  {stat:<6}  INSUFFICIENT_DATA")
            continue
        assert isinstance(r, dict)
        v = r["ship_recommendation"]
        ship_n += (v == "SHIP")
        reject_n += (v != "SHIP")
        print(f"  {stat:<6} {r['n_test']:>7}  "
              f"{r['cqr_coverage']:>7.1%} {r['sc_coverage']:>7.1%}  "
              f"{r['cqr_width_mean']:>8.3f} {r['sc_width_mean']:>7.3f}  "
              f"{r['cqr_pinball']:>7.4f} {r['sc_pinball']:>7.4f}  {v}")
    print(f"\n  SHIP={ship_n}  REJECT={reject_n}  (honest gate -- REJECT is success)")
    print(f"  {_HONEST_NOTE}")


if __name__ == "__main__":
    _main()
