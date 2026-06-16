"""scripts.platformkit.proof_soccer.beat_the_close_ou — soccer O/U-2.5: match the close?

Runs the beat-the-close test on the soccer Over/Under 2.5 goals market. Our leak-free
walk-forward forecaster (EW Poisson attack/defense ratings -> finishing-residual shrink
prior -> bivariate-Poisson scoreline engine -> P(over 2.5)) is compared, after a leak-free
pooled Platt recalibration (fit on the FIRST half, applied to the second), against the
devigged Pinnacle CLOSING O/U-2.5 price, scored on Brier over the held-out second half.

"Beat the best prediction" = lower Brier than the devigged close on the SAME real outcomes.
Pinnacle is sharp and soccer pregame markets are efficient, so MATCHING the close (within
sampling noise) is the realistic best case; BEHIND (~0.02 Brier) is the expected honest result.
No $ edge claimed.

Leak-free:
  - Ratings/finishing-prior emit a STRICTLY pre-match snapshot, updated only AFTER the snapshot.
  - The pooled Platt recalibrator is FIT on the first chronological half and APPLIED to the
    held-out second half only.
  - The closing line is a market datum used ONLY as the comparison forecaster, never a model input.
INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_soccer.beat_the_close_ou
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pandas as pd  # noqa: E402

from domains.soccer.finishing_prior import walk_forward_finishing_prior  # noqa: E402

_MATCHES = _REPO / "data/domains/soccer/matches.parquet"
_STATS = _REPO / "data/domains/soccer/match_stats.parquet"
_ODDS = _REPO / "data/domains/soccer/odds.parquet"


def _corpus_from_env() -> Optional[Path]:
    """Return $PROOF_CORPUS_ROOT/soccer if the env var is set, else None.

    Shared corpus-override contract: the scoreboard sets PROOF_CORPUS_ROOT before
    calling run() with no args; setting it must make every proof read the tiny
    committed fixtures under tests/fixtures/proof/soccer/.
    """
    root = os.environ.get("PROOF_CORPUS_ROOT")
    return Path(root) / "soccer" if root else None


def _paths(corpus: Optional[Path]) -> Tuple[Path, Path, Path]:
    """Resolve (matches, stats, odds) paths by precedence:
    explicit corpus arg > $PROOF_CORPUS_ROOT/soccer > real data/domains default."""
    root = corpus or _corpus_from_env()
    if root is not None:
        return (root / "matches.parquet", root / "match_stats.parquet",
                root / "odds.parquet")
    return _MATCHES, _STATS, _ODDS


def devig_two_way(odds_a: np.ndarray, odds_b: np.ndarray) -> np.ndarray:
    """Decimal two-way odds -> devigged P(side a).  imp = 1/odds; p = imp_a/(imp_a+imp_b)."""
    imp_a = 1.0 / odds_a
    imp_b = 1.0 / odds_b
    return imp_a / (imp_a + imp_b)


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(np.mean((p - y) ** 2))


def _fit_platt(p: np.ndarray, y: np.ndarray, iters: int = 400, lr: float = 0.5) -> Tuple[float, float]:
    """Fit Platt scaling a,b on logit(p) via gradient descent on log-loss (no sklearn dep)."""
    eps = 1e-6
    z = np.log(np.clip(p, eps, 1 - eps) / np.clip(1 - p, eps, 1 - eps))  # logit(p)
    a, b = 1.0, 0.0
    n = len(z)
    for _ in range(iters):
        q = 1.0 / (1.0 + np.exp(-(a * z + b)))
        g = q - y
        ga = float(np.mean(g * z))
        gb = float(np.mean(g))
        a -= lr * ga
        b -= lr * gb
    return a, b


def _apply_platt(p: np.ndarray, a: float, b: float) -> np.ndarray:
    eps = 1e-6
    z = np.log(np.clip(p, eps, 1 - eps) / np.clip(1 - p, eps, 1 - eps))
    return 1.0 / (1.0 + np.exp(-(a * z + b)))


def _build_model_forecast(matches_path: Path, stats_path: Path) -> pd.DataFrame:
    """Walk-forward composed forecaster: ratings -> finishing prior -> scoreline engine.

    Returns a DataFrame with event_id, date, p_over25 (the finishing-adjusted engine prob),
    and the realized over-2.5 target.  All probabilities are STRICTLY pre-match (leak-free).
    """
    matches = pd.read_parquet(matches_path)
    stats = pd.read_parquet(stats_path)
    wf = walk_forward_finishing_prior(matches, stats, rho=0.0)
    # p_over25_adj = finishing-residual-shrunk lambdas through the bivariate-Poisson engine.
    wf = wf.copy()
    if "target_over25" not in wf.columns:
        wf["target_over25"] = ((wf["fthg"] + wf["ftag"]) >= 3).astype(float)
    wf = wf[wf["target_over25"].notna()].copy()
    wf["p_model_raw"] = wf["p_over25_adj"].astype(float)
    return wf[["event_id", "date", "p_model_raw", "target_over25"]]


def run(corpus: Optional[Path] = None) -> Dict:
    matches_path, stats_path, odds_path = _paths(corpus)
    if not (matches_path.exists() and odds_path.exists()):
        return {"status": "data_missing", "n": 0}

    model = _build_model_forecast(matches_path, stats_path)

    odds = pd.read_parquet(odds_path)
    # Pinnacle CLOSE O/U 2.5 (pc_over / pc_under = decimal closing odds).
    odds = odds.dropna(subset=["pc_over", "pc_under"]).copy()
    odds = odds[(odds["pc_over"] > 1.0) & (odds["pc_under"] > 1.0)]
    odds["p_close"] = devig_two_way(odds["pc_over"].to_numpy(float),
                                    odds["pc_under"].to_numpy(float))

    m = model.merge(odds[["event_id", "p_close"]], on="event_id", how="inner")
    m["date"] = pd.to_datetime(m["date"])
    m = m.sort_values("date", kind="mergesort").reset_index(drop=True)
    m = m.dropna(subset=["p_model_raw", "p_close", "target_over25"]).reset_index(drop=True)
    n = len(m)
    if n < 200:
        return {"status": "data_limited", "n": n}

    y = m["target_over25"].to_numpy(float)
    p_raw = m["p_model_raw"].to_numpy(float)
    p_close = m["p_close"].to_numpy(float)

    # Chronological split: fit Platt on the first half, evaluate on the held-out second half.
    mid = n // 2
    tr = slice(0, mid)
    te = slice(mid, n)

    a, b = _fit_platt(p_raw[tr], y[tr])
    p_cal = _apply_platt(p_raw, a, b)

    b_model = _brier(p_cal[te], y[te])
    b_close = _brier(p_close[te], y[te])
    b_model_raw = _brier(p_raw[te], y[te])
    gap = round(b_model - b_close, 4)  # >0 => market sharper

    if gap < -0.002:
        verdict = (f"OUR model BEATS the close on Brier ({round(b_model, 4)} vs "
                   f"{round(b_close, 4)})")
    elif gap <= 0.012:
        verdict = (f"OUR model MATCHES the close (Brier {round(b_model, 4)} vs "
                   f"{round(b_close, 4)}, gap {gap:+})")
    else:
        verdict = (f"close sharper by {gap} Brier — Pinnacle O/U-2.5 is efficient "
                   f"(freshness/sharp-money edge we don't capture pregame)")

    return {
        "status": "ok",
        "n": n,
        "n_holdout": n - mid,
        "model_brier": round(b_model, 4),
        "model_brier_uncalibrated": round(b_model_raw, 4),
        "close_brier": round(b_close, 4),
        "gap": gap,
        "platt_a": round(a, 4),
        "platt_b": round(b, 4),
        "base_rate_over25": round(float(np.mean(y[te])), 4),
        "verdict": verdict,
        "note": ("Composed walk-forward forecaster (EW Poisson ratings -> finishing-residual "
                 "shrink -> bivariate-Poisson engine) + leak-free pooled Platt (fit first half, "
                 "applied second) vs the devigged Pinnacle close. No $ edge claimed."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n={rep.get('n')}")
        return 0
    print(f"=== Soccer O/U-2.5: OUR composed forecaster vs the devigged Pinnacle close "
          f"(n={rep['n']}, holdout={rep['n_holdout']}) ===")
    print(f"  {'predictor':>22}  {'Brier':>8}")
    print(f"  {'devig Pinnacle close':>22}  {rep['close_brier']:>8}")
    print(f"  {'our model (Platt cal)':>22}  {rep['model_brier']:>8}")
    print(f"  {'our model (raw)':>22}  {rep['model_brier_uncalibrated']:>8}")
    print(f"\nPlatt: a={rep['platt_a']} b={rep['platt_b']}  |  "
          f"base-rate(over)={rep['base_rate_over25']}  |  Brier gap to close: {rep['gap']:+}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
