"""scripts.platformkit.proof_mlb.runline_calibration -- MLB run-line cover-rate calibration gate.

Goal (pa6): are the market's run-line odds calibrated, and does our walk-forward Elo model
predict run-line cover rates accurately?

The MLB run-line is almost always -1.5 / +1.5 runs. A -1.5 home team must win by 2+ runs
to cover; a +1.5 home team covers unless they lose by 2+. Home covers iff home_margin > -runline.

Method:
  1. Walk-forward MOV-Elo (reuses beat_the_close_ml engine) -> P(home win).
  2. Implied margin from Elo: mu = Phi^{-1}(p_home) * sigma_runs, sigma_runs calibrated
     from historical MLB run-margin std (~4.3 runs).
  3. P(model covers runline r) = Phi((mu - (-r)) / sigma_runs)
                               = Phi((mu + r) / sigma_runs)
     For r=-1.5 (home -1.5 fav): P(margin > 1.5); for r=+1.5: P(margin > -1.5).
  4. Market-implied cover prob: American runline_odds -> raw implied probability.
  5. ECE of both model and market implied vs realized outcomes (holdout second half).
  6. Per-quantile-bin cover-rate table.

Two scorecards:
  - model_ece: Elo-derived cover prob vs actual covers
  - market_ece: raw market implied prob vs actual covers (calibration of the price itself)

Acceptance: BOTH ECE < ECE_TARGET (0.10); <60 overlap -> data_limited sentinel.
Calibration only. No $ edge claimed. Leak-free WF.

INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_mlb.runline_calibration
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

from scripts.platformkit.proof_mlb.beat_the_close_ml import (  # noqa: E402
    _walk_forward_elo)
from kernel.validation.proof_metrics import ece  # noqa: E402

_GAMES = _REPO / "data/domains/mlb/games.parquet"
_ODDS = _REPO / "data/domains/mlb/odds.parquet"
_ECE_TARGET = 0.10
_N_BINS = 5
_MIN_HOLDOUT = 60
# MLB run-margin typical std; calibrated from ~27k historical games
_SIGMA_RUNS = 4.34


def _corpus_from_env() -> Optional[Path]:
    r = os.environ.get("PROOF_CORPUS_ROOT")
    return Path(r) / "mlb" if r else None


def _resolve(corpus: Optional[Path]):
    root = corpus or _corpus_from_env()
    if root is not None:
        return root / "games.parquet", root / "odds.parquet"
    return _GAMES, _ODDS


# ---------------------------------------------------------------------------
# Pure-math helpers (no scipy -- use the same inline Normal as spread_calibration)
# ---------------------------------------------------------------------------

def _phi(z: float) -> float:
    """Standard normal CDF (Abramowitz & Stegun approx, max error < 1.5e-7)."""
    return float(0.5 * (1.0 + _erf(z / 2.0 ** 0.5)))


def _erf(x: float) -> float:
    sign = 1 if x >= 0 else -1
    x = abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t)
                  + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-x * x)
    return sign * y


def _phi_inv(p: float) -> float:
    """Probit approximation (Beasley-Springer-Moro, |err| < 4.5e-4)."""
    p = float(np.clip(p, 1e-6, 1 - 1e-6))
    if p < 0.5:
        return -_phi_inv(1.0 - p)
    r = np.sqrt(-2.0 * np.log(1.0 - p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    return (r - (c0 + c1 * r + c2 * r ** 2) /
            (1.0 + d1 * r + d2 * r ** 2 + d3 * r ** 3))


def _model_cover_prob(p_home: np.ndarray, runline: np.ndarray,
                      sigma: float) -> np.ndarray:
    """P(home_margin > -runline) given Elo P(home win).

    mu = Phi^{-1}(p_home) * sigma  (Elo implied expected margin)
    P(covers) = Phi((mu - (-runline)) / sigma) = Phi(Phi^{-1}(p_home) + runline / sigma)
    """
    phiv = np.vectorize(_phi)
    piov = np.vectorize(_phi_inv)
    return phiv(piov(p_home) + runline / sigma)


def _american_to_implied(ml: float) -> float:
    """American odds -> implied probability (includes vig)."""
    ml = float(ml)
    return (-ml) / (-ml + 100.0) if ml < 0 else 100.0 / (ml + 100.0)


def _ece_bins(p: np.ndarray, y: np.ndarray, n_bins: int) -> List[Dict]:
    """Quantile-bin calibration table."""
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
            "n": int(mask.sum()),
            "pred_cover_rate": round(mean_p, 4),
            "actual_cover_rate": round(actual, 4),
            "gap": round(mean_p - actual, 4),
        })
    return bins_out


def run(corpus: Optional[Path] = None) -> Dict:
    """Compute MLB run-line cover-rate calibration gate. Returns a result dict."""
    import pandas as pd
    games_path, odds_path = _resolve(corpus)
    if not games_path.is_file() or not odds_path.is_file():
        return {"status": "missing_data",
                "note": "games.parquet or odds.parquet not found"}

    games = pd.read_parquet(games_path)
    games["date"] = pd.to_datetime(games["date"])
    games = games.sort_values(
        ["date", "game_seq", "event_id"]).reset_index(drop=True)
    games["home_margin"] = (games["home_runs"].astype(float)
                            - games["away_runs"].astype(float))

    # walk-forward Elo (leak-free, reuses beat_the_close_ml engine)
    games["p_home_elo"] = _walk_forward_elo(games)

    odds = pd.read_parquet(odds_path)
    odds = odds.dropna(subset=["runline", "runline_odds"])
    odds = odds[["event_id", "runline", "runline_odds"]].copy()

    m = (games.merge(odds, on="event_id", how="inner")
         .sort_values(["date", "game_seq", "event_id"])
         .reset_index(drop=True))
    n = len(m)
    if n < _MIN_HOLDOUT:
        return {"status": "data_limited", "n_overlap": n,
                "note": f"Only {n} rows with runline overlap; need >= {_MIN_HOLDOUT}."}

    # home covers if home_margin > -runline
    m["home_covers"] = (m["home_margin"] > -m["runline"]).astype(float)

    # model cover prob: P(margin > -runline) via Elo mu + Normal tail
    m["p_model_cover"] = _model_cover_prob(
        m["p_home_elo"].to_numpy(),
        m["runline"].to_numpy(),
        _SIGMA_RUNS,
    )

    # market-implied cover prob from runline_odds (with vig; used as calibration baseline)
    m["p_mkt_cover"] = m["runline_odds"].map(_american_to_implied)

    mid = n // 2
    te = m.iloc[mid:].copy().reset_index(drop=True)
    n_holdout = len(te)

    p_model = te["p_model_cover"].to_numpy()
    p_mkt = te["p_mkt_cover"].to_numpy()
    y = te["home_covers"].to_numpy()

    model_ece = float(ece(p_model, y))
    market_ece = float(ece(p_mkt, y))
    model_passed = model_ece < _ECE_TARGET
    market_passed = market_ece < _ECE_TARGET

    model_bins = _ece_bins(p_model, y, _N_BINS)
    market_bins = _ece_bins(p_mkt, y, _N_BINS)

    if model_passed and market_passed:
        verdict = (f"PASS: model ECE {model_ece:.4f} and market ECE {market_ece:.4f} "
                   f"both < target {_ECE_TARGET} (n_holdout={n_holdout}).")
    else:
        failing = []
        if not model_passed:
            failing.append(f"model ECE {model_ece:.4f}")
        if not market_passed:
            failing.append(f"market ECE {market_ece:.4f}")
        verdict = (f"CALIBRATION_GAP: {'; '.join(failing)} >= target {_ECE_TARGET}. "
                   f"Run-line cover-rate calibration needs improvement.")

    return {
        "status": "ok",
        "n_overlap": n,
        "n_holdout": n_holdout,
        "model_ece": round(model_ece, 4),
        "market_ece": round(market_ece, 4),
        "ece_target": _ECE_TARGET,
        "model_passed": model_passed,
        "market_passed": market_passed,
        "sigma_runs": _SIGMA_RUNS,
        "actual_cover_rate": round(float(y.mean()), 4),
        "model_bins": model_bins,
        "market_bins": market_bins,
        "verdict": verdict,
        "note": ("MLB run-line cover-rate calibration (pa6). "
                 "Elo P(home win) -> Normal-tail cover prob vs realized covers. "
                 "Market-implied prob (with vig) also graded. "
                 "ECE target is 0.10. Calibration only -- no $ edge claimed."),
    }


def _main() -> int:
    rep = run()
    status = rep.get("status")
    if status != "ok":
        print(f"{status}: {rep.get('note', '')}"); return 0
    print(f"=== MLB run-line cover-rate calibration "
          f"(n={rep['n_overlap']}, holdout={rep['n_holdout']}) ===")
    print(f"  sigma_runs={rep['sigma_runs']}  |  "
          f"actual cover rate (holdout)={rep['actual_cover_rate']}")
    print(f"\n  --- Model (Elo-based) ---")
    print(f"  {'bin':>4}  {'pred_cover':>10}  {'actual_cover':>12}  {'gap':>7}  {'n':>5}")
    for b in rep["model_bins"]:
        print(f"  {b['bin']:>4}  {b['pred_cover_rate']:>10.4f}  "
              f"{b['actual_cover_rate']:>12.4f}  {b['gap']:>+7.4f}  {b['n']:>5}")
    print(f"\n  model ECE={rep['model_ece']}  target={rep['ece_target']}  "
          f"passed={rep['model_passed']}")
    print(f"\n  --- Market (runline_odds implied) ---")
    for b in rep["market_bins"]:
        print(f"  {b['bin']:>4}  {b['pred_cover_rate']:>10.4f}  "
              f"{b['actual_cover_rate']:>12.4f}  {b['gap']:>+7.4f}  {b['n']:>5}")
    print(f"\n  market ECE={rep['market_ece']}  target={rep['ece_target']}  "
          f"passed={rep['market_passed']}")
    print(f"\nVERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
