"""domains.tennis.match_engine_holds — As-of hold%-fed match engine for GAMES/SETS markets.

Wraps match_engine.py (read-only) with per-player surface-conditioned as-of hold%
from asof_hold.py (read-only).  Uses each player's own as-of hold% as their BASE,
then bisects a shared delta so simulated MATCH-WIN still anchors to the Elo target.
This reshapes the GAMES/SETS distribution without changing match-win parity.

HONEST: accuracy/calibration only.  NO edge claimed.
LEAK DISCIPLINE: as-of hold is prior-only by construction (see asof_hold.py).
NO src/ / kernel/ / api/ / scripts/team_system edits.  <=300 LOC.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# Read-only imports from existing modules
from domains.tennis.match_engine import (
    _sim_matches,           # point MC runner
    markets_from_engine,    # full market surface
    _BASE_HOLD_PROB,
    _BISECT_TOL,
    _BISECT_MAX_ITER,
    _N_SIMS_DEFAULT,
)

_MIN_PRIOR: int = 5                          # below this → fallback to population mean
_FALLBACK_HOLD: float = _BASE_HOLD_PROB      # same as flat engine default


def _pick_hold(
    overall: float,
    surface_specific: float,
    n_prior: int,
    fallback: float = _FALLBACK_HOLD,
    min_prior: int = _MIN_PRIOR,
) -> float:
    """Return best hold estimate: surface-specific > overall > fallback.  n_prior < min_prior → fallback."""
    if n_prior < min_prior:
        return fallback
    if not math.isnan(surface_specific):
        return float(np.clip(surface_specific, 0.30, 0.95))
    if not math.isnan(overall):
        return float(np.clip(overall, 0.30, 0.95))
    return fallback


def serve_probs_asof(
    target_match_p: float,
    best_of: int,
    base_hold_p1: float,
    base_hold_p2: float,
    *,
    n_sims: int = _N_SIMS_DEFAULT,
    seed: int = 42,
) -> Tuple[float, float]:
    """Return (ph1, ph2) by bisecting delta: ph1=base_h1+d, ph2=base_h2-d → sim MW ≈ elo target."""
    target_match_p = float(np.clip(target_match_p, 0.01, 0.99))
    margin = min(base_hold_p1 - 0.01, 0.99 - base_hold_p2, 0.40)
    lo, hi = -margin, margin

    def _sim_win(delta: float) -> float:
        p1 = float(np.clip(base_hold_p1 + delta, 0.01, 0.99))
        p2 = float(np.clip(base_hold_p2 - delta, 0.01, 0.99))
        sims = _sim_matches(p1, p2, best_of, n_sims, np.random.default_rng(seed))
        return float((sims[:, 0] >= (best_of + 1) // 2).mean())

    for _ in range(_BISECT_MAX_ITER):
        mid = (lo + hi) / 2.0
        pw = _sim_win(mid)
        if abs(pw - target_match_p) < _BISECT_TOL:
            break
        if pw < target_match_p:
            lo = mid
        else:
            hi = mid

    d = (lo + hi) / 2.0
    return (
        float(np.clip(base_hold_p1 + d, 0.01, 0.99)),
        float(np.clip(base_hold_p2 - d, 0.01, 0.99)),
    )


def markets_asof(
    elo_win_prob_p1: float,
    best_of: int,
    base_hold_p1: float,
    base_hold_p2: float,
    *,
    seed: int = 0,
    n_sims: int = _N_SIMS_DEFAULT,
) -> Dict[str, float]:
    """Full market surface: match-win anchored to Elo, games/sets shaped by as-of hold bases."""
    ph1, ph2 = serve_probs_asof(
        elo_win_prob_p1, best_of, base_hold_p1, base_hold_p2,
        n_sims=n_sims, seed=seed,
    )
    return markets_from_engine(ph1, ph2, best_of, seed=seed, n_sims=n_sims)


def assert_matchwin_parity(
    elo_p: float,
    best_of: int,
    base_hold_p1: float,
    base_hold_p2: float,
    *,
    tol: float = 0.05,
    n_sims: int = 2000,
    seed: int = 99,
) -> None:
    """Raise AssertionError if |sim_match_win - elo_p| > tol after as-of bisection."""
    ph1, ph2 = serve_probs_asof(
        elo_p, best_of, base_hold_p1, base_hold_p2, n_sims=n_sims, seed=seed,
    )
    sims = _sim_matches(ph1, ph2, best_of, n_sims, np.random.default_rng(seed + 1))
    stw = (best_of + 1) // 2
    sim_mw = float((sims[:, 0] >= stw).mean())
    err = abs(sim_mw - elo_p)
    if err > tol:
        raise AssertionError(
            f"Match-win parity violated: elo_p={elo_p:.4f}, sim={sim_mw:.4f}, "
            f"err={err:.4f} > tol={tol:.4f}  (ph1={ph1:.4f}, ph2={ph2:.4f})"
        )


def _parse_total_games(score: str) -> Optional[int]:  # e.g. '6-3 6-1 7-5' → 22
    if not isinstance(score, str) or not score.strip():
        return None
    try:
        total = 0
        for s in score.split():
            s_clean = s.split("(")[0]
            parts = s_clean.split("-")
            if len(parts) == 2:
                total += int(parts[0]) + int(parts[1])
        return total if total > 0 else None
    except Exception:
        return None


def calibrate_total_games(
    seasons: Optional[Sequence[int]] = None,
    *,
    repo_root: Optional[Path] = None,
    n_sims: int = 1500,
    seed: int = 42,
    min_prior: int = _MIN_PRIOR,
    max_rows: int = 2000,
) -> Dict:
    """Walk-forward: flat-0.62 vs as-of-hold on total-games MAE + O/U Brier (max_rows recent subset).

    HONEST: no edge claimed; reports truthfully if as-of-hold does not improve.
    """
    from domains.tennis.elo_walkforward import walk_forward_elo
    from domains.tennis.match_engine import serve_probs_from_winprob

    root = repo_root or Path(__file__).resolve().parents[2]
    matches_path = root / "data" / "domains" / "tennis" / "matches.parquet"
    asof_path = root / "data" / "domains" / "tennis" / "asof_hold.parquet"

    df = pd.read_parquet(matches_path)
    if seasons:
        df["_year"] = pd.to_datetime(df["date"]).dt.year
        df = df[df["_year"].isin(seasons)].drop(columns=["_year"])

    wf = walk_forward_elo(df)
    aoh = pd.read_parquet(asof_path)

    merged = wf.merge(aoh[["event_id", "p1_hold_pct_asof", "p2_hold_pct_asof",
                             "p1_hold_pct_hard_asof", "p1_hold_pct_clay_asof",
                             "p1_hold_pct_grass_asof", "p2_hold_pct_hard_asof",
                             "p2_hold_pct_clay_asof", "p2_hold_pct_grass_asof",
                             "p1_n_prior", "p2_n_prior"]],
                      on="event_id", how="left")
    merged["_total_games"] = merged["score"].apply(_parse_total_games)
    valid = merged[
        merged["win_prob_p1"].notna() &
        merged["_total_games"].notna() &
        (merged["_total_games"] > 0)
    ].copy()

    # Subset: last max_rows rows after sorting chronologically
    valid = valid.sort_values("date").tail(max_rows).reset_index(drop=True)

    flat_preds: List[float] = []
    asof_preds: List[float] = []
    actuals: List[float] = []
    flat_ou_probs: List[float] = []
    asof_ou_probs: List[float] = []
    ou_actuals: List[float] = []
    ou_line = 22.5   # canonical line (close to bo3 median ~24)

    for idx, row in valid.iterrows():
        elo_p = float(row["win_prob_p1"])
        bo = int(row.get("best_of", 3))
        tg_actual = float(row["_total_games"])
        surf = str(row.get("surface", "Hard"))
        n1 = int(row.get("p1_n_prior", 0))
        n2 = int(row.get("p2_n_prior", 0))

        surf_col = surf.lower() if surf.lower() in ("hard", "clay", "grass") else "hard"
        h1_surf = float(row.get(f"p1_hold_pct_{surf_col}_asof") or float("nan"))
        h2_surf = float(row.get(f"p2_hold_pct_{surf_col}_asof") or float("nan"))
        h1_all = float(row.get("p1_hold_pct_asof") or float("nan"))
        h2_all = float(row.get("p2_hold_pct_asof") or float("nan"))

        base_h1 = _pick_hold(h1_all, h1_surf, n1, min_prior=min_prior)
        base_h2 = _pick_hold(h2_all, h2_surf, n2, min_prior=min_prior)

        run_seed = seed + (idx % 500)
        # -- Flat engine (baseline)
        ph1_flat, ph2_flat = serve_probs_from_winprob(
            elo_p, bo, base_hold=_BASE_HOLD_PROB, n_sims=800, seed=run_seed,
        )
        m_flat = markets_from_engine(ph1_flat, ph2_flat, bo, seed=run_seed, n_sims=800)
        flat_mean = m_flat["total_games_mean"]
        flat_preds.append(flat_mean)
        flat_ou = m_flat.get(f"over_{ou_line:g}", 0.5)
        flat_ou_probs.append(flat_ou)
        # -- As-of-hold engine
        ph1_asof, ph2_asof = serve_probs_asof(
            elo_p, bo, base_h1, base_h2, n_sims=800, seed=run_seed,
        )
        m_asof = markets_from_engine(ph1_asof, ph2_asof, bo, seed=run_seed, n_sims=800)
        asof_mean = m_asof["total_games_mean"]
        asof_preds.append(asof_mean)
        asof_ou = m_asof.get(f"over_{ou_line:g}", 0.5)
        asof_ou_probs.append(asof_ou)

        actuals.append(tg_actual)
        ou_actuals.append(1.0 if tg_actual > ou_line else 0.0)

    flat_mae = float(np.mean(np.abs(np.array(flat_preds) - np.array(actuals))))
    asof_mae = float(np.mean(np.abs(np.array(asof_preds) - np.array(actuals))))

    def _brier(probs: List[float], acts: List[float]) -> float:
        p = np.array(probs); a = np.array(acts)
        return float(np.mean((p - a) ** 2))

    flat_brier = _brier(flat_ou_probs, ou_actuals)
    asof_brier = _brier(asof_ou_probs, ou_actuals)

    return {
        "n": len(actuals),
        "ou_line": ou_line,
        "flat_total_games_mae": flat_mae,
        "asof_total_games_mae": asof_mae,
        "delta_mae": asof_mae - flat_mae,
        "flat_ou_brier": flat_brier,
        "asof_ou_brier": asof_brier,
        "delta_brier": asof_brier - flat_brier,
        "note": (
            "HONEST: accuracy/calibration only. delta_mae < 0 means as-of engine predicts "
            "total-games better; delta_mae > 0 means flat engine wins. NO edge claimed. "
            "Gate decides signal merit."
        ),
    }
