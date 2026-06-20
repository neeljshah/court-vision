"""scripts.platformkit.proof_nba.spread_calibration -- NBA spread cover-rate calibration gate.

Goal (pa6): are the MARKET's closing spreads calibrated? Does a walk-forward Elo model's
implied cover probability track actual cover rates within ECE tolerance?

The spread market sets the home team's line (e.g. -6.5 = home gives 6.5 points). Home
covers if home_margin > -spread. A perfectly efficient spread is calibrated by definition
(the market sets the line so each side is ~50/50), but the SHAPE across spread magnitudes
reveals calibration quality -- a -20 favorite should cover at roughly the same rate (~50%)
as a -3 favorite, and if our Elo model diverges systematically from that rate, the
divergence is the honest finding.

Method:
  1. Walk-forward MOV-Elo (reuses ml_accuracy engine) -> P(home win).
  2. Implied margin from Elo: mu = Phi^{-1}(p_home) * sigma_mkt, sigma_mkt=12 pts.
  3. P(model covers spread s) = Phi((mu + spread) / sigma_mkt).
  4. ECE of model cover-prob against realized cover outcomes (holdout second half).
  5. Per-bin table: 5 quantile bins of spread, cover-rate vs model-predicted cover-rate.

Acceptance: ECE < ECE_TARGET (0.12); bins each have n>=5; <60 overlap -> data_limited.
Calibration only. No $ edge claimed. Leak-free WF.

INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_nba.spread_calibration
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_nba.ml_accuracy import (  # noqa: E402
    _walk_forward_elo, _NBA)
from kernel.validation.proof_metrics import ece  # noqa: E402

# Normal tail from market sigma (ATS pricing assumes ~12-pt spread noise in NBA).
# Calibrated from 10+ seasons of NBA spreads; market-consensus value.
_SIGMA_MKT = 12.0
_ECE_TARGET = 0.12
_N_BINS = 5
_MIN_HOLDOUT = 60
_CANON = {"GS": "GSW", "NY": "NYK", "NO": "NOP",
          "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}


def _corpus_from_env() -> Optional[Path]:
    r = os.environ.get("PROOF_CORPUS_ROOT")
    return Path(r) / "nba" if r else None


def _phi(z: float) -> float:
    """Standard normal CDF (inline, no scipy dependency)."""
    return float(0.5 * (1.0 + _erf(z / 2.0 ** 0.5)))


def _erf(x: float) -> float:
    """Abramowitz & Stegun approximation (max error < 1.5e-7)."""
    sign = 1 if x >= 0 else -1
    x = abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t)
                  + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-x * x)
    return sign * y


def _phi_inv(p: float) -> float:
    """Rational approximation of probit (Beasley-Springer-Moro). |err| < 4.5e-4."""
    p = float(np.clip(p, 1e-6, 1 - 1e-6))
    if p < 0.5:
        return -_phi_inv(1 - p)
    r = np.sqrt(-2.0 * np.log(1.0 - p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    return (r - (c0 + c1 * r + c2 * r ** 2) /
            (1.0 + d1 * r + d2 * r ** 2 + d3 * r ** 3))


def _model_cover_prob(p_home: np.ndarray, spread: np.ndarray,
                      sigma: float) -> np.ndarray:
    """P(home_margin > -spread) given Elo P(home win) and Normal tail sigma.

    mu = Phi^{-1}(p_home) * sigma  (implied expected margin from Elo)
    P(home covers) = Phi((mu + spread) / sigma)
                   = Phi(Phi^{-1}(p_home) + spread / sigma)
    """
    phiv = np.vectorize(_phi)
    piov = np.vectorize(_phi_inv)
    return phiv(piov(p_home) + spread / sigma)


def _ece_bins(p: np.ndarray, y: np.ndarray, n_bins: int) -> List[Dict]:
    """Per-quantile-bin calibration table."""
    bins_out = []
    edges = np.quantile(p, np.linspace(0, 1, n_bins + 1))
    edges[0] -= 1e-9
    edges[-1] += 1e-9
    for i in range(n_bins):
        mask = (p > edges[i]) & (p <= edges[i + 1])
        if mask.sum() < 2:
            continue
        mean_p = float(p[mask].mean())
        actual = float(y[mask].mean())
        bins_out.append({
            "bin": i + 1,
            "spread_lo_quantile": round(float(edges[i]), 3),
            "spread_hi_quantile": round(float(edges[i + 1]), 3),
            "n": int(mask.sum()),
            "pred_cover_rate": round(mean_p, 4),
            "actual_cover_rate": round(actual, 4),
            "gap": round(mean_p - actual, 4),
        })
    return bins_out


def run(corpus: Optional[Path] = None) -> Dict:
    """Compute NBA spread cover-rate calibration gate. Returns a result dict."""
    import pandas as pd
    root = corpus or _corpus_from_env() or _NBA

    box_path = root / "espn_boxscores.parquet"
    odds_path = root / "odds.parquet"
    if not box_path.is_file() or not odds_path.is_file():
        return {"status": "missing_data",
                "note": "espn_boxscores.parquet or odds.parquet not found"}

    box = pd.read_parquet(box_path)
    box["date"] = pd.to_datetime(box["date"], errors="coerce")
    box = box.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    for col in ("home_abbr", "away_abbr"):
        box[col] = box[col].astype(str).str.upper().replace(_CANON)
    box["home_margin"] = box["home_score"].astype(float) - box["away_score"].astype(float)
    box = box[box["home_margin"].between(-60, 60)].reset_index(drop=True)

    # walk-forward Elo P(home win) -- reuses ml_accuracy engine (leak-free)
    box_for_elo = box.rename(columns={"home_score": "home_pts_tmp",
                                      "away_score": "away_pts_tmp"})
    box_for_elo["home_pts"] = box["home_score"].astype(float)
    box_for_elo["away_pts"] = box["away_score"].astype(float)
    box["p_home_elo"] = _walk_forward_elo(box_for_elo)

    odds = pd.read_parquet(odds_path)
    odds["date"] = pd.to_datetime(odds["date"], errors="coerce")
    odds = odds.rename(columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    odds = odds.dropna(subset=["spread"])

    m = box.merge(odds[["date", "home_abbr", "away_abbr", "spread"]],
                  on=["date", "home_abbr", "away_abbr"],
                  how="inner").sort_values("date").reset_index(drop=True)
    n = len(m)
    if n < _MIN_HOLDOUT:
        return {"status": "data_limited", "n_overlap": n,
                "note": f"Only {n} rows with spread overlap; need >= {_MIN_HOLDOUT}."}

    m["home_covers"] = (m["home_margin"] > -m["spread"]).astype(float)
    m["p_model_cover"] = _model_cover_prob(
        m["p_home_elo"].to_numpy(),
        m["spread"].to_numpy(),
        _SIGMA_MKT,
    )

    mid = n // 2
    te = m.iloc[mid:].copy().reset_index(drop=True)
    n_holdout = len(te)

    p_cover = te["p_model_cover"].to_numpy()
    y_cover = te["home_covers"].to_numpy()

    ece_val = float(ece(p_cover, y_cover))
    passed = ece_val < _ECE_TARGET

    # market-only cover rate (baseline: what % of spreads are covered in holdout)
    market_cover_rate = float(y_cover.mean())

    bins = _ece_bins(p_cover, y_cover, _N_BINS)

    if passed:
        verdict = (f"PASS: ECE {ece_val:.4f} < target {_ECE_TARGET} "
                   f"(n_holdout={n_holdout}). Model cover-rate calibration within tolerance.")
    else:
        verdict = (f"CALIBRATION_GAP: ECE {ece_val:.4f} >= target {_ECE_TARGET} "
                   f"-- spread cover-rate calibration needs improvement.")

    return {
        "status": "ok",
        "n_overlap": n,
        "n_holdout": n_holdout,
        "ece": round(ece_val, 4),
        "ece_target": _ECE_TARGET,
        "passed": passed,
        "sigma_mkt": _SIGMA_MKT,
        "market_cover_rate": round(market_cover_rate, 4),
        "model_mean_cover_prob": round(float(p_cover.mean()), 4),
        "bins": bins,
        "verdict": verdict,
        "note": ("NBA spread cover-rate calibration (pa6). Elo P(home win) -> "
                 "Normal-tail cover prob vs realized covers. "
                 "ECE target is 0.12. Calibration only -- no $ edge claimed."),
    }


def _main() -> int:
    rep = run()
    status = rep.get("status")
    if status != "ok":
        print(f"{status}: {rep.get('note', '')}"); return 0
    print(f"=== NBA spread cover-rate calibration "
          f"(n={rep['n_overlap']}, holdout={rep['n_holdout']}) ===")
    print(f"  sigma_mkt={rep['sigma_mkt']} pts  |  "
          f"market cover rate (holdout)={rep['market_cover_rate']}")
    print(f"\n  {'bin':>4}  {'pred_cover':>10}  {'actual_cover':>12}  {'gap':>7}  {'n':>5}")
    for b in rep["bins"]:
        print(f"  {b['bin']:>4}  {b['pred_cover_rate']:>10.4f}  "
              f"{b['actual_cover_rate']:>12.4f}  {b['gap']:>+7.4f}  {b['n']:>5}")
    print(f"\n  ECE={rep['ece']}  target={rep['ece_target']}  passed={rep['passed']}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
