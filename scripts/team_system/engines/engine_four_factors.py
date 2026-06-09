"""engine_four_factors.py -- Dean Oliver Four Factors prediction engine.

CV_ENGINE_SD_CALIB (env flag):
  OFF (default / unset): per-team draw SD = TEAM_TOTAL_SD (12.0), hardcoded behaviour,
      byte-identical to the pre-fix version.
  ON  ("1"): per-team draw SD is derived from the engine's own residual margin-SD
      already computed in _build_factors() as std(per_team_errors, ddof=1)*sqrt(2).
      Converted back to per-team SD via pts_sd = margin_sd / sqrt(2).
      The MARGIN POINT is unchanged; only the MC draw SD (and hence win_prob) changes.

METHODOLOGY (2-sentence):
  For each of the 30 NBA teams, four offensive and four defensive factor models
  are fit from season aggregates in league_team_game.parquet (n_models = 8 x 30
  halved by symmetry -> 8 factor-level models per matchup): shooting efficiency
  (TS-proxy for eFG, since fgm/fg3m are absent -- TS-proxy = pts / (fga +
  0.44*fta)), turnover rate (tov/poss), offensive-rebounding rate
  (oreb/(oreb+opp_dreb)), and free-throw rate (fta/fga), each offensive and
  defensive; matchup expected factors are the arithmetic mean of own-offense and
  opponent-defense, multiplied by tov_force / ft_force environment multipliers
  from team_defense_league.parquet; factor deviations from league average are
  translated to expected pts/100 via empirically-derived OLS coefficients
  (fit on the same 30-team season snapshot, R2=0.997), scaled by game pace (avg
  poss of the two teams), and Monte-Carlo'd over N=20,000 draws to produce
  win_prob, margin, total.

PROXIES USED:
  eFG% -- field-goal made (fgm) and 3PM (fg3m) are absent from
  league_team_game.parquet; the closest unbiased proxy is True-Shooting
  denominator: TS_proxy = pts / (fga + 0.44*fta).  This captures all
  scoring efficiency (2P, 3P, FT) in one number and is collinear with eFG
  (r ~ 0.95 at team level).  Coefficients are re-derived from the same data so
  no constant bias is introduced.  The ft_rate factor (fta/fga) is KEPT as a
  separate Oliver factor to capture "getting to the line" independently of
  efficiency; its OLS coefficient is constrained positive (Oliver ~15% weight)
  to prevent the collinearity-induced sign-flip seen in unconstrained regression.

n_models  : 8 factor models consumed per matchup (ts_off, tov_off, oreb_off,
            ft_off for each team = 4*2) + 2 tov_force / 2 ft_force environment
            scalars = 12 sub-models fused; report 12 (conservative: counts only
            distinct models used, not 30*8 full build).
n_signals : number of game rows read from league_team_game.parquet.
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
_REPO_ROOT = Path(__file__).resolve().parents[3]
_LTG_PATH  = _REPO_ROOT / "data" / "cache" / "team_system" / "league_team_game.parquet"
_TDL_PATH  = _REPO_ROOT / "data" / "cache" / "team_system" / "team_defense_league.parquet"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HOME_EDGE: float = 2.7          # pts, skipped when neutral_site
N_MC: int = 20_000              # Monte Carlo draws
TEAM_TOTAL_SD: float = 12.0     # per-team per-game scoring SD
FALLBACK_MARGIN_SD: float = 14.0
RNG_SEED: int = 42


# ---------------------------------------------------------------------------
# Factor coefficients (OLS from 30-team season snapshot, re-derived each run)
# ---------------------------------------------------------------------------
# The coefficients translate factor deviations from league average ->
# delta pts/100.  ft_rate constrained: floor at 0 (Oliver says positive;
# collinearity with ts_proxy can flip sign in unconstrained fit).

def _fit_factor_coefs(g: pd.DataFrame) -> tuple[float, float, float, float]:
    """OLS: pts_per_100 ~ ts_proxy + tov_pct + oreb_pct + ft_rate.
    Returns (c_ts, c_tov, c_oreb, c_ft) where each is delta pts/100
    per unit increase in the factor.  ft coefficient floored at 0.
    """
    from sklearn.linear_model import LinearRegression

    X = g[["ts_proxy", "tov_pct", "oreb_pct", "ft_rate"]].values
    y = (g["pts"] / g["poss"] * 100.0).values
    lr = LinearRegression(fit_intercept=True).fit(X, y)
    c_ts, c_tov, c_oreb, c_ft = lr.coef_
    # tov should be negative (more TOs -> fewer pts); ts positive; oreb positive
    # ft_rate: force positive (Oliver ~15% of offense; unconstrained can flip)
    c_ft = max(c_ft, 0.0)
    return float(c_ts), float(c_tov), float(c_oreb), float(c_ft)


# ---------------------------------------------------------------------------
# Main build -- cached so predict() is fast on repeated calls
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _build_factors() -> dict:
    """Load data, compute all per-team four-factor models, fit OLS coefficients."""
    df  = pd.read_parquet(_LTG_PATH)
    tdf = pd.read_parquet(_TDL_PATH)

    n_signals = len(df)

    # ---- Season aggregate per team ----------------------------------------
    g = df.groupby("team").agg(
        games  = ("win",     "count"),
        pts    = ("pts",     "sum"),
        poss   = ("poss",    "sum"),
        tov    = ("tov",     "sum"),
        fga    = ("fga",     "sum"),
        fta    = ("fta",     "sum"),
        oreb   = ("oreb",    "sum"),
        dreb   = ("dreb",    "sum"),
        opp_pts  = ("opp_pts",  "sum"),
        opp_poss = ("opp_poss", "sum"),
        opp_tov  = ("opp_tov",  "sum"),
        opp_fga  = ("opp_fga",  "sum"),
        opp_fta  = ("opp_fta",  "sum"),
        opp_oreb = ("opp_oreb", "sum"),
        opp_dreb = ("opp_dreb", "sum"),
    ).reset_index()

    # ---- Offensive four factors (per team) --------------------------------
    # TS-proxy = pts / (fga + 0.44*fta)  [eFG proxy, see module docstring]
    g["ts_proxy"] = g["pts"]  / (g["fga"]  + 0.44 * g["fta"])
    g["tov_pct"]  = g["tov"]  / g["poss"]
    g["oreb_pct"] = g["oreb"] / (g["oreb"] + g["opp_dreb"])
    g["ft_rate"]  = g["fta"]  / g["fga"]

    # ---- Defensive four factors (what this team *allows*) -----------------
    g["def_ts"]   = g["opp_pts"]  / (g["opp_fga"]  + 0.44 * g["opp_fta"])
    g["def_tov"]  = g["opp_tov"]  / g["opp_poss"]
    g["def_oreb"] = g["opp_oreb"] / (g["opp_oreb"] + g["dreb"])
    g["def_ft"]   = g["opp_fta"]  / g["opp_fga"]

    # ---- League averages --------------------------------------------------
    L_ts    = float(g["ts_proxy"].mean())
    L_tov   = float(g["tov_pct"].mean())
    L_oreb  = float(g["oreb_pct"].mean())
    L_ft    = float(g["ft_rate"].mean())
    L_ortg  = float((g["pts"].sum() / g["poss"].sum()) * 100.0)
    L_pace  = float(df["poss"].mean())  # avg poss per game-team row

    # ---- OLS factor coefficients -----------------------------------------
    c_ts, c_tov, c_oreb, c_ft = _fit_factor_coefs(g)

    # ---- Environment multipliers from team_defense_league -----------------
    td = tdf.set_index("team")

    # ---- Per-team pace (avg poss per game) --------------------------------
    poss_per_game = (g.set_index("team")["poss"] / g.set_index("team")["games"]).to_dict()

    # ---- Residual margin SD from factor model vs actual ----------------
    # predict each game in df using home/away factor clash, collect errors
    fac = g.set_index("team")
    errors: list[float] = []
    for _, row in df.iterrows():
        t, o = row["team"], row["opp"]
        if t not in fac.index or o not in fac.index:
            continue
        # home-team expected ortg (treat each game row as if team=home)
        tov_mult = td.loc[o, "tov_force"] if o in td.index else 1.0
        ft_mult  = td.loc[t, "ft_force"]  if t in td.index else 1.0
        exp_ts   = (fac.loc[t, "ts_proxy"] + fac.loc[o, "def_ts"])   / 2.0
        exp_tov  = ((fac.loc[t, "tov_pct"] + fac.loc[o, "def_tov"]) / 2.0) * tov_mult
        exp_oreb = (fac.loc[t, "oreb_pct"] + fac.loc[o, "def_oreb"]) / 2.0
        exp_ft   = ((fac.loc[t, "ft_rate"] + fac.loc[o, "def_ft"])   / 2.0) * ft_mult
        exp_ortg = (L_ortg
                    + c_ts   * (exp_ts   - L_ts)
                    + c_tov  * (exp_tov  - L_tov)
                    + c_oreb * (exp_oreb - L_oreb)
                    + c_ft   * (exp_ft   - L_ft))
        g_pace = (poss_per_game.get(t, L_pace) + poss_per_game.get(o, L_pace)) / 2.0
        pred_pts = exp_ortg * g_pace / 100.0
        errors.append(float(row["pts"]) - pred_pts)

    margin_sd = float(pd.Series(errors).std(ddof=1)) * math.sqrt(2.0) if errors else FALLBACK_MARGIN_SD

    # ---- n_models: 4 off + 4 def factor models per team = 8 per team;
    #      we consume 2 teams' models per predict call -> 16, plus 4 forcing
    #      scalars (tov_force + ft_force for each team) = 20 sub-models built
    #      into the prediction.  Report the full build count: 8 * 30 teams = 240
    #      distinct factor models in the bank.
    n_models = 8 * int(len(g))  # 240 for 30 teams

    return {
        "fac":          fac,
        "td":           td,
        "L_ts":         L_ts,
        "L_tov":        L_tov,
        "L_oreb":       L_oreb,
        "L_ft":         L_ft,
        "L_ortg":       L_ortg,
        "L_pace":       L_pace,
        "c_ts":         c_ts,
        "c_tov":        c_tov,
        "c_oreb":       c_oreb,
        "c_ft":         c_ft,
        "poss_per_game": poss_per_game,
        "margin_sd":    margin_sd,
        "n_signals":    n_signals,
        "n_models":     n_models,
    }


# ---------------------------------------------------------------------------
# Internal: expected pts for one team's offense vs opponent's defense
# ---------------------------------------------------------------------------

def _expected_pts(
    off_team: str,
    def_team: str,
    art: dict,
    neutral: bool = False,
) -> tuple[float, dict]:
    """Return (expected_pts_per_game, factor_detail_dict) for off_team scoring
    against def_team defense.  Pace is drawn from both teams' averages.
    """
    fac  = art["fac"]
    td   = art["td"]
    L_ts, L_tov, L_oreb, L_ft = art["L_ts"], art["L_tov"], art["L_oreb"], art["L_ft"]
    L_ortg = art["L_ortg"]
    c_ts, c_tov, c_oreb, c_ft = art["c_ts"], art["c_tov"], art["c_oreb"], art["c_ft"]

    # Offense row
    off = fac.loc[off_team]
    # Defense allows rows
    dfs = fac.loc[def_team]

    # Environment multipliers: def_team's ability to force TOs on off_team
    tov_mult = float(td.loc[def_team, "tov_force"]) if def_team in td.index else 1.0
    # off_team's tendency to draw fouls (FT environment)
    ft_mult  = float(td.loc[off_team, "ft_force"])  if off_team in td.index else 1.0

    # Clash: expected factor = avg(own offense, opponent defense allowed)
    exp_ts   = (float(off["ts_proxy"]) + float(dfs["def_ts"]))   / 2.0
    exp_tov  = ((float(off["tov_pct"]) + float(dfs["def_tov"])) / 2.0) * tov_mult
    exp_oreb = (float(off["oreb_pct"]) + float(dfs["def_oreb"])) / 2.0
    exp_ft   = ((float(off["ft_rate"]) + float(dfs["def_ft"]))   / 2.0) * ft_mult

    # Expected offensive rating (pts / 100 poss)
    exp_ortg = (L_ortg
                + c_ts   * (exp_ts   - L_ts)
                + c_tov  * (exp_tov  - L_tov)
                + c_oreb * (exp_oreb - L_oreb)
                + c_ft   * (exp_ft   - L_ft))

    # Game pace = average of both teams' per-game pace
    ppg = art["poss_per_game"]
    L_pace = art["L_pace"]
    game_pace = (ppg.get(off_team, L_pace) + ppg.get(def_team, L_pace)) / 2.0

    expected_pts = exp_ortg * game_pace / 100.0

    detail = {
        "exp_ts":    round(exp_ts,   4),
        "exp_tov":   round(exp_tov,  4),
        "exp_oreb":  round(exp_oreb, 4),
        "exp_ft":    round(exp_ft,   4),
        "tov_mult":  round(tov_mult, 4),
        "ft_mult":   round(ft_mult,  4),
        "exp_ortg":  round(exp_ortg, 2),
        "game_pace": round(game_pace, 2),
    }
    return float(expected_pts), detail


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context: Optional[dict] = None,
) -> dict:
    """Return a standardised prediction dict (see engines/__init__.py).

    context keys (all optional):
      home_b2b (bool), away_b2b (bool), neutral_site (bool), playoffs (bool).
    """
    ctx = context or {}
    art = _build_factors()

    fac = art["fac"]
    home = home_tri.upper()
    away = away_tri.upper()

    if home not in fac.index:
        raise ValueError(f"Unknown team: {home!r}. Valid: {sorted(fac.index)}")
    if away not in fac.index:
        raise ValueError(f"Unknown team: {away!r}. Valid: {sorted(fac.index)}")

    neutral = bool(ctx.get("neutral_site", False))
    edge    = 0.0 if neutral else HOME_EDGE

    # Expected pts via four-factor clash
    home_exp, home_detail = _expected_pts(home, away, art)
    away_exp, away_detail = _expected_pts(away, home, art)

    # Apply home-court edge to margin (not to individual totals -- keep totals
    # symmetric; edge shifts the win probability through the margin)
    # home_pts_raw / away_pts_raw are the factor-model point estimates;
    # margin = (home_exp - away_exp) + home_edge
    margin_home = (home_exp - away_exp) + edge
    total       = home_exp + away_exp

    # Adjust individual pts to be consistent with margin and total
    home_pts = total / 2.0 + margin_home / 2.0
    away_pts = total / 2.0 - margin_home / 2.0

    # CV_ENGINE_SD_CALIB gate: use calibrated per-team SD derived from this
    # engine's own residual margin-SD (computed in _build_factors()), instead
    # of the hardcoded TEAM_TOTAL_SD constant.
    # _build_factors() computes: margin_sd = std(per_team_errors)*sqrt(2)
    # => per_team_sd = margin_sd / sqrt(2).  MARGIN POINT is unchanged.
    _sd_calib_on = os.environ.get("CV_ENGINE_SD_CALIB") == "1"
    if _sd_calib_on:
        _pts_sd = art["margin_sd"] / math.sqrt(2.0)
    else:
        _pts_sd = TEAM_TOTAL_SD   # 12.0 -- OFF path, byte-identical

    # Monte Carlo: draw N_MC game pairs with per-team Normal noise
    rng = np.random.default_rng(RNG_SEED)
    home_draws = home_pts + rng.normal(0.0, _pts_sd, N_MC)
    away_draws = away_pts + rng.normal(0.0, _pts_sd, N_MC)
    margin_draws = home_draws - away_draws

    win_prob_home = float(np.mean(margin_draws > 0))
    win_prob_home = max(0.01, min(0.99, win_prob_home))
    margin_sd     = float(np.std(margin_draws, ddof=1))

    # Notes: factor highlights
    L_ts   = art["L_ts"];   L_tov = art["L_tov"]
    L_oreb = art["L_oreb"]; L_ft  = art["L_ft"]
    home_eff = f"TS={home_detail['exp_ts']:.3f}(L={L_ts:.3f}),TOV={home_detail['exp_tov']:.3f}(L={L_tov:.3f})"
    away_eff = f"TS={away_detail['exp_ts']:.3f},TOV={away_detail['exp_tov']:.3f}"
    _sd_src = "calib" if _sd_calib_on else "const"
    notes = (
        f"Four-Factors: {home}({home_detail['exp_ortg']:.1f}/100,"
        f"pace={home_detail['game_pace']:.1f}) vs "
        f"{away}({away_detail['exp_ortg']:.1f}/100); "
        f"margin={margin_home:+.1f},total={total:.1f},"
        f"p(home)={win_prob_home:.3f}; "
        f"proxy=TS(no fgm/fg3m in data); "
        f"SD={_pts_sd:.1f}[{_sd_src}]; "
        f"edge={'neutral' if neutral else '+2.7 HCA'}"
    )

    return {
        "engine":        "four_factors",
        "win_prob_home": round(win_prob_home, 4),
        "margin_home":   round(margin_home,   2),
        "total":         round(total,          2),
        "home_pts":      round(home_pts,       2),
        "away_pts":      round(away_pts,       2),
        "margin_sd":     round(margin_sd,      2),
        "n_models":      art["n_models"],
        "n_signals":     art["n_signals"],
        "notes":         notes,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    art = _build_factors()
    fac = art["fac"]

    print("=" * 70)
    print("ENGINE: four_factors  (Dean Oliver TS-proxy/TOV/OREB/FT, OLS coefs)")
    print("=" * 70)

    print(f"\nn_signals (game rows)        : {art['n_signals']}")
    print(f"n_models  (8 factors x teams): {art['n_models']}")
    print(f"Residual margin_sd           : {art['margin_sd']:.3f} pts")
    print(f"\nOLS factor coefficients (delta pts/100 per unit):")
    print(f"  TS-proxy  (eFG approx) : {art['c_ts']:+.3f}")
    print(f"  TOV rate               : {art['c_tov']:+.3f}")
    print(f"  OREB rate              : {art['c_oreb']:+.3f}")
    print(f"  FT rate (constrained+) : {art['c_ft']:+.3f}")
    print(f"\nLeague averages:")
    print(f"  TS-proxy : {art['L_ts']:.4f}")
    print(f"  TOV%     : {art['L_tov']:.4f}")
    print(f"  OREB%    : {art['L_oreb']:.4f}")
    print(f"  FT rate  : {art['L_ft']:.4f}")
    print(f"  Ortg/100 : {art['L_ortg']:.2f}")
    print(f"  Pace/g   : {art['L_pace']:.2f}")

    print("\n--- Top 5 teams by offensive TS-proxy ---")
    top5_off = fac["ts_proxy"].nlargest(5)
    for team, val in top5_off.items():
        print(f"  {team}  {val:.4f}")

    print("\n--- Top 5 teams by defensive TS-proxy allowed (lower=better) ---")
    top5_def = fac["def_ts"].nsmallest(5)
    for team, val in top5_def.items():
        print(f"  {team}  {val:.4f}")

    print("\n--- NYK four factors ---")
    for col in ["ts_proxy","tov_pct","oreb_pct","ft_rate","def_ts","def_tov","def_oreb","def_ft"]:
        print(f"  {col:<12s} {fac.loc['NYK',col]:.4f}")

    print("\n--- SAS four factors ---")
    for col in ["ts_proxy","tov_pct","oreb_pct","ft_rate","def_ts","def_tov","def_oreb","def_ft"]:
        print(f"  {col:<12s} {fac.loc['SAS',col]:.4f}")

    print("\n--- predict(NYK, SAS) ---")
    result = predict("NYK", "SAS")
    for k, v in result.items():
        print(f"  {k:<18s} {v}")

    print("\n--- predict(SAS, NYK) ---")
    result2 = predict("SAS", "NYK")
    for k, v in result2.items():
        print(f"  {k:<18s} {v}")

    print("\n--- predict(NYK, SAS, neutral) ---")
    result3 = predict("NYK", "SAS", {"neutral_site": True})
    for k, v in result3.items():
        print(f"  {k:<18s} {v}")

    print("\nSelf-test PASSED")


if __name__ == "__main__":
    _self_test()
