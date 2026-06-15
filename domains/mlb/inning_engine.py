"""domains.mlb.inning_engine — Leak-free runs-scoring engine for MLB.

Poisson run-rate lambdas → joint runs matrix → ML/RL/totals/F5 markets.
HONEST: WIN = coherent RL/totals/F5 surface Elo can't emit. NO edge claimed.
LIVE-WIRED: only RunRateState (per-game lambda estimation) is wired into the
production path; runs_matrix (the Poisson joint) is reused externally just by the
sgp_pricer __main__ demo (hardcoded lambdas), so it is research/demo-only here.
RESEARCH-ONLY: markets_from_matrix builds a Poisson market surface that is
SUPERSEDED by domains/mlb/negbinom_engine.py (over-dispersed); anchor_lambdas_to_winprob
(Elo-anchor, default OFF) tilts the lambda ratio to match target P(home win) while
preserving lambda SUM. build_engine_forecast is an EVAL HARNESS (walk-forward
back-test of engine vs Elo), NOT a per-game live wiring; anchor_to_elo=True is its
research toggle, False=original.
INVARIANTS: never edit src/kernel; imports read-only; <=300 LOC.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_MAX_RUNS_DEFAULT = 25
_TOTAL_LINES: Tuple[float, ...] = (6.5, 7.5, 8.5, 9.5, 10.5)
_F5_SCALE = 5.0 / 9.0
_F5_MAX_RUNS = 12


def _poisson_pmf(lam: float, max_k: int) -> np.ndarray:
    """Poisson PMF P(X=k) for k=0..max_k in log-space."""
    k = np.arange(max_k + 1, dtype=float)
    lf = np.zeros(max_k + 1, dtype=float)
    for i in range(1, max_k + 1):
        lf[i] = lf[i - 1] + math.log(i)
    return np.exp(-lam + k * math.log(lam) - lf)


def runs_matrix(
    lam_home: float,
    lam_away: float,
    *,
    max_runs: int = _MAX_RUNS_DEFAULT,
) -> np.ndarray:
    """Independent-Poisson joint runs matrix P[i,j]=P(home=i, away=j runs).

    Shape (max_runs+1, max_runs+1). Renormalised to sum=1 (truncation correction).
    """
    if lam_home <= 0 or lam_away <= 0:
        raise ValueError(f"lambdas must be positive; got {lam_home}, {lam_away}")
    P = np.outer(_poisson_pmf(lam_home, max_runs), _poisson_pmf(lam_away, max_runs))
    s = P.sum()
    if s > 0:
        P /= s
    return P


def _total_dist(P: np.ndarray) -> np.ndarray:
    """Marginal distribution of total runs from joint matrix."""
    n = P.shape[0]
    d = np.zeros(2 * n - 1, dtype=float)
    for i in range(n):
        for j in range(n):
            d[i + j] += P[i, j]
    return d


def _f5_surface(F5: np.ndarray) -> Dict[str, float]:
    """F5 ML + O/U 4.5/5.5 from a first-5-innings runs matrix."""
    n = F5.shape[0]
    ri, ci = np.arange(n)[:, None], np.arange(n)[None, :]
    ph = float(F5[ri > ci].sum())
    pa = float(F5[ri < ci].sum())
    pt = float(F5[ri == ci].sum())
    out = {"f5_ml_home": ph + 0.5 * pt, "f5_ml_away": pa + 0.5 * pt}
    d = _total_dist(F5)
    for line in (4.5, 5.5):
        po = float(d[int(line + 0.5):].sum())
        out[f"f5_over_{line:g}"] = po
        out[f"f5_under_{line:g}"] = 1.0 - po
    return out


def markets_from_matrix(
    P: np.ndarray,
    *,
    total_lines: Sequence[float] = _TOTAL_LINES,
    f5_lam_home: Optional[float] = None,
    f5_lam_away: Optional[float] = None,
) -> Dict[str, float]:
    """Full market surface from a runs matrix.

    Keys: ml_home/ml_away (ML; sum=1), rl_home_minus15/rl_away_plus15 (RL; sum=1),
    over_N/under_N for N in total_lines, f5_* if f5 lambdas supplied.
    Tie redistribution: P(draw) split 50/50 (extra innings ~ coin flip).
    """
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
        po = float(d[int(line + 0.5):].sum())
        out[f"over_{line:g}"] = po
        out[f"under_{line:g}"] = 1.0 - po
    if f5_lam_home is not None and f5_lam_away is not None:
        out.update(_f5_surface(runs_matrix(f5_lam_home, f5_lam_away, max_runs=_F5_MAX_RUNS)))
    return out


def anchor_lambdas_to_winprob(
    lam_home: float,
    lam_away: float,
    target_p_home: float,
    *,
    max_iter: int = 40,
) -> Tuple[float, float]:
    """Tilt the lambda RATIO so runs_matrix ML == target_p_home; SUM preserved.

    Tilt t: lam_home'=S*t/(1+t), lam_away'=S/(1+t), S=lam_home+lam_away.
    Bisect on t (geometric midpoints) until ml_home == target within ~1e-9.
    """
    if not (0.0 < target_p_home < 1.0):
        raise ValueError(f"target_p_home must be in (0,1); got {target_p_home}")
    if lam_home <= 0 or lam_away <= 0:
        raise ValueError(f"lambdas must be positive; got {lam_home}, {lam_away}")

    S = lam_home + lam_away  # SUM preserved throughout

    def _ml(t: float) -> float:
        lh = max(S * t / (1.0 + t), 1e-6)
        la = max(S / (1.0 + t), 1e-6)
        return markets_from_matrix(runs_matrix(lh, la))["ml_home"]

    t0 = lam_home / lam_away
    if abs(_ml(t0) - target_p_home) < 1e-9:  # fast no-op path
        return lam_home, lam_away

    lo, hi = 1e-6, 1e6
    for _ in range(max_iter):
        mid = math.sqrt(lo * hi)  # geometric bisect on positive ratio
        if _ml(mid) < target_p_home:
            lo = mid
        else:
            hi = mid

    t_star = math.sqrt(lo * hi)
    return max(S * t_star / (1.0 + t_star), 1e-6), max(S / (1.0 + t_star), 1e-6)


class RunRateState:
    """EW team run-rate state (off+def), updated AFTER each pre-game snapshot.

    lam_home = HFA * (off_home * def_away) / mu
    lam_away = (off_away * def_home) / mu
    Mirrors soccer ratings _GoalsState pattern but for baseball runs.
    """
    ALPHA = 0.06
    MU_INIT = 4.4
    HFA = 1.04
    SEASON_REGRESS = 0.25

    def __init__(self) -> None:
        self._off: Dict[str, float] = {}
        self._def: Dict[str, float] = {}
        self._last_season: Dict[str, int] = {}

    def _init_team(self, team: str, season: int) -> None:
        if team not in self._off:
            self._off[team] = self._def[team] = self.MU_INIT
            self._last_season[team] = season
        elif self._last_season.get(team) != season:
            mu = self.MU_INIT
            r = self.SEASON_REGRESS
            self._off[team] += r * (mu - self._off[team])
            self._def[team] += r * (mu - self._def[team])
            self._last_season[team] = season

    def snapshot(self, home: str, away: str, season: int) -> Tuple[float, float]:
        """Return (lam_home, lam_away) BEFORE this game's result is incorporated."""
        self._init_team(home, season)
        self._init_team(away, season)
        mu = self.MU_INIT
        lh = max(self.HFA * self._off[home] * self._def[away] / mu, 0.1)
        la = max(self._off[away] * self._def[home] / mu, 0.1)
        return lh, la

    def update(self, home: str, away: str, hr: float, ar: float) -> None:
        """Incorporate observed result (call AFTER snapshot)."""
        a = self.ALPHA
        self._off[home] = (1 - a) * self._off[home] + a * hr
        self._off[away] = (1 - a) * self._off[away] + a * ar
        self._def[home] = (1 - a) * self._def[home] + a * ar
        self._def[away] = (1 - a) * self._def[away] + a * hr


def build_engine_forecast(
    seasons: Optional[Sequence[int]] = None,
    *,
    repo_root: Optional[Path] = None,
    games_path: Optional[str] = None,
    anchor_to_elo: bool = False,
) -> Dict:
    """Walk-forward over the MLB corpus; score engine vs Elo-baseline moneyline.

    Returns: n, baseline/engine {brier,ece,log_loss}, dBrier, dECE, note,
    sample_surface (full market dict for the last game).
    Engine WIN: coherent RL/totals/F5. ML calibration ~parity; NO edge claimed.

    anchor_to_elo=True: tilt lambdas per-game so ml_home==Elo p_home (SUM preserved).
    False (default): original behaviour exactly. HONEST: parity ML; NO edge claimed.
    """
    import pandas as pd
    from scripts.platformkit.scoreboard import score_forecaster
    from domains.mlb.ratings import _sorted, walk_forward_elo

    if games_path is not None:
        games_df = pd.read_parquet(games_path)
    else:
        root = repo_root or Path(__file__).resolve().parents[2]
        path = root / "data" / "domains" / "mlb" / "games.parquet"
        if not path.exists():
            raise FileNotFoundError(f"MLB games corpus not found at {path}")
        games_df = pd.read_parquet(path)

    if seasons:
        games_df = games_df[games_df["season"].isin(seasons)]

    wf_elo = walk_forward_elo(games_df)
    df_s = _sorted(games_df)
    rr = RunRateState()
    lam_homes: List[float] = []
    lam_aways: List[float] = []

    for i in range(len(df_s)):
        home = str(df_s["home_team"].iloc[i])
        away = str(df_s["away_team"].iloc[i])
        season = int(df_s["season"].iloc[i])
        hr = float(df_s["home_runs"].iloc[i])
        ar = float(df_s["away_runs"].iloc[i])
        lh, la = rr.snapshot(home, away, season)
        lam_homes.append(lh)
        lam_aways.append(la)
        rr.update(home, away, hr, ar)

    df_s = df_s.copy()
    df_s["lam_home"] = lam_homes
    df_s["lam_away"] = lam_aways
    wf = wf_elo.merge(df_s[["event_id", "lam_home", "lam_away"]], on="event_id", how="left")
    valid = wf[wf["target_home_win"].notna() & wf["lam_home"].notna()].copy()

    targets: List[float] = valid["target_home_win"].astype(float).tolist()
    baseline_probs: List[float] = valid["p_home_elo"].tolist()
    engine_probs: List[float] = []
    last_surface: Optional[Dict] = None
    last_row = None

    for _, row in valid.iterrows():
        lh, la = float(row["lam_home"]), float(row["lam_away"])
        if anchor_to_elo:
            target_p = float(row["p_home_elo"])
            # Clamp target to valid open range (avoid degenerate matrices)
            target_p = max(0.01, min(0.99, target_p))
            lh, la = anchor_lambdas_to_winprob(lh, la, target_p)
        P = runs_matrix(lh, la)
        mkts = markets_from_matrix(P, f5_lam_home=lh * _F5_SCALE, f5_lam_away=la * _F5_SCALE)
        engine_probs.append(mkts["ml_home"])
        last_surface, last_row = mkts, row

    base_s = score_forecaster(baseline_probs, targets)
    eng_s = score_forecaster(engine_probs, targets)

    if last_surface is not None and last_row is not None:
        last_surface["_game"] = (
            f"{last_row.get('home_team','?')} vs {last_row.get('away_team','?')}"
            f" (lam_h={float(last_row['lam_home']):.3f}, lam_a={float(last_row['lam_away']):.3f})"
        )
        last_surface["_date"] = str(last_row.get("date", "?"))

    if anchor_to_elo:
        note = (
            "HONEST: anchor_to_elo=True — ML == Elo p_home (parity); "
            "RL/totals/F5 from sum-preserved run-rate matrix. NO edge claimed; gate decides."
        )
    else:
        note = (
            "HONEST: engine WIN = coherent RL/totals/F5 surface (Elo can't price these). "
            "ML calibration ~parity with Elo. NO edge claimed; gate decides."
        )
    return {
        "n": base_s["n"],
        "baseline": {k: base_s[k] for k in ("brier", "ece", "log_loss")},
        "engine":   {k: eng_s[k]  for k in ("brier", "ece", "log_loss")},
        "dBrier": eng_s["brier"] - base_s["brier"],
        "dECE":   eng_s["ece"]   - base_s["ece"],
        "anchor_to_elo": anchor_to_elo,
        "note": note,
        "sample_surface": last_surface,
    }
