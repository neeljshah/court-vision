"""domains.soccer.scoreline_engine — Dixon-Coles bivariate-Poisson scoreline engine.

Turns pre-match Poisson lambdas into a full joint goals matrix and prices every
market: 1X2, O/U 0.5–4.5, BTTS, top correct scores.

HONEST: value = coherent full surface (1X2/BTTS/correct-score unavailable from the
scalar Poisson baseline).  At rho=0 engine_over25 == closed-form baseline to 1e-6
(correctness anchor, tested).  Calibration parity expected.  NO edge claimed.

INVARIANTS: never edit src/ or kernel/; imports are read-only; <=300 LOC.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from domains.soccer.ratings import _p_over, walk_forward_goals  # read-only

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_GOALS_DEFAULT = 12   # inclusive 13x13 grid. scoreline_matrix renormalises (P/=P.sum()),
                          # so any truncated tail mass is benignly redistributed for markets.
                          # RATE_CLIP lets lam_total reach ~8.0; closed-form O/U parity to <1e-6
                          # at high lambda would need max_goals>=25 (override via the kwarg).
_OU_LINES: Tuple[float, ...] = (0.5, 1.5, 2.5, 3.5, 4.5)


# ---------------------------------------------------------------------------
# Core: scoreline probability matrix
# ---------------------------------------------------------------------------

def scoreline_matrix(
    lam_home: float,
    lam_away: float,
    *,
    rho: float = 0.0,
    max_goals: int = _MAX_GOALS_DEFAULT,
) -> np.ndarray:
    """Bivariate-Poisson scoreline matrix with Dixon-Coles low-score correction.

    P[i, j] = P(home=i goals, away=j goals), shape (max_goals+1, max_goals+1).
    Renormalised to sum=1 to correct for truncation.

    Algorithm:
      1. Independent Poisson outer product P_ind[i,j] = Pois(i;lam_h)*Pois(j;lam_a).
      2. DC tau correction on (0,0),(0,1),(1,0),(1,1) — standard Dixon-Coles (1997):
           tau_00 = 1 - lam_h*lam_a*rho   tau_01 = 1 + lam_h*rho
           tau_10 = 1 + lam_a*rho          tau_11 = 1 - rho
         rho=0 => all taus=1 (no-op; pure independent Poisson).
      3. Renormalise P /= P.sum().

    rho<0 inflates 0-0 and 1-1 relative to independence (typical for soccer).
    """
    if lam_home <= 0 or lam_away <= 0:
        raise ValueError(f"lambdas must be positive; got lam_home={lam_home}, lam_away={lam_away}")

    n = max_goals + 1

    # Step 1 — log-space Poisson PMF for numerical stability
    goals = np.arange(n, dtype=float)
    log_fact = np.array(
        [sum(math.log(k) for k in range(1, i + 1)) for i in range(n)], dtype=float
    )
    pois_h = np.exp(-lam_home + goals * math.log(lam_home) - log_fact)
    pois_a = np.exp(-lam_away + goals * math.log(lam_away) - log_fact)
    P = np.outer(pois_h, pois_a)

    # Step 2 — DC tau correction (skipped entirely at rho=0)
    if rho != 0.0:
        P[0, 0] *= 1.0 - lam_home * lam_away * rho
        P[0, 1] *= 1.0 + lam_home * rho
        P[1, 0] *= 1.0 + lam_away * rho
        P[1, 1] *= 1.0 - rho

    # Step 3 — renormalise
    total = P.sum()
    if total > 0:
        P /= total
    return P


# ---------------------------------------------------------------------------
# Market read-offs
# ---------------------------------------------------------------------------

def _total_dist(P: np.ndarray) -> np.ndarray:
    """Total-goals marginal: out[t] = sum of P over all (i, j) with i + j == t.

    Each anti-diagonal of P holds a fixed total t = i + j, so the marginal is the
    vector of anti-diagonal sums (length 2n-1).  Equivalent to the naive double
    loop ``out[i + j] += P[i, j]`` but vectorised via np.trace over offsets.
    """
    n = P.shape[0]
    Pf = np.fliplr(P)  # anti-diagonal i+j==t maps to a diagonal of the flipped matrix
    return np.array([np.trace(Pf, offset=k) for k in range(n - 1, -n, -1)], dtype=float)


def markets_from_matrix(P: np.ndarray, *, top_n: int = 8) -> Dict[str, float]:
    """Full market surface from a scoreline matrix.

    Returns dict with keys:
      '1X2_home', '1X2_draw', '1X2_away'     (sum to 1.0)
      'over_N', 'under_N' for N in {0.5,1.5,2.5,3.5,4.5}
      'btts_yes', 'btts_no'                   (sum to 1.0)
      'cs_{i}_{j}' for top_n most-probable correct scores
    """
    n = P.shape[0]
    row_idx = np.arange(n)[:, None]
    col_idx = np.arange(n)[None, :]

    out: Dict[str, float] = {
        "1X2_home": float(P[row_idx > col_idx].sum()),
        "1X2_draw": float(P[row_idx == col_idx].sum()),
        "1X2_away": float(P[row_idx < col_idx].sum()),
    }

    # O/U lines — build total-goals marginal distribution first
    total_dist = _total_dist(P)

    for line in _OU_LINES:
        threshold = int(line + 0.5)  # e.g. 2.5 -> 3
        p_over = float(total_dist[threshold:].sum())
        out[f"over_{line:g}"] = p_over
        out[f"under_{line:g}"] = 1.0 - p_over

    # BTTS via inclusion-exclusion: P(h>=1, a>=1) = 1 - P(h=0) - P(a=0) + P(0,0)
    p_btts = float(1.0 - P[0, :].sum() - P[:, 0].sum() + P[0, 0])
    out["btts_yes"] = max(0.0, p_btts)
    out["btts_no"] = 1.0 - out["btts_yes"]

    # Top correct scores
    for flat_i in np.argsort(P.ravel())[::-1][:top_n]:
        hi, ai = divmod(int(flat_i), n)
        out[f"cs_{hi}_{ai}"] = float(P[hi, ai])

    return out


# ---------------------------------------------------------------------------
# Convenience: engine O/U 2.5 probability
# ---------------------------------------------------------------------------

def engine_over25(
    lam_home: float,
    lam_away: float,
    rho: float = 0.0,
    *,
    max_goals: int = _MAX_GOALS_DEFAULT,
) -> float:
    """P(total goals >= 3) via the scoreline matrix.  At rho=0 equals _p_over(lam_h+lam_a)."""
    P = scoreline_matrix(lam_home, lam_away, rho=rho, max_goals=max_goals)
    return float(_total_dist(P)[3:].sum())


# ---------------------------------------------------------------------------
# Walk-forward validation against real corpus
# ---------------------------------------------------------------------------

def build_engine_forecast(
    seasons: Optional[Sequence[int]] = None,
    rho: float = 0.0,
    *,
    repo_root: Optional[Path] = None,
    matches_path: Optional[str] = None,
) -> Dict:
    """Walk-forward over the soccer corpus; score engine over2.5 vs Poisson baseline.

    Returns dict:
        n, baseline:{brier,ece,log_loss}, engine:{brier,ece,log_loss},
        dBrier (engine - baseline; ~0 expected at rho=0),
        dECE, rho, note, sample_surface (full market dict for the last corpus match).
    """
    from scripts.platformkit.scoreboard import score_forecaster

    import pandas as pd
    if matches_path is not None:
        matches_df = pd.read_parquet(matches_path)
    else:
        root = repo_root or Path(__file__).resolve().parents[2]
        path = root / "data" / "domains" / "soccer" / "matches.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Soccer matches corpus not found at {path}")
        matches_df = pd.read_parquet(path)

    if seasons:
        matches_df = matches_df[matches_df["season"].isin(seasons)]

    wf = walk_forward_goals(matches_df)

    if "target_over25" not in wf.columns:
        raise ValueError("matches.parquet must have 'target_over25' column")

    wf_valid = wf[wf["target_over25"].notna()].copy()
    targets: List[float] = wf_valid["target_over25"].astype(float).tolist()
    baseline_probs: List[float] = []
    engine_probs: List[float] = []
    last_P: Optional[np.ndarray] = None
    last_row = None

    for _, row in wf_valid.iterrows():
        lh, la = float(row["lam_home"]), float(row["lam_away"])
        baseline_probs.append(float(row["p_over25"]))
        engine_probs.append(engine_over25(lh, la, rho=rho))
        last_P = scoreline_matrix(lh, la, rho=rho)
        last_row = row

    base_s = score_forecaster(baseline_probs, targets)
    eng_s = score_forecaster(engine_probs, targets)

    sample_surface: Optional[Dict] = None
    if last_P is not None and last_row is not None:
        sample_surface = markets_from_matrix(last_P)
        sample_surface["_match"] = (
            f"{last_row.get('home_team','?')} vs {last_row.get('away_team','?')}"
            f" (lam_h={float(last_row['lam_home']):.3f},"
            f" lam_a={float(last_row['lam_away']):.3f})"
        )

    return {
        "n": base_s["n"],
        "baseline": {k: base_s[k] for k in ("brier", "ece", "log_loss")},
        "engine":   {k: eng_s[k]  for k in ("brier", "ece", "log_loss")},
        "dBrier": eng_s["brier"] - base_s["brier"],
        "dECE":   eng_s["ece"]   - base_s["ece"],
        "rho": rho,
        "note": (
            "HONEST: engine value = coherent full surface (1X2/BTTS/correct-score); "
            "over2.5 calibration parity expected (rho=0 algebraically == baseline); "
            "NO edge claimed; gate decides signal merit."
        ),
        "sample_surface": sample_surface,
    }
