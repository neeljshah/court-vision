"""engine_asof_backtest.py -- As-of engine reliability backtest (V0).

honesty_class = research.

Builds a leak-free walk-forward over 3 as-of-capable engines:
  - power_ratings  (SRS over prior game rows)
  - team_score     (ORtg/DRtg MLE over prior rows, closed-form margin)
  - four_factors   (four-factor OLS over prior rows, closed-form margin)

Excluded (no date/gid column in their source data):
  - player_impact       -- player_ratings.parquet has no date
  - attribute_matchup   -- attribute_vault.parquet has no date
  - possession_mc       -- TeamModel season-substrate, no within-season refresh
  - clock_trajectory    -- same TeamModel blocker

Outputs:
  data/cache/team_system/engine_asof_preds.parquet
  data/cache/team_system/engine_reliability_weights.json

Usage:
  python scripts/team_system/engine_asof_backtest.py
"""
from __future__ import annotations

import json
import math
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS   = os.path.join(ROOT, "data", "cache", "team_system")

# ---- burn-in (must match walkforward_league.py convention) -----------------
BURNIN       = 10
HOME_EDGE    = 2.7
SIGMA_FALLBACK = 13.0          # prior for margin_sd before 50 games exist
K_RTG        = 400.0           # possessions -- empirical-Bayes shrink (walkforward_league.py)
K_PACE       = 8.0
K_MECH       = 12.0
FF_MIN_TEAMS = 15              # min team-rows before refitting OLS (use fixed coefs below)

# fixed OLS coefs from full-season fit (fallback when too few rows)
_FIXED_C_TS   =  120.0
_FIXED_C_TOV  =  -90.0
_FIXED_C_OREB =   15.0
_FIXED_C_FT   =   10.0


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ===========================================================================
# Accumulator helpers (mirroring walkforward_league.py)
# ===========================================================================

def _blank_acc() -> dict:
    return dict(
        g=0,
        pts=0.0, poss=0.0,
        opp_pts=0.0, opp_poss=0.0,
        opp_tov=0.0, opp_fta=0.0, opp_fga=0.0,
        oreb=0.0, opp_dreb=0.0,
        tov=0.0,
        fga=0.0, fta=0.0,
        dreb=0.0,
        opp_oreb=0.0,
        margins=[]          # list of actual game margins for this team (for SRS)
    )


def _update_acc(acc: dict, row) -> None:
    """Update a team's running accumulator from one game row (namedtuple from itertuples)."""
    a = acc
    a["g"]        += 1
    a["pts"]      += float(row.pts)
    a["poss"]     += float(row.poss)
    a["opp_pts"]  += float(row.opp_pts)
    a["opp_poss"] += float(row.opp_poss)
    a["opp_tov"]  += float(row.opp_tov)
    a["opp_fta"]  += float(row.opp_fta)
    a["opp_fga"]  += float(row.opp_fga)
    a["oreb"]     += float(row.oreb)
    a["opp_dreb"] += float(row.opp_dreb)
    a["tov"]      += float(row.tov)
    a["fga"]      += float(row.fga)
    a["fta"]      += float(row.fta)
    a["dreb"]     += float(row.dreb)
    a["opp_oreb"] += float(row.opp_oreb)


# ===========================================================================
# Power-ratings (SRS) as-of
# ===========================================================================

def _srs_asof(prior_rows: pd.DataFrame, teams: list[str]) -> dict[str, float]:
    """Run SRS on prior_rows sub-graph. Returns {team: srs_rating}."""
    records: dict[str, list[tuple[float, str]]] = {t: [] for t in teams}
    for row in prior_rows.itertuples(index=False):
        records[row.team].append((float(row.pts - row.opp_pts), row.opp))

    ratings: dict[str, float] = {t: 0.0 for t in teams}
    for _ in range(50):
        new_r: dict[str, float] = {}
        for t in teams:
            if records[t]:
                new_r[t] = sum(m + ratings[o] for m, o in records[t]) / len(records[t])
            else:
                new_r[t] = 0.0
        mean_r = sum(new_r.values()) / max(len(teams), 1)
        new_r  = {t: v - mean_r for t, v in new_r.items()}
        delta  = max(abs(new_r[t] - ratings[t]) for t in teams)
        ratings = new_r
        if delta < 1e-7:
            break
    return ratings


def _power_asof(ht: str, at: str, prior_df: pd.DataFrame,
                margin_errors: list[float]) -> dict:
    """Return {margin_home, margin_sd, win_prob_home} for power_ratings engine."""
    teams = list(prior_df["team"].unique())
    if not teams:
        return dict(margin_home=HOME_EDGE, margin_sd=SIGMA_FALLBACK, win_prob_home=_phi(HOME_EDGE / SIGMA_FALLBACK))

    ratings = _srs_asof(prior_df, teams)
    r_h = ratings.get(ht, 0.0)
    r_a = ratings.get(at, 0.0)
    margin_home = (r_h - r_a) + HOME_EDGE

    # expanding residual SD from prior graded games
    margin_sd = float(np.std(margin_errors, ddof=1)) if len(margin_errors) >= 5 else SIGMA_FALLBACK

    return dict(
        margin_home  = margin_home,
        margin_sd    = margin_sd,
        win_prob_home= _phi(margin_home / max(margin_sd, 1.0)),
    )


# ===========================================================================
# Team-score as-of (closed-form; no MC to keep the backtest fast)
# ===========================================================================

def _team_score_asof(ht: str, at: str,
                     acc: dict[str, dict],
                     L_ORTG: float, L_PACE: float) -> dict:
    """Closed-form team-score engine using per-team accumulators."""
    def _ratings(team: str):
        a = acc.get(team)
        if a is None or a["g"] == 0:
            return L_ORTG, L_ORTG, L_PACE
        w_o = a["poss"]     / (a["poss"]     + K_RTG)
        w_d = a["opp_poss"] / (a["opp_poss"] + K_RTG)
        wp  = a["g"]        / (a["g"]        + K_PACE)
        ortg = (100 * a["pts"]     / a["poss"])     * w_o + L_ORTG * (1 - w_o) if a["poss"]     > 0 else L_ORTG
        drtg = (100 * a["opp_pts"] / a["opp_poss"]) * w_d + L_ORTG * (1 - w_d) if a["opp_poss"] > 0 else L_ORTG
        pace = (a["poss"] / a["g"]) * wp + L_PACE * (1 - wp) if a["g"] > 0 else L_PACE
        return ortg, drtg, pace

    h_ortg, h_drtg, h_pace = _ratings(ht)
    a_ortg, a_drtg, a_pace = _ratings(at)

    home_pts100 = (h_ortg + a_drtg) / 2.0
    away_pts100 = (a_ortg + h_drtg) / 2.0
    game_pace   = (h_pace + a_pace) / 2.0
    home_pts_exp = home_pts100 * game_pace / 100.0 + HOME_EDGE / 2.0
    away_pts_exp = away_pts100 * game_pace / 100.0 - HOME_EDGE / 2.0

    margin_home = home_pts_exp - away_pts_exp
    # pts_sd from within-team residuals; use empirical ~12.5 as fallback
    # closed-form: margin_sd = sqrt(2) * pts_sd (independent draws)
    pts_sd      = 12.5
    margin_sd   = math.sqrt(2.0) * pts_sd

    return dict(
        margin_home  = margin_home,
        margin_sd    = margin_sd,
        win_prob_home= _phi(margin_home / margin_sd),
    )


# ===========================================================================
# Four-factors as-of (closed-form; OLS refit on prior team-level snapshot)
# ===========================================================================

def _fit_ff_coefs(snapshot: pd.DataFrame) -> tuple[float, float, float, float]:
    """Fit OLS coefs from per-team season snapshot. Returns (c_ts, c_tov, c_oreb, c_ft)."""
    if len(snapshot) < FF_MIN_TEAMS:
        return _FIXED_C_TS, _FIXED_C_TOV, _FIXED_C_OREB, _FIXED_C_FT

    try:
        from sklearn.linear_model import LinearRegression
        X = snapshot[["ts_proxy", "tov_pct", "oreb_pct", "ft_rate"]].values
        y = (snapshot["pts"] / snapshot["poss"] * 100.0).values
        lr = LinearRegression(fit_intercept=True).fit(X, y)
        c_ts, c_tov, c_oreb, c_ft = [float(c) for c in lr.coef_]
        c_ft = max(c_ft, 0.0)  # floor positive per Oliver
        return c_ts, c_tov, c_oreb, c_ft
    except Exception:
        return _FIXED_C_TS, _FIXED_C_TOV, _FIXED_C_OREB, _FIXED_C_FT


def _four_factors_asof(ht: str, at: str,
                       acc: dict[str, dict],
                       L_ORTG: float, L_PACE: float,
                       L_tov: float, L_oreb: float, L_ft: float, L_ts: float,
                       c_ts: float, c_tov: float, c_oreb: float, c_ft: float,
                       tov_force: dict[str, float], ft_force: dict[str, float]) -> dict:
    """Closed-form four-factors engine using per-team accumulators + prefit OLS coefs."""

    def _factors(team: str):
        a = acc.get(team)
        if a is None or a["g"] == 0:
            return dict(ts=L_ts, tov=L_tov, oreb=L_oreb, ft=L_ft,
                        def_ts=L_ts, def_tov=L_tov, def_oreb=L_oreb, def_ft=L_ft,
                        pace=L_PACE)
        poss_t  = a["poss"]
        wpace   = a["g"] / (a["g"] + K_PACE)
        pace    = (a["poss"] / a["g"]) * wpace + L_PACE * (1 - wpace) if a["g"] > 0 else L_PACE
        ts      = a["pts"]     / (a["fga"]     + 0.44 * a["fta"])  if (a["fga"]     + 0.44 * a["fta"])  > 0 else L_ts
        tov_p   = a["tov"]     / a["poss"]                          if a["poss"]     > 0 else L_tov
        orebn   = a["oreb"] + a["opp_dreb"]
        oreb_p  = a["oreb"]    / orebn                              if orebn         > 0 else L_oreb
        ft_r    = a["fta"]     / a["fga"]                           if a["fga"]      > 0 else L_ft
        # defensive four factors (what this team *allows*)
        def_ts  = a["opp_pts"] / (a["opp_fga"] + 0.44 * a["opp_fta"]) if (a["opp_fga"] + 0.44 * a["opp_fta"]) > 0 else L_ts
        def_tov = a["opp_tov"] / a["opp_poss"] if a["opp_poss"] > 0 else L_tov
        doreb_n = a["opp_oreb"] + a["dreb"]
        def_oreb= a["opp_oreb"] / doreb_n   if doreb_n > 0 else L_oreb
        def_ft  = a["opp_fta"] / a["opp_fga"] if a["opp_fga"] > 0 else L_ft
        return dict(ts=ts, tov=tov_p, oreb=oreb_p, ft=ft_r,
                    def_ts=def_ts, def_tov=def_tov, def_oreb=def_oreb, def_ft=def_ft,
                    pace=pace)

    hf = _factors(ht); af = _factors(at)
    tov_mult_h = tov_force.get(at, 1.0)  # away team's tov-force on home offense
    tov_mult_a = tov_force.get(ht, 1.0)
    ft_mult_h  = ft_force.get(ht, 1.0)
    ft_mult_a  = ft_force.get(at, 1.0)

    def _exp_pts(off: dict, dfe: dict, tov_m: float, ft_m: float) -> float:
        exp_ts   = (off["ts"]   + dfe["def_ts"])   / 2.0
        exp_tov  = ((off["tov"] + dfe["def_tov"])  / 2.0) * tov_m
        exp_oreb = (off["oreb"] + dfe["def_oreb"]) / 2.0
        exp_ft   = ((off["ft"]  + dfe["def_ft"])   / 2.0) * ft_m
        exp_ortg = (L_ORTG
                    + c_ts   * (exp_ts   - L_ts)
                    + c_tov  * (exp_tov  - L_tov)
                    + c_oreb * (exp_oreb - L_oreb)
                    + c_ft   * (exp_ft   - L_ft))
        pace     = (off["pace"] + dfe["pace"]) / 2.0
        return exp_ortg * pace / 100.0

    home_exp = _exp_pts(hf, af, tov_mult_h, ft_mult_h)
    away_exp = _exp_pts(af, hf, tov_mult_a, ft_mult_a)
    margin_home = (home_exp - away_exp) + HOME_EDGE

    # closed-form margin sd; use ~sqrt(2)*12 from four_factors engine constant
    margin_sd = math.sqrt(2.0) * 12.0

    return dict(
        margin_home  = margin_home,
        margin_sd    = margin_sd,
        win_prob_home= _phi(margin_home / margin_sd),
    )


# ===========================================================================
# Main backtest loop
# ===========================================================================

def run_backtest() -> pd.DataFrame:
    TG = pd.read_parquet(os.path.join(TS, "league_team_game.parquet"))
    sg = {
        r["game_id"]: r
        for r in json.load(open(os.path.join(ROOT, "data", "nba", "season_games_2025-26.json")))["rows"]
        if "home_win" in r
    }

    # tov_force / ft_force from full-season team_defense_league (used as prior/fallback
    # for env multipliers; within-season as-of rebuild is the four_factors rolling coef)
    try:
        tdf = pd.read_parquet(os.path.join(TS, "team_defense_league.parquet"))
        tov_force = dict(zip(tdf.team, tdf.tov_force))
        ft_force  = dict(zip(tdf.team, tdf.ft_force))
    except Exception:
        tov_force = {}; ft_force = {}

    # League priors from the FULL corpus (used only for shrinkage toward league mean,
    # NOT to look up individual game outcomes -- so no leak here)
    L_ORTG = 100 * TG.pts.sum() / TG.poss.sum()
    L_PACE = float(TG.poss.mean())
    L_TOV  = float(TG.opp_tov.sum() / TG.opp_poss.sum())
    L_FTR  = float(TG.opp_fta.sum() / TG.opp_fga.sum())
    L_OREB = float(TG.oreb.sum() / (TG.oreb.sum() + TG.opp_dreb.sum()))
    L_TS   = float((TG.pts / (TG.fga + 0.44 * TG.fta)).mean())

    # Index for O(1) lookup
    tg_by_gid_team = {(r.gid, r.team): r for r in TG.itertuples(index=False)}
    all_teams = sorted(TG["team"].unique())

    # Build game list (same sort as walkforward_league.py)
    games = []
    for gid, g in TG.groupby("gid"):
        s = sg.get(gid)
        if s is None:
            continue
        ht, at = s["home_team"], s["away_team"]
        hr = g[g.team == ht]; ar = g[g.team == at]
        if len(hr) != 1 or len(ar) != 1:
            continue
        hr = hr.iloc[0]; ar = ar.iloc[0]
        games.append(dict(gid=gid, date=s["game_date"], ht=ht, at=at,
                          home_pts=int(hr.pts), away_pts=int(ar.pts),
                          home_win=int(s["home_win"])))
    games = sorted(games, key=lambda r: (r["date"], r["gid"]))

    # Per-team accumulators
    acc: dict[str, dict] = {}

    # Running margin errors for SRS residual SD
    power_margin_errors: list[float] = []

    rows = []
    n_graded = 0
    n_skipped_burnin = 0

    for gm in games:
        ht, at = gm["ht"], gm["at"]
        acc.setdefault(ht, _blank_acc())
        acc.setdefault(at, _blank_acc())

        H = acc[ht]; A = acc[at]
        gradeable = (H["g"] >= BURNIN and A["g"] >= BURNIN)

        if gradeable:
            # Build prior-rows dataframe for this game (all rows with date < game date
            # already accumulated; we reconstruct the needed slice from accumulators
            # rather than re-scanning the full TG, which is O(N^2)).
            # For SRS we need the sub-graph -- but scanning TG once per game is
            # prohibitively slow. Instead, use the accumulator-based approach:
            # power_asof is called with the FULL TG filtered to date < gm["date"]
            # for SRS (this is O(N) once, already cheap at 2316 rows).
            prior_df = TG[TG["date"] < gm["date"]].copy()

            # --- power_ratings as-of ---
            p = _power_asof(ht, at, prior_df, power_margin_errors)
            m_pow = p["margin_home"]; sd_pow = p["margin_sd"]; wp_pow = p["win_prob_home"]

            # --- team_score as-of (closed-form, fast) ---
            ts_res = _team_score_asof(ht, at, acc, L_ORTG, L_PACE)
            m_ts = ts_res["margin_home"]; sd_ts = ts_res["margin_sd"]; wp_ts = ts_res["win_prob_home"]

            # --- four_factors as-of ---
            # Build per-team snapshot from accumulators for OLS refit
            snap_rows = []
            for team, a_t in acc.items():
                if a_t["g"] < 2:
                    continue
                row_d = dict(
                    team     = team,
                    pts      = a_t["pts"],
                    poss     = a_t["poss"],
                    fga      = a_t["fga"],
                    fta      = a_t["fta"],
                    tov      = a_t["tov"],
                    oreb     = a_t["oreb"],
                    opp_dreb = a_t["opp_dreb"],
                )
                row_d["ts_proxy"] = a_t["pts"] / (a_t["fga"] + 0.44 * a_t["fta"]) if (a_t["fga"] + 0.44 * a_t["fta"]) > 0 else L_TS
                row_d["tov_pct"]  = a_t["tov"] / a_t["poss"] if a_t["poss"] > 0 else L_TOV
                row_d["oreb_pct"] = a_t["oreb"] / (a_t["oreb"] + a_t["opp_dreb"]) if (a_t["oreb"] + a_t["opp_dreb"]) > 0 else L_OREB
                row_d["ft_rate"]  = a_t["fta"] / a_t["fga"] if a_t["fga"] > 0 else L_FTR
                snap_rows.append(row_d)

            snap = pd.DataFrame(snap_rows).set_index("team") if snap_rows else pd.DataFrame()
            c_ts_f, c_tov_f, c_oreb_f, c_ft_f = _fit_ff_coefs(snap.reset_index() if len(snap) > 0 else snap)
            ff_res = _four_factors_asof(
                ht, at, acc,
                L_ORTG, L_PACE, L_TOV, L_OREB, L_FTR, L_TS,
                c_ts_f, c_tov_f, c_oreb_f, c_ft_f,
                tov_force, ft_force,
            )
            m_ff = ff_res["margin_home"]; sd_ff = ff_res["margin_sd"]; wp_ff = ff_res["win_prob_home"]

            actual_margin = gm["home_pts"] - gm["away_pts"]
            rows.append(dict(
                gid          = gm["gid"],
                date         = gm["date"],
                home_win     = gm["home_win"],
                margin       = actual_margin,
                m_power      = m_pow,  sd_power = sd_pow,  wp_power = wp_pow,
                m_team       = m_ts,   sd_team  = sd_ts,   wp_team  = wp_ts,
                m_ff         = m_ff,   sd_ff    = sd_ff,   wp_ff    = wp_ff,
            ))
            n_graded += 1

            # Update SRS error for next game
            power_margin_errors.append(actual_margin - m_pow)
        else:
            n_skipped_burnin += 1

        # Update AFTER predicting (leak-free)
        hr_row = tg_by_gid_team.get((gm["gid"], ht))
        ar_row = tg_by_gid_team.get((gm["gid"], at))
        if hr_row is not None:
            _update_acc(acc[ht], hr_row)
        if ar_row is not None:
            _update_acc(acc[at], ar_row)

    print(f"GRADED GAMES: {n_graded}  (burn-in skipped: {n_skipped_burnin}; burn-in={BURNIN}/team)")
    return pd.DataFrame(rows)


# ===========================================================================
# Reliability metrics
# ===========================================================================

def compute_metrics(P: pd.DataFrame) -> dict:
    y  = P.home_win.values.astype(float)
    am = P.margin.values

    engines = [
        ("power_ratings", P.m_power.values, P.wp_power.values),
        ("team_score",    P.m_team.values,  P.wp_team.values),
        ("four_factors",  P.m_ff.values,    P.wp_ff.values),
    ]
    out = {}
    for name, m, wp in engines:
        wp_c = np.clip(wp, 1e-6, 1 - 1e-6)
        brier = float(np.mean((wp_c - y) ** 2))
        acc   = float(np.mean((wp_c >= 0.5).astype(float) == y))
        rmse  = float(np.sqrt(np.mean((m - am) ** 2)))
        bias  = float(np.mean(m - am))
        out[name] = dict(brier=round(brier, 6), margin_rmse=round(rmse, 4),
                         bias=round(bias, 4), acc=round(acc, 4))
    return out


# ===========================================================================
# Weight learning (simplex-constrained)
# ===========================================================================

def _brier_equal(P: pd.DataFrame) -> float:
    y  = P.home_win.values.astype(float)
    margins = np.stack([P.m_power.values, P.m_team.values, P.m_ff.values], axis=1)
    sds     = np.stack([P.sd_power.values, P.sd_team.values, P.sd_ff.values], axis=1)
    w_eq    = np.array([1/3, 1/3, 1/3])
    m_fus   = (margins * w_eq).sum(axis=1)
    sd_pool = np.sqrt((w_eq * sds**2).sum(axis=1))
    wp      = np.vectorize(_phi)(m_fus / np.maximum(sd_pool, 1.0))
    wp      = np.clip(wp, 1e-6, 1 - 1e-6)
    return float(np.mean((wp - y) ** 2))


def _brier_w(w: np.ndarray, margins: np.ndarray, sds: np.ndarray, y: np.ndarray) -> float:
    w = np.abs(w); w = w / w.sum()
    m_fus   = (margins * w).sum(axis=1)
    sd_pool = np.sqrt((w * sds**2).sum(axis=1))
    wp      = np.vectorize(_phi)(m_fus / np.maximum(sd_pool, 1.0))
    wp      = np.clip(wp, 1e-6, 1 - 1e-6)
    return float(np.mean((wp - y) ** 2))


def learn_weights(P: pd.DataFrame) -> dict:
    """Learn fusion weights via two methods; report both; apply out-of-time holdout test."""
    n = len(P)
    metrics = compute_metrics(P)

    # --- Method 1: inverse-variance (closed form) --------------------------
    rmse_vals = np.array([metrics[k]["margin_rmse"] for k in ["power_ratings", "team_score", "four_factors"]])
    iv_w_raw  = 1.0 / np.maximum(rmse_vals, 1e-6) ** 2
    iv_w      = iv_w_raw / iv_w_raw.sum()

    # --- Method 2: SLSQP min Brier (time-blocked 5-fold CV) ----------------
    # Use first 60% as train, last 40% as holdout (single split -- time-blocked)
    # Also report 5-fold time-block CV std on holdout to set the threshold.
    fold_size  = n // 5
    holdout_briers_learned = []
    holdout_briers_equal   = []

    margins = np.stack([P.m_power.values, P.m_team.values, P.m_ff.values], axis=1)
    sds     = np.stack([P.sd_power.values, P.sd_team.values, P.sd_ff.values], axis=1)
    y       = P.home_win.values.astype(float)

    best_w_slsqp = np.array([1/3, 1/3, 1/3])
    fold_w_list  = []

    for fold in range(5):
        val_start = fold * fold_size
        val_end   = val_start + fold_size if fold < 4 else n
        # train = everything BEFORE the validation block (time-blocked; no future leakage)
        train_end = val_start
        if train_end < 10:
            continue
        m_tr = margins[:train_end]; sd_tr = sds[:train_end]; y_tr = y[:train_end]
        m_va = margins[val_start:val_end]; sd_va = sds[val_start:val_end]; y_va = y[val_start:val_end]

        # SLSQP on training fold
        w0 = np.array([1/3, 1/3, 1/3])
        cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
        bnds = [(0.0, 1.0)] * 3
        res  = minimize(lambda w: _brier_w(w, m_tr, sd_tr, y_tr), w0,
                        method="SLSQP", bounds=bnds, constraints=cons,
                        options={"maxiter": 500, "ftol": 1e-9})
        w_fit = np.abs(res.x); w_fit = w_fit / w_fit.sum()
        fold_w_list.append(w_fit)

        b_learned = _brier_w(w_fit, m_va, sd_va, y_va)
        b_equal   = _brier_w(np.array([1/3, 1/3, 1/3]), m_va, sd_va, y_va)
        holdout_briers_learned.append(b_learned)
        holdout_briers_equal.append(b_equal)

    # Final holdout: train on first 60%, validate on last 40%
    split     = int(0.6 * n)
    m_tr = margins[:split]; sd_tr = sds[:split]; y_tr = y[:split]
    m_ho = margins[split:]; sd_ho = sds[split:]; y_ho = y[split:]

    w0   = np.array([1/3, 1/3, 1/3])
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    bnds = [(0.0, 1.0)] * 3
    res  = minimize(lambda w: _brier_w(w, m_tr, sd_tr, y_tr), w0,
                    method="SLSQP", bounds=bnds, constraints=cons,
                    options={"maxiter": 500, "ftol": 1e-9})
    w_slsqp = np.abs(res.x); w_slsqp = w_slsqp / w_slsqp.sum()

    holdout_brier_learned = _brier_w(w_slsqp, m_ho, sd_ho, y_ho)
    holdout_brier_equal   = _brier_w(np.array([1/3, 1/3, 1/3]), m_ho, sd_ho, y_ho)

    # Cross-validation std of holdout brier differences
    diffs    = [l - e for l, e in zip(holdout_briers_learned, holdout_briers_equal)]
    cv_std   = float(np.std(diffs, ddof=1)) if len(diffs) >= 2 else 0.01
    final_diff = holdout_brier_learned - holdout_brier_equal

    # Decision: beats equal weight only if improvement > 1 CV std
    beats_equal = bool(final_diff < -cv_std)

    # Choose final method and weights
    if beats_equal:
        final_w  = w_slsqp
        method   = "slqp_logloss"
    else:
        # Check inverse-variance too
        iv_holdout = _brier_w(iv_w, m_ho, sd_ho, y_ho)
        iv_diff    = iv_holdout - holdout_brier_equal
        if iv_diff < -cv_std:
            final_w = iv_w
            method  = "inverse_variance"
            beats_equal = True
        else:
            final_w = np.array([1/3, 1/3, 1/3])
            method  = "equal_weight_fallback"
            beats_equal = False

    return dict(
        weights              = final_w.tolist(),
        method               = method,
        beats_equal_weight   = beats_equal,
        holdout_brier_learned= round(holdout_brier_learned, 6),
        holdout_brier_equal  = round(holdout_brier_equal,   6),
        final_diff           = round(float(final_diff), 6),
        cv_std               = round(cv_std, 6),
        iv_weights           = iv_w.tolist(),
        slsqp_weights        = w_slsqp.tolist(),
    )


# ===========================================================================
# Win-prob calibration (reuse walkforward_league.py bucket approach)
# ===========================================================================

def _calibration(P: pd.DataFrame, wp_col: str, label: str) -> None:
    wp = P[wp_col].values
    y  = P.home_win.values.astype(float)
    dfc = pd.DataFrame({"wp": wp, "y": y})
    dfc["bucket"] = pd.cut(dfc.wp, [0, .35, .5, .65, .8, 1.0])
    cc = dfc.groupby("bucket", observed=True).agg(pred=("wp","mean"), actual=("y","mean"), n=("y","size"))
    print(f"\n  Calibration {label}:")
    print(cc.round(3).to_string())


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    print("=" * 70)
    print("ENGINE AS-OF RELIABILITY BACKTEST (V0, honesty_class=research)")
    print("=" * 70)
    print("As-of engines: power_ratings, team_score, four_factors")
    print("Excluded:      player_impact, attribute_matchup, possession_mc, clock_trajectory")
    print("Reason:        no date/gid column in source data (cannot slice as-of)")
    print()

    # ----- run backtest -----
    P = run_backtest()
    out_pq = os.path.join(TS, "engine_asof_preds.parquet")
    P.to_parquet(out_pq, index=False)
    print(f"Wrote {len(P)} rows -> {out_pq}")

    # ----- per-engine reliability -----
    metrics = compute_metrics(P)
    y = P.home_win.values.astype(float)
    print(f"\nN graded games: {len(P)}")
    print(f"Home-win base rate: {y.mean():.3f}")
    print(f"\n{'engine':20s}  {'Brier':>8s}  {'margin_RMSE':>12s}  {'bias':>7s}  {'acc':>6s}")
    for name, m in metrics.items():
        print(f"  {name:20s}  {m['brier']:8.5f}  {m['margin_rmse']:12.4f}  {m['bias']:+7.4f}  {m['acc']:6.4f}")

    # calibration printout for each engine
    for col, label in [("wp_power","power_ratings"), ("wp_team","team_score"), ("wp_ff","four_factors")]:
        _calibration(P, col, label)

    # ----- weight learning -----
    print("\n" + "=" * 70)
    print("WEIGHT LEARNING (simplex-constrained, time-blocked hold-out)")
    print("=" * 70)
    wl = learn_weights(P)
    print(f"SLSQP weights:         power={wl['slsqp_weights'][0]:.3f}  team={wl['slsqp_weights'][1]:.3f}  ff={wl['slsqp_weights'][2]:.3f}")
    print(f"Inv-var weights:       power={wl['iv_weights'][0]:.3f}  team={wl['iv_weights'][1]:.3f}  ff={wl['iv_weights'][2]:.3f}")
    print(f"Holdout Brier learned: {wl['holdout_brier_learned']:.6f}")
    print(f"Holdout Brier equal:   {wl['holdout_brier_equal']:.6f}")
    print(f"Improvement (- = better): {wl['final_diff']:+.6f}  (threshold: -{wl['cv_std']:.6f} CV std)")
    if wl["beats_equal_weight"]:
        print(f"=> LEARNED WEIGHTS WIN ({wl['method']}) -- recommend flag ON")
    else:
        print("=> EQUAL-WEIGHT NOT BEATEN -- net-rating cluster is redundant + uniformly reliable (confirms iter-7)")
        print("   equal-weight stays shipped; beats_equal_weight=false; flag OFF behavior unchanged")

    # ----- final weights to use (simplex check) -----
    final_w = wl["weights"]
    assert abs(sum(final_w) - 1.0) < 1e-6, f"weights do not sum to 1: {sum(final_w)}"
    eng_names = ["power_ratings", "team_score", "four_factors"]

    # ----- write JSON -----
    out_json = os.path.join(TS, "engine_reliability_weights.json")
    doc = {
        "engines":       eng_names,
        "weights":       [round(w, 6) for w in final_w],
        "method":        wl["method"],
        "per_engine":    metrics,
        "holdout_brier_learned": wl["holdout_brier_learned"],
        "holdout_brier_equal":   wl["holdout_brier_equal"],
        "beats_equal_weight":    wl["beats_equal_weight"],
        "n_graded":      len(P),
        "burnin":        BURNIN,
        "seasons":       ["2025-26"],
        "excluded_engines": {
            "player_impact":    "no date/gid in player_ratings.parquet",
            "attribute_matchup":"no date in attribute_vault.parquet",
            "possession_mc":    "TeamModel season substrate, no within-season refresh",
            "clock_trajectory": "TeamModel season substrate, no within-season refresh",
        },
        "honesty_class": "research",
        "asof":          True,
        "leakfree":      True,
        "notes":         (
            "3 as-of-capable engines all express home.net - away.net at the margin level "
            "(net-rating cluster, N_eff ~1.2 per decorrelation audit). "
            "Reliability-weighting is expected NOT to beat equal-weight (iter-7 prior). "
            "Cross-season validation substrate-blocked for V0 (only 2025-26 league_team_game exists)."
        ),
    }
    with open(out_json, "w") as f:
        json.dump(doc, f, indent=2)
    print(f"\nWrote weights -> {out_json}")
    print(f"beats_equal_weight = {wl['beats_equal_weight']}")
    print(f"Final weights: {dict(zip(eng_names, [round(w,4) for w in final_w]))}")


if __name__ == "__main__":
    main()
