"""Count-stat interval recalibration (profile-factory iteration 2, local lane).

Iter-1 finding: BLK 90% interval coverage was 0.742 (vs 0.90 nominal) — blocks are
overdispersed with fat tails the Poisson/Gaussian interval misses. This script tests, on the
real walk-forward OOF data, whether a NegBinom predictive interval (mean-dependent dispersion)
restores coverage for the low-mean count stats.

Honest gate: NegBinom empirical 90% coverage must land closer to 0.90 than the Poisson baseline.
Output: data/cache/count_interval_calibration.parquet  (per stat: dispersion + Poisson vs NB coverage)
        + per-player blk dispersion for downstream profile section `interval_calibration`.

Reads only data/cache/pregame_oof.parquet. No RunPod, no db, no profiles JSON edits.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
OOF = ROOT / "data" / "cache" / "pregame_oof.parquet"
OUT = ROOT / "data" / "cache" / "count_interval_calibration.parquet"
OUT_PLAYER = ROOT / "data" / "cache" / "blk_player_dispersion.parquet"

COUNT_STATS = ["blk", "stl", "fg3m", "ast", "reb", "tov", "pts"]
LO, HI, NOMINAL = 0.05, 0.95, 0.90

# Production emitted per-stat sigma (mean of predictions_cache_2026-05-26.parquet `sigma`).
# These are the intervals the system actually ships; measured too-tight here.
LIVE_SIGMA = {"blk": 0.398, "stl": 0.733, "fg3m": 0.954, "ast": 1.472,
              "reb": 2.106, "tov": 0.932, "pts": 4.773}


def nb_interval(mu: np.ndarray, phi: float):
    """NegBinom q05/q95 given per-row mean mu and constant dispersion phi=var/mean (>1)."""
    mu = np.clip(mu, 1e-3, None)
    phi = max(phi, 1.01)
    var = phi * mu
    p = mu / var                       # = 1/phi
    n = mu * mu / (var - mu)           # size
    lo = stats.nbinom.ppf(LO, n, p)
    hi = stats.nbinom.ppf(HI, n, p)
    return lo, hi


def pois_interval(mu: np.ndarray):
    mu = np.clip(mu, 1e-3, None)
    return stats.poisson.ppf(LO, mu), stats.poisson.ppf(HI, mu)


def gauss_interval(mu: np.ndarray, sigma: np.ndarray):
    z = stats.norm.ppf(HI)
    return mu - z * sigma, mu + z * sigma


def coverage(actual, lo, hi):
    return float(np.mean((actual >= lo) & (actual <= hi)))


def main():
    df = pd.read_parquet(OOF)
    # expected long format: player_id, stat, oof_pred, actual
    need = {"player_id", "stat", "oof_pred", "actual"}
    if not need.issubset(df.columns):
        raise SystemExit(f"OOF missing cols; has {list(df.columns)}")
    df = df.dropna(subset=["oof_pred", "actual"])

    rows = []
    for st in COUNT_STATS:
        g = df[df["stat"] == st]
        if g.empty:
            continue
        mu = g["oof_pred"].to_numpy(float)
        actual = g["actual"].to_numpy(float)
        # method-of-moments dispersion phi = mean( (actual-mu)^2 / mu )
        m = mu > 0.1
        phi = float(np.mean((actual[m] - mu[m]) ** 2 / mu[m])) if m.any() else 1.0
        # baselines
        plo, phi_hi = pois_interval(mu)
        cov_pois = coverage(actual, plo, phi_hi)
        # gaussian using residual-std sigma (constant) — proxy for the emitted Gaussian band
        sigma = float(np.std(actual - mu))
        glo, ghi = gauss_interval(mu, np.full_like(mu, sigma))
        cov_gauss = coverage(actual, glo, ghi)
        # negbinom
        nlo, nhi = nb_interval(mu, phi)
        cov_nb = coverage(actual, nlo, nhi)
        # PRODUCTION fix: emitted live-cache sigma is too tight. Measure before->after.
        live_sigma = LIVE_SIGMA.get(st)
        cov_live = None
        inflation = None
        if live_sigma:
            llo, lhi = gauss_interval(mu, np.full_like(mu, live_sigma))
            cov_live = round(coverage(actual, llo, lhi), 4)   # BEFORE (production)
            inflation = round(sigma / live_sigma, 3)          # recommended sigma x-factor
        rows.append({
            "stat": st, "n": int(len(g)), "mean_pred": round(float(mu.mean()), 3),
            "mean_actual": round(float(actual.mean()), 3),
            "var_actual": round(float(actual.var()), 3),
            "dispersion_phi": round(phi, 3),
            "live_sigma": live_sigma,
            "resid_sigma": round(sigma, 3),
            "sigma_inflation_factor": inflation,
            "cov_live_sigma_BEFORE": cov_live,
            "cov_resid_sigma_AFTER": round(cov_gauss, 4),
            "cov_poisson": round(cov_pois, 4),
            "cov_negbinom": round(cov_nb, 4),
            "nominal": NOMINAL,
        })

    res = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    res.to_parquet(OUT, index=False)
    pd.set_option("display.width", 160)
    print("=== Count-stat interval calibration (90% nominal) ===")
    print(res.to_string(index=False))

    # per-player BLK dispersion (>=15 obs) for the interval_calibration profile section
    gb = df[df["stat"] == "blk"]
    prows = []
    for pid, pg in gb.groupby("player_id"):
        mu = pg["oof_pred"].to_numpy(float)
        a = pg["actual"].to_numpy(float)
        if len(pg) < 15:
            continue
        m = mu > 0.1
        if not m.any():
            continue
        phi = float(np.mean((a[m] - mu[m]) ** 2 / mu[m]))
        nlo, nhi = nb_interval(mu, phi)
        prows.append({
            "player_id": int(pid), "stat": "blk", "n": int(len(pg)),
            "mean_pred": round(float(mu.mean()), 3),
            "mean_actual": round(float(a.mean()), 3),
            "dispersion_phi": round(phi, 3),
            "cov_negbinom": round(coverage(a, nlo, nhi), 4),
            "cov_poisson": round(coverage(a, *pois_interval(mu)), 4),
        })
    pdf = pd.DataFrame(prows)
    pdf.to_parquet(OUT_PLAYER, index=False)
    print(f"\nPer-player BLK dispersion: {len(pdf)} players (>=15 obs) -> {OUT_PLAYER.name}")
    if not pdf.empty:
        print(f"  median blk dispersion_phi: {pdf['dispersion_phi'].median():.3f}")
        print(f"  mean cov_poisson {pdf['cov_poisson'].mean():.3f} -> cov_negbinom {pdf['cov_negbinom'].mean():.3f}")


if __name__ == "__main__":
    main()
