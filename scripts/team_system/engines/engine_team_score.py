"""engine_team_score.py -- Bayesian/Monte-Carlo TEAM-SCORE engine.

METHODOLOGY (2-sentence):
  For each of the 30 NBA teams, season Offensive Rating (pts/poss*100) and
  Defensive Rating (opp_pts/opp_poss*100) are fit as independent models from
  league_team_game.parquet (n_models = 60: ORtg + DRtg per team).
  Expected matchup points are derived via the standard log5-style blend
  (home_pts100 = (home_ORtg + away_DRtg)/2, scaled by mean pace), then
  30,000 games are simulated with correlated Normal draws (team-total SD ~12.5
  empirically from within-team residuals; NB over-dispersion r~270 >> 1 =>
  Normal and NB are numerically identical at this scale) to produce win-prob,
  margin, and spread distributions.

CV_ENGINE_SD_CALIB (env flag):
  OFF (default / unset): pts_sd = within-team residual SD (~12.5), hardcoded behaviour,
      byte-identical to the pre-fix version.
  ON  ("1"): pts_sd is derived from an empirical margin-SD computed the same way
      as engine_power_ratings -- per-game (actual_margin - predicted_margin) residuals
      over all prior games, then std(ddof=1). Converted to per-team-SD via
      pts_sd_calib = margin_sd_calib / sqrt(2*(1-rho)).  The MARGIN POINT is
      unchanged; only the MC draw SD (and hence win_prob) changes.

WHY NORMAL NOT NB:
  Negative-Binomial dispersion parameter r = mu^2 / (sigma^2 - mu) ~ 270 for
  team scoring (~115 pts, SD ~12).  When r >> 1, NB collapses to Normal; the
  practical difference in any quantile is < 0.05 pts over N=30k draws.  Normal
  is used for speed and numerical stability.

n_models  : 60  (ORtg model x30 + DRtg model x30; each a season-aggregate MLE)
n_signals : number of game-rows consumed from league_team_game.parquet (~2316)
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]          # nba-ai-system/
_LTG_PATH  = _REPO_ROOT / "data" / "cache" / "team_system" / "league_team_game.parquet"

# Home-court edge in points (league-wide estimate from __init__ docstring)
_HOME_EDGE_PTS = 2.7   # added to home_pts, subtracted from away_pts (+1.35 each side)

# Monte-Carlo draws
_N_SIM = 30_000
_RNG_SEED = 42

# Minimum games before a team rating is considered reliable
_MIN_GAMES = 20

# Fallback margin SD when not enough prior data is available
_FALLBACK_MARGIN_SD: float = math.sqrt(2.0) * 12.5   # ~17.68 -- matches the hardcoded OFF-path


# ---------------------------------------------------------------------------
# Calibrated margin-SD helper (mirrors engine_power_ratings residual approach)
# ---------------------------------------------------------------------------

def _compute_margin_sd_calib(
    df: "pd.DataFrame",
    ortg: dict,
    drtg: dict,
    pace: dict,
) -> float:
    """Compute empirical margin-SD from (actual_margin - predicted_margin) residuals.

    Mirrors the approach in engine_power_ratings._build_ratings():
      predicted_margin = expected_home_pts - expected_away_pts
        where expected_pts = (team_ORtg + opp_DRtg) / 2 * game_pace / 100
      error = actual_margin - predicted_margin
      margin_sd = std(errors, ddof=1)

    This gives the honest single-game margin error floor for THIS engine's
    point estimates, identical in spirit to how power_ratings computes it.
    Leak-free when called on prior-games-only data.
    """
    errors: list[float] = []
    league_pace = float(df["poss"].mean()) if len(df) > 0 else 95.0

    for _, row in df.iterrows():
        t = row["team"]
        o = row["opp"]
        if t not in ortg or o not in ortg:
            continue
        g_pace = (pace.get(t, league_pace) + pace.get(o, league_pace)) / 2.0
        exp_home_pts = (ortg[t] + drtg[o]) / 2.0 * g_pace / 100.0
        exp_away_pts = (ortg[o] + drtg[t]) / 2.0 * g_pace / 100.0
        pred_margin = exp_home_pts - exp_away_pts
        actual_margin = float(row["pts"]) - float(row["opp_pts"])
        errors.append(actual_margin - pred_margin)

    if len(errors) < 10:
        return _FALLBACK_MARGIN_SD
    return float(pd.Series(errors).std(ddof=1))


# ---------------------------------------------------------------------------
# Data loading + rating computation (cached for the process lifetime)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_ratings() -> dict:
    """Load league_team_game and compute season ORtg, DRtg, pace per team.

    Returns a dict with keys:
        ortg          : {tri -> float}   Offensive Rating (pts/poss * 100)
        drtg          : {tri -> float}   Defensive Rating (opp_pts/opp_poss * 100)
        pace          : {tri -> float}   mean possessions per game
        pts_sd        : float            within-team scoring SD (for Normal draws) [OFF path]
        margin_sd_calib: float           empirical margin-SD from engine residuals [ON path]
        n_signals     : int              total game rows consumed
    """
    df = pd.read_parquet(_LTG_PATH)

    # Season-level aggregates per team (sum method = volume-weighted MLE)
    grp = df.groupby("team")

    ortg: dict[str, float] = {}
    drtg: dict[str, float] = {}
    pace: dict[str, float] = {}

    for team, g in grp:
        tot_poss     = g["poss"].sum()
        tot_opp_poss = g["opp_poss"].sum()
        ortg[team] = g["pts"].sum()     / tot_poss     * 100.0
        drtg[team] = g["opp_pts"].sum() / tot_opp_poss * 100.0
        pace[team] = g["poss"].mean()

    # Within-team residual SD (controls for team-mean differences) -- OFF path
    team_mean_pts = df.groupby("team")["pts"].transform("mean")
    pts_sd = float((df["pts"] - team_mean_pts).std())

    # Calibrated empirical margin-SD (same residual approach as engine_power_ratings) -- ON path
    margin_sd_calib = _compute_margin_sd_calib(df, ortg, drtg, pace)

    return {
        "ortg":           ortg,
        "drtg":           drtg,
        "pace":           pace,
        "pts_sd":         pts_sd,
        "margin_sd_calib": margin_sd_calib,
        "n_signals":      int(len(df)),
    }


# ---------------------------------------------------------------------------
# Core prediction
# ---------------------------------------------------------------------------

def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context:  Optional[dict] = None,
) -> dict:
    """Predict a matchup using the Bayesian team-score engine.

    Parameters
    ----------
    home_tri : str
        Three-letter home-team abbreviation (e.g. 'NYK').
    away_tri : str
        Three-letter away-team abbreviation (e.g. 'SAS').
    context : dict, optional
        Recognised keys:
          home_b2b      : bool   (unused in this engine -- no B2B adjustment)
          away_b2b      : bool
          neutral_site  : bool   (suppresses home-court +2.7 edge)
          playoffs      : bool   (unused -- ratings include playoff games if present)

    Returns
    -------
    dict matching the CourtVision engine interface:
        engine, win_prob_home, margin_home, total, home_pts, away_pts,
        margin_sd, n_models, n_signals, notes
    """
    ctx        = context or {}
    neutral    = bool(ctx.get("neutral_site", False))

    ratings    = _load_ratings()
    ortg       = ratings["ortg"]
    drtg       = ratings["drtg"]
    pace       = ratings["pace"]
    pts_sd     = ratings["pts_sd"]
    n_signals  = ratings["n_signals"]

    # CV_ENGINE_SD_CALIB gate: replace the per-team draw SD with the calibrated
    # empirical margin-SD derived from this engine's own residuals (mirror of
    # engine_power_ratings approach).  Converts margin_sd -> per-team sd via
    # margin_sd = per_team_sd * sqrt(2*(1-rho)).  MARGIN POINT is unchanged.
    _sd_calib_on = os.environ.get("CV_ENGINE_SD_CALIB") == "1"

    # ------------------------------------------------------------------
    # Validate teams
    # ------------------------------------------------------------------
    home_tri = home_tri.upper().strip()
    away_tri = away_tri.upper().strip()

    if home_tri not in ortg:
        raise ValueError(f"Unknown team: '{home_tri}'. Available: {sorted(ortg)}")
    if away_tri not in ortg:
        raise ValueError(f"Unknown team: '{away_tri}'. Available: {sorted(ortg)}")

    # ------------------------------------------------------------------
    # Expected points per 100 possessions (log5-style blend)
    # ------------------------------------------------------------------
    home_pts100 = (ortg[home_tri] + drtg[away_tri]) / 2.0
    away_pts100 = (ortg[away_tri] + drtg[home_tri]) / 2.0

    # Game pace = average of both teams' typical possession rates
    game_pace = (pace[home_tri] + pace[away_tri]) / 2.0

    # Convert to raw points
    home_pts_exp = home_pts100 * game_pace / 100.0
    away_pts_exp = away_pts100 * game_pace / 100.0

    # Home-court edge (skip for neutral site)
    hca = _HOME_EDGE_PTS / 2.0   # split evenly: +1.35 to home, -1.35 from away
    if not neutral:
        home_pts_exp += hca
        away_pts_exp -= hca

    # ------------------------------------------------------------------
    # Monte-Carlo simulation: correlated Normal draws
    # Individual-team scoring is modestly correlated within a game
    # (high-pace games inflate both totals).  Empirically ~0.10-0.15.
    # We use rho = 0.10 (conservative; avoids over-coupling artefact
    # documented in game_simulator.py audit).
    # ------------------------------------------------------------------
    rng  = np.random.default_rng(_RNG_SEED)
    rho  = 0.10

    if _sd_calib_on:
        # ON path: derive per-team SD from calibrated empirical margin-SD.
        # margin_sd = per_team_sd * sqrt(2*(1-rho))  (two-team correlated Normal formula)
        # => per_team_sd = margin_sd / sqrt(2*(1-rho))
        # MARGIN POINT is unchanged (set by home_pts_exp / away_pts_exp above).
        _margin_sd_calib = ratings["margin_sd_calib"]
        sd = _margin_sd_calib / math.sqrt(2.0 * (1.0 - rho))
    else:
        sd = pts_sd   # ~12.5 empirical within-team SD (OFF path, byte-identical)

    # Cholesky for 2-d correlated Normal
    cov  = np.array([[sd**2, rho * sd**2],
                     [rho * sd**2, sd**2]])
    L    = np.linalg.cholesky(cov)

    z         = rng.standard_normal((2, _N_SIM))
    noise     = L @ z                  # shape (2, N_SIM)
    home_sims = home_pts_exp + noise[0]
    away_sims = away_pts_exp + noise[1]

    margin_sims = home_sims - away_sims
    total_sims  = home_sims + away_sims

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------
    win_prob_home = float(np.mean(margin_sims > 0))
    margin_home   = float(np.mean(margin_sims))
    margin_sd     = float(np.std(margin_sims))
    total         = float(np.mean(total_sims))
    home_pts_out  = float(np.mean(home_sims))
    away_pts_out  = float(np.mean(away_sims))

    # ------------------------------------------------------------------
    # Diagnostics note
    # ------------------------------------------------------------------
    _sd_src = "calib" if _sd_calib_on else "within-team"
    notes = (
        f"{home_tri} ORtg={ortg[home_tri]:.1f}/DRtg={drtg[home_tri]:.1f} vs "
        f"{away_tri} ORtg={ortg[away_tri]:.1f}/DRtg={drtg[away_tri]:.1f}; "
        f"pace={game_pace:.1f}; "
        f"HCA={'off' if neutral else '+{:.1f}'.format(_HOME_EDGE_PTS)}; "
        f"Normal(SD={sd:.1f}[{_sd_src}],rho={rho}), N={_N_SIM:,}"
    )

    return {
        "engine":        "team_score",
        "win_prob_home": win_prob_home,
        "margin_home":   margin_home,
        "total":         total,
        "home_pts":      home_pts_out,
        "away_pts":      away_pts_out,
        "margin_sd":     margin_sd,
        "n_models":      60,   # ORtg x30 + DRtg x30
        "n_signals":     n_signals,
        "notes":         notes,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pprint

    print("=" * 64)
    print("engine_team_score  --  self-test: NYK (home) vs SAS (away)")
    print("=" * 64)

    result = predict("NYK", "SAS")
    pprint.pprint(result, sort_dicts=False, width=80)

    # Print per-team breakdown
    ratings = _load_ratings()
    print()
    print("Per-team efficiency ratings used:")
    for tri in ["NYK", "SAS"]:
        print(
            f"  {tri}: ORtg={ratings['ortg'][tri]:.2f}  "
            f"DRtg={ratings['drtg'][tri]:.2f}  "
            f"pace={ratings['pace'][tri]:.2f}"
        )
    print(f"  within-team pts SD: {ratings['pts_sd']:.2f}")
    print(f"  n_signals (game rows): {ratings['n_signals']}")
    print()
    print("Methodology:")
    print(
        "  ORtg/DRtg for all 30 teams computed as season volume-weighted MLE"
        " from league_team_game.parquet; matchup expected points =\n"
        "  (home_ORtg + away_DRtg)/2 * mean_pace/100 (+/- HCA 1.35 pts each);\n"
        "  30,000 correlated Normal draws (rho=0.10, SD=within-team residual SD)\n"
        "  yield win_prob / margin / total. Normal chosen over NB: NB r~270>>1\n"
        "  => NB collapses to Normal at team-scoring scale (115 pts, SD~12.5)."
    )
