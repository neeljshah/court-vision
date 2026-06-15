"""domains.mlb.negbinom_engine — Over-dispersed (NegBinom) MLB run marginal engine.

MOTIVATION: MLB runs are lumpy. Independent-Poisson understates tail variance →
O/U and run-line tail probs are mis-calibrated. Fix: Negative-Binomial marginal
with the SAME mean (lambda) but fitted dispersion r > 0.

NegBinom: nbinom(n=r, p=r/(r+lam)) → mean=lam, var=lam+lam²/r. As r→∞, →Poisson.
ADDITIVE ONLY: does NOT touch inning_engine.py or any other existing file.
HONEST: accuracy/calibration only — NO edge claimed.
<=300 lines (wc -l domains/mlb/negbinom_engine.py).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.stats import nbinom

_MAX_RUNS_DEFAULT = 25
_TOTAL_LINES: Tuple[float, ...] = (6.5, 7.5, 8.5, 9.5, 10.5)
_MIN_R = 0.5       # floor on dispersion to avoid degenerate PMFs
_FALLBACK_R = 4.0  # default when fewer than 10 observations
_UNDERDISP_R = 1e6  # ~Poisson: returned when sample is under-dispersed (var<=mu)


# --- PMFs -------------------------------------------------------------------

def _negbinom_pmf(lam: float, r: float, max_k: int) -> np.ndarray:
    """NegBinom PMF P(X=k) for k=0..max_k; renormalized to sum=1."""
    if lam <= 0:
        raise ValueError(f"lam must be > 0; got {lam}")
    if r <= 0:
        raise ValueError(f"r must be > 0; got {r}")
    p = r / (r + lam)
    pmf = nbinom.pmf(np.arange(max_k + 1, dtype=np.int64), n=r, p=p).astype(float)
    s = pmf.sum()
    if s > 0:
        pmf /= s
    return pmf


def _poisson_pmf(lam: float, max_k: int) -> np.ndarray:
    """Poisson PMF (local copy; does NOT import from inning_engine)."""
    k = np.arange(max_k + 1, dtype=float)
    lf = np.zeros(max_k + 1, dtype=float)
    for i in range(1, max_k + 1):
        lf[i] = lf[i - 1] + math.log(i)
    pmf = np.exp(-lam + k * math.log(max(lam, 1e-12)) - lf)
    s = pmf.sum()
    if s > 0:
        pmf /= s
    return pmf


# --- Dispersion estimation (Method of Moments, leak-free) -------------------

def fit_r_mom(runs: np.ndarray) -> float:
    """MoM dispersion: r = mean²/(variance-mean). Returns _FALLBACK_R if <10 obs.

    When the sample is UNDER-dispersed vs Poisson (var<=mu) the MoM estimate of
    over-dispersion is undefined / negative. NegBinom cannot represent under-dispersion,
    so we collapse toward Poisson by returning a LARGE r (_UNDERDISP_R, var→lam as r→∞).
    Returning the _MIN_R floor here would be the WRONG direction (maximal over-dispersion).
    """
    if len(runs) < 10:
        return _FALLBACK_R
    mu = float(np.mean(runs))
    if mu <= 0:
        return _FALLBACK_R
    var = float(np.var(runs, ddof=1))
    if var <= mu:
        return _UNDERDISP_R  # under-dispersed: nearest NegBinom is ~Poisson (large r)
    return max(mu ** 2 / (var - mu), _MIN_R)


def fit_dispersion_first_half(games_df) -> Tuple[float, float, int]:
    """Fit r_home, r_away on the FIRST 50% of corpus (date-sorted).

    Leak-free: val games at indices [n_train:] never touch train fit.
    Returns (r_home, r_away, n_train).
    """
    df = games_df.sort_values("date").reset_index(drop=True)
    mid = len(df) // 2
    train = df.iloc[:mid]
    return fit_r_mom(train["home_runs"].values), fit_r_mom(train["away_runs"].values), mid


# --- Score matrices ---------------------------------------------------------

def runs_matrix_nb(
    lam_home: float, lam_away: float, r_home: float, r_away: float,
    *, max_runs: int = _MAX_RUNS_DEFAULT,
) -> np.ndarray:
    """Independent-NegBinom joint P[i,j]=P(home=i,away=j). Renormalized.

    HONESTY NOTE: callers that scale the remaining-innings lambda (e.g. the repricer)
    scale lambda, NOT r -- thinning NB(r,lam) by a fraction f is not exactly NB(r, lam*f),
    so the partial-inning tail shape is approximate.
    """
    if lam_home <= 0 or lam_away <= 0:
        raise ValueError(f"lambdas must be positive; got {lam_home}, {lam_away}")
    P = np.outer(_negbinom_pmf(lam_home, r_home, max_runs),
                 _negbinom_pmf(lam_away, r_away, max_runs))
    s = P.sum()
    if s > 0:
        P /= s
    return P


def runs_matrix_poisson(
    lam_home: float, lam_away: float,
    *, max_runs: int = _MAX_RUNS_DEFAULT,
) -> np.ndarray:
    """Poisson joint matrix (same-mean baseline for comparison). Renormalized."""
    if lam_home <= 0 or lam_away <= 0:
        raise ValueError(f"lambdas must be positive; got {lam_home}, {lam_away}")
    P = np.outer(_poisson_pmf(lam_home, max_runs), _poisson_pmf(lam_away, max_runs))
    s = P.sum()
    if s > 0:
        P /= s
    return P


# --- Market surface ---------------------------------------------------------

def _total_dist(P: np.ndarray) -> np.ndarray:
    """Marginal total-runs distribution from joint matrix."""
    n = P.shape[0]
    d = np.zeros(2 * n - 1, dtype=float)
    for i in range(n):
        for j in range(n):
            d[i + j] += P[i, j]
    return d


def markets_from_matrix_nb(
    P: np.ndarray, *, total_lines: Sequence[float] = _TOTAL_LINES,
) -> Dict[str, float]:
    """O/U + run-line surface. Keys: ml_home/ml_away, rl_home_minus15/rl_away_plus15,
    over_N/under_N for N in total_lines."""
    n = P.shape[0]
    ri, ci = np.arange(n)[:, None], np.arange(n)[None, :]
    ph = float(P[ri > ci].sum())
    pa = float(P[ri < ci].sum())
    pt = float(P[ri == ci].sum())
    out: Dict[str, float] = {
        "ml_home": ph + 0.5 * pt,
        "ml_away": pa + 0.5 * pt,
        "rl_home_minus15": float(P[ri >= ci + 2].sum()),
    }
    out["rl_away_plus15"] = 1.0 - out["rl_home_minus15"]
    d = _total_dist(P)
    for line in total_lines:
        # CONTRACT: lines are X.5 (half-integer), the only shape every caller passes
        # (_TOTAL_LINES + predictor/repricer). For a half-integer line there is no push
        # bucket, so over = P(total >= ceil(line)) and over+under == 1 exactly.
        # For an INTEGER line, total==line is a PUSH: it must be EXCLUDED from over so
        # that over + push + under == 1 (the old int(line+0.5) silently folded the push
        # into over). We compute the push explicitly and report under as the remainder.
        cutoff = int(math.ceil(line))           # first total strictly above an integer line
        po = float(d[cutoff:].sum())            # P(total > line)
        is_half = (line != math.floor(line))    # True for X.5 lines (no push)
        push = 0.0 if is_half else float(d[int(round(line))])
        out[f"over_{line:g}"] = po
        out[f"under_{line:g}"] = 1.0 - po - push
        if not is_half:
            out[f"push_{line:g}"] = push
    return out


# --- Validation utilities ---------------------------------------------------

def brier_score(probs: List[float], outcomes: List[float]) -> float:
    """Mean Brier score."""
    p, o = np.array(probs, dtype=float), np.array(outcomes, dtype=float)
    return float(np.mean((p - o) ** 2))


def _tail_coverage(probs: np.ndarray, outcomes: np.ndarray) -> Dict[str, float]:
    """Calibration in extreme buckets: p<0.10 (low) and p>0.90 (high)."""
    out: Dict[str, float] = {}
    for lo, hi, label in [(0.0, 0.10, "low"), (0.90, 1.01, "high")]:
        mask = (probs >= lo) & (probs < hi)
        n = int(mask.sum())
        out[f"tail_{label}_n"] = n
        out[f"tail_{label}_pred"] = float(probs[mask].mean()) if n >= 5 else float("nan")
        out[f"tail_{label}_realized"] = float(outcomes[mask].mean()) if n >= 5 else float("nan")
    return out


# --- End-to-end validation --------------------------------------------------

def run_validation(
    games_path: Optional[str] = None,
    *, repo_root: Optional[Path] = None,
    total_lines: Sequence[float] = _TOTAL_LINES,
) -> Dict:
    """Walk-forward Poisson vs NegBinom O/U + run-line comparison.

    Dispersion r fitted on first 50% of sorted corpus → applied to second 50%.
    LEAK-FREE: no future data in r estimate. NO edge claimed.
    """
    import pandas as pd
    from domains.mlb.inning_engine import RunRateState

    if games_path is not None:
        df = pd.read_parquet(games_path)
    else:
        root = repo_root or Path(__file__).resolve().parents[2]
        path = root / "data" / "domains" / "mlb" / "games.parquet"
        if not path.exists():
            raise FileNotFoundError(f"MLB corpus not found at {path}")
        df = pd.read_parquet(path)

    df = df.sort_values("date").reset_index(drop=True)
    r_home, r_away, n_train = fit_dispersion_first_half(df)

    # Walk-forward lambdas (read-only import from inning_engine)
    rr = RunRateState()
    lam_homes: List[float] = []
    lam_aways: List[float] = []
    for i in range(len(df)):
        home, away = str(df["home_team"].iloc[i]), str(df["away_team"].iloc[i])
        season = int(df["season"].iloc[i])
        hr, ar = float(df["home_runs"].iloc[i]), float(df["away_runs"].iloc[i])
        lh, la = rr.snapshot(home, away, season)
        lam_homes.append(lh)
        lam_aways.append(la)
        rr.update(home, away, hr, ar)

    df = df.copy()
    df["lam_home"] = lam_homes
    df["lam_away"] = lam_aways

    val = df.iloc[n_train:].copy()
    assert (val.index >= n_train).all(), "Leak: val indices overlap train"

    keys = [f"over_{l:g}" for l in total_lines] + ["rl_home_minus15"]
    results_nb: Dict[str, List[float]] = {k: [] for k in keys}
    results_po: Dict[str, List[float]] = {k: [] for k in keys}
    total_runs_act: List[float] = []
    rl_act: List[float] = []

    for _, row in val.iterrows():
        lh, la = float(row["lam_home"]), float(row["lam_away"])
        hr, ar = float(row["home_runs"]), float(row["away_runs"])
        total_runs_act.append(hr + ar)
        rl_act.append(1.0 if hr >= ar + 2 else 0.0)
        P_nb = runs_matrix_nb(lh, la, r_home, r_away)
        P_po = runs_matrix_poisson(lh, la)
        mkts_nb = markets_from_matrix_nb(P_nb, total_lines=total_lines)
        mkts_po = markets_from_matrix_nb(P_po, total_lines=total_lines)
        for k in keys:
            results_nb[k].append(mkts_nb[k])
            results_po[k].append(mkts_po[k])

    tot = np.array(total_runs_act)
    ou_brier: Dict[str, Dict] = {}
    for line in total_lines:
        key = f"over_{line:g}"
        act = (tot > line).astype(float)
        nb_p, po_p = np.array(results_nb[key]), np.array(results_po[key])
        ou_brier[key] = {
            "brier_negbinom": brier_score(nb_p.tolist(), act.tolist()),
            "brier_poisson":  brier_score(po_p.tolist(), act.tolist()),
            "delta_brier":    brier_score(nb_p.tolist(), act.tolist())
                              - brier_score(po_p.tolist(), act.tolist()),
            "tail_nb": _tail_coverage(nb_p, act),
            "tail_po": _tail_coverage(po_p, act),
        }

    rl_a = np.array(rl_act)
    nb_rl, po_rl = np.array(results_nb["rl_home_minus15"]), np.array(results_po["rl_home_minus15"])
    return {
        "n_train": n_train, "n_val": len(val),
        "r_home": r_home, "r_away": r_away,
        "ou_brier": ou_brier,
        "run_line": {
            "brier_negbinom": brier_score(nb_rl.tolist(), rl_a.tolist()),
            "brier_poisson":  brier_score(po_rl.tolist(), rl_a.tolist()),
            "delta_brier":    brier_score(nb_rl.tolist(), rl_a.tolist())
                              - brier_score(po_rl.tolist(), rl_a.tolist()),
            "tail_nb": _tail_coverage(nb_rl, rl_a),
            "tail_po": _tail_coverage(po_rl, rl_a),
        },
        "note": (
            "HONEST: r fitted on first 50% only (leak-free). "
            "Win expected in tail calibration; mean-preserving by design. NO edge claimed."
        ),
    }
