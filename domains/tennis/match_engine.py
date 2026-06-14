"""domains.tennis.match_engine — Point-by-point tennis match simulation engine.

Turns per-point serve-win probabilities into a coherent full market surface:
match win, set betting, total games O/U, straight-sets / correct-set scores.

HONEST: engine ADDS market coverage (set/games/straight-sets). Match-win
calibration == Elo baseline by construction (serve_probs_from_winprob bisects
so simulated match-win ≈ Elo target). PARITY is the win. NO edge claimed.

INVARIANTS: never edit src/ or kernel/; <=300 LOC.
"""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.sim_framework import JointDistribution  # read-only

_BASE_HOLD_PROB: float = 0.62   # typical ATP serve-hold rate
_BISECT_TOL: float = 1e-6
_BISECT_MAX_ITER: int = 60
_N_SIMS_DEFAULT: int = 3000


# ---------------------------------------------------------------------------
# 1. Analytic game-win probability (standard deuce-corrected closed form)
# ---------------------------------------------------------------------------

def game_win_prob(p_serve: float) -> float:
    """P(server wins game) for per-point serve-win prob p_serve (deuce model).

    Exact closed form (Barnett & Clarke 2005):
      P_hold = P(win, no-deuce) + P(reach 3-3) * p^2 / (p^2 + q^2)
    """
    if not (0.0 <= p_serve <= 1.0):
        raise ValueError(f"p_serve must be in [0,1]; got {p_serve}")
    p, q = p_serve, 1.0 - p_serve
    p4, q4 = p ** 4, q ** 4
    pw_nd = p4 * (1.0 + 4.0 * q + 10.0 * q ** 2)   # P(win at 4-0, 4-1, 4-2)
    p_rd = math.comb(6, 3) * (p ** 3) * (q ** 3)     # P(reach 3-3 deuce)
    denom = p ** 2 + q ** 2
    p_win_deuce = (p ** 2) / denom if denom > 1e-15 else 0.5
    return float(pw_nd + p_rd * p_win_deuce)


# ---------------------------------------------------------------------------
# 2. Monte Carlo: simulate n_sims matches -> (n_sims, 3): sets_p1, sets_p2, games
# ---------------------------------------------------------------------------

def _sim_matches(
    ph1: float, ph2: float, best_of: int, n_sims: int, rng: np.random.Generator,
) -> np.ndarray:
    """Returns (n_sims, 3): [sets_p1, sets_p2, total_games]."""
    stw = (best_of + 1) // 2   # sets to win
    res = np.zeros((n_sims, 3), dtype=np.int32)
    for i in range(n_sims):
        s1 = s2 = tg = 0
        srv = 0  # 0=p1 serves, alternates each game
        while s1 < stw and s2 < stw:
            g1 = g2 = 0
            while True:
                held = rng.random() < (ph1 if srv == 0 else ph2)
                if held:
                    if srv == 0: g1 += 1
                    else:        g2 += 1
                else:
                    if srv == 0: g2 += 1
                    else:        g1 += 1
                srv ^= 1
                mx, mn = max(g1, g2), min(g1, g2)
                if mx >= 6 and mx - mn >= 2: break
                if mx == 7: break
                if mx == 6 and mn == 6:
                    if rng.random() < 0.5: g1 += 1  # tiebreak ≈ 50/50
                    else:                  g2 += 1
                    srv ^= 1
                    break
            tg += g1 + g2
            if g1 > g2: s1 += 1
            else:        s2 += 1
        res[i] = [s1, s2, tg]
    return res


# ---------------------------------------------------------------------------
# 3. Calibration: bisect delta on hold-prob so sim match-win ≈ target
# ---------------------------------------------------------------------------

def serve_probs_from_winprob(
    target_match_p: float, best_of: int, *,
    base_hold: float = _BASE_HOLD_PROB,
    n_sims: int = _N_SIMS_DEFAULT, seed: int = 42,
) -> Tuple[float, float]:
    """Return (ph1, ph2) hold probs so P(p1 wins match) ≈ target_match_p.

    Parameterises ph1 = base_hold + delta, ph2 = base_hold - delta and bisects
    delta until the simulated match-win probability matches the Elo target.
    This anchors match-win calibration; the engine adds set/games coverage.
    """
    target_match_p = float(np.clip(target_match_p, 0.01, 0.99))
    margin = base_hold - 0.01
    lo, hi = -margin, margin

    def _sim_win(delta: float) -> float:
        p1 = float(np.clip(base_hold + delta, 0.01, 0.99))
        p2 = float(np.clip(base_hold - delta, 0.01, 0.99))
        s = _sim_matches(p1, p2, best_of, n_sims, np.random.default_rng(seed))
        return float((s[:, 0] >= (best_of + 1) // 2).mean())

    for _ in range(_BISECT_MAX_ITER):
        mid = (lo + hi) / 2.0
        pw = _sim_win(mid)
        if abs(pw - target_match_p) < _BISECT_TOL:
            break
        if pw < target_match_p: lo = mid
        else:                   hi = mid

    d = (lo + hi) / 2.0
    return float(np.clip(base_hold + d, 0.01, 0.99)), float(np.clip(base_hold - d, 0.01, 0.99))


# ---------------------------------------------------------------------------
# 4. Full market surface from one JointDistribution
# ---------------------------------------------------------------------------

def markets_from_engine(
    p_serve_p1: float, p_serve_p2: float, best_of: int,
    seed: int = 0, n_sims: int = _N_SIMS_DEFAULT,
) -> Dict[str, float]:
    """Full market surface: match win, sets, straight-sets, total games O/U."""
    rng = np.random.default_rng(seed)
    sims = _sim_matches(p_serve_p1, p_serve_p2, best_of, n_sims, rng)
    JointDistribution(sims.astype(float), joint_quality="simulated")  # coherence wrap

    stw = (best_of + 1) // 2
    mw_p1 = float((sims[:, 0] >= stw).mean())
    mw_p2 = float((sims[:, 1] >= stw).mean())
    ss_p1 = float(((sims[:, 0] == stw) & (sims[:, 1] == 0)).mean())
    ss_p2 = float(((sims[:, 1] == stw) & (sims[:, 0] == 0)).mean())

    set_mkt = {
        f"sets_{int(s1)}_{int(s2)}": c / n_sims
        for (s1, s2), c in Counter(zip(sims[:, 0].tolist(), sims[:, 1].tolist())).items()
    }
    tg = sims[:, 2].astype(float)
    med = int(round(float(np.median(tg))))
    ou = {}
    for line in [float(med + d) for d in (-3.5, -1.5, 0.5, 2.5, 4.5)]:
        po = float((tg > line).mean())
        ou[f"over_{line:g}"] = po
        ou[f"under_{line:g}"] = 1.0 - po

    return {
        "match_win_p1": mw_p1, "match_win_p2": mw_p2,
        "straight_sets_p1": ss_p1, "straight_sets_p2": ss_p2,
        "total_games_mean": float(tg.mean()), "total_games_q50": float(np.median(tg)),
        **set_mkt, **ou,
    }


# ---------------------------------------------------------------------------
# 5. Walk-forward validation on the real corpus
# ---------------------------------------------------------------------------

def build_engine_forecast(
    seasons: Optional[Sequence[int]] = None, *,
    repo_root: Optional[Path] = None,
    matches_path: Optional[str] = None,
    n_sims: int = _N_SIMS_DEFAULT,
    seed: int = 42,
) -> Dict:
    """Walk-forward over tennis corpus; score engine match-win vs Elo baseline.

    Derives serve probs from walk_forward_elo win_prob_p1 (leak-free Elo anchor),
    runs the engine, scores both via score_forecaster against target=winner.
    Returns {n, baseline, engine, dBrier, dECE, note, sample_surface}.
    """
    from scripts.platformkit.scoreboard import score_forecaster
    from domains.tennis.elo_walkforward import walk_forward_elo
    import pandas as pd

    if matches_path is not None:
        df = pd.read_parquet(matches_path)
    else:
        root = repo_root or Path(__file__).resolve().parents[2]
        path = root / "data" / "domains" / "tennis" / "matches.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Tennis matches corpus not found at {path}")
        df = pd.read_parquet(path)

    if seasons:
        df["_year"] = pd.to_datetime(df["date"]).dt.year
        df = df[df["_year"].isin(seasons)].drop(columns=["_year"])

    wf = walk_forward_elo(df)
    valid = wf[wf["win_prob_p1"].notna()].copy()

    targets: List[float] = []
    base_probs: List[float] = []
    eng_probs: List[float] = []
    last_row = None

    for idx, (_, row) in enumerate(valid.iterrows()):
        elo_p = float(row["win_prob_p1"])
        bo = int(row.get("best_of", 3))
        targets.append(1.0 if int(row["winner"]) == 1 else 0.0)
        base_probs.append(elo_p)
        ph1, ph2 = serve_probs_from_winprob(elo_p, bo, n_sims=800, seed=seed + idx % 200)
        eng_probs.append(markets_from_engine(ph1, ph2, bo, seed=seed + idx % 200, n_sims=800)["match_win_p1"])
        last_row = (row, elo_p, bo)

    base_s = score_forecaster(base_probs, targets)
    eng_s = score_forecaster(eng_probs, targets)

    sample_surface: Optional[Dict] = None
    if last_row:
        row, elo_p, bo = last_row
        ph1, ph2 = serve_probs_from_winprob(elo_p, bo, n_sims=n_sims, seed=seed)
        sample_surface = markets_from_engine(ph1, ph2, bo, seed=seed, n_sims=n_sims)
        sample_surface["_match"] = (
            f"{row.get('p1_name','P1')} vs {row.get('p2_name','P2')}"
            f" ({row.get('date','?')}, bo{bo}, elo_p1={elo_p:.3f},"
            f" hold_p1={ph1:.3f}, hold_p2={ph2:.3f})"
        )

    return {
        "n": base_s["n"],
        "baseline": {k: base_s[k] for k in ("brier", "ece", "log_loss")},
        "engine":   {k: eng_s[k]  for k in ("brier", "ece", "log_loss")},
        "dBrier": eng_s["brier"] - base_s["brier"],
        "dECE":   eng_s["ece"]   - base_s["ece"],
        "note": (
            "HONEST: engine value = coherent set/games/straight-sets surface; "
            "match-win calibration parity expected (serve calibrated to Elo anchor); "
            "NO edge claimed; gate decides signal merit."
        ),
        "sample_surface": sample_surface,
    }
