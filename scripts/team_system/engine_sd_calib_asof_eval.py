"""engine_sd_calib_asof_eval.py -- OFF vs ON as-of win-prob reliability eval for
CV_ENGINE_SD_CALIB (V0b).  honesty_class = research.

PURPOSE
-------
The shipped engines (engine_team_score, engine_four_factors) gain a gated path
(CV_ENGINE_SD_CALIB=1) that replaces a hardcoded per-team draw SD with an
EMPIRICAL margin-SD computed from the engine's own (actual - predicted) margin
residuals -- the same residual approach engine_power_ratings already uses.

This script measures whether that calibrated SD actually IMPROVES the win-prob
Brier of each engine, LEAK-FREE (as-of), and whether fusion reliability-weighting
beats equal-weight once all 3 engines are calibrated.

LEAK-FREE GUARANTEE
-------------------
We reuse the exact as-of substrate from engine_asof_backtest.py (imported, not
copied): the same accumulators, burn-in, game ordering, and MARGIN POINTS.  The
margin point is IDENTICAL OFF and ON -- only the SD (=> win-prob) changes.

The calibrated SD for each engine is an EXPANDING / PRIOR-GAMES-ONLY empirical
margin-error SD: at game t we use std(margin_errors over graded games 0..t-1).
This mirrors how engine_asof_backtest._power_asof already derives power_ratings'
SD (`power_margin_errors`) and is the as-of analog of the engine's full-season
_compute_margin_sd_calib / _build_factors().margin_sd (which is the convergent
value of this same expanding estimate over all rows).

OFF path uses the engine's hardcoded constants:
    team_score   : margin_sd = sqrt(2) * 12.5   (~17.68)
    four_factors : margin_sd = sqrt(2) * 12.0    (~16.97)
    power_ratings: already calibrated (no constant OFF path) -- reported for ref.

Usage:
    python scripts/team_system/engine_sd_calib_asof_eval.py
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

# Import the as-of substrate (READ-ONLY use -- we do not modify it).
import engine_asof_backtest as B  # noqa: E402

TS = B.TS

# OFF-path constants (must match the engines' hardcoded OFF SD exactly).
OFF_SD_TEAM = math.sqrt(2.0) * 12.5   # engine_team_score _FALLBACK / OFF per-team 12.5
OFF_SD_FF   = math.sqrt(2.0) * 12.0   # engine_four_factors TEAM_TOTAL_SD = 12.0
SIGMA_FALLBACK = B.SIGMA_FALLBACK      # prior before enough graded games (13.0)
MIN_PRIOR = 30                          # min prior graded games before trusting calibrated SD


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def run_asof() -> pd.DataFrame:
    """Walk-forward over the same games as engine_asof_backtest.run_backtest(),
    but additionally track per-engine EXPANDING margin-error SDs (leak-free) so we
    can score OFF (constant SD) vs ON (calibrated SD) win-prob for each engine.

    The MARGIN POINTS (m_power/m_team/m_ff) are computed by the SAME functions
    used by engine_asof_backtest, so they are identical to the shipped backtest.
    """
    TG = pd.read_parquet(os.path.join(TS, "league_team_game.parquet"))
    sg = {
        r["game_id"]: r
        for r in json.load(open(os.path.join(ROOT, "data", "nba", "season_games_2025-26.json")))["rows"]
        if "home_win" in r
    }

    try:
        tdf = pd.read_parquet(os.path.join(TS, "team_defense_league.parquet"))
        tov_force = dict(zip(tdf.team, tdf.tov_force))
        ft_force  = dict(zip(tdf.team, tdf.ft_force))
    except Exception:
        tov_force = {}
        ft_force = {}

    L_ORTG = 100 * TG.pts.sum() / TG.poss.sum()
    L_PACE = float(TG.poss.mean())
    L_TOV  = float(TG.opp_tov.sum() / TG.opp_poss.sum())
    L_FTR  = float(TG.opp_fta.sum() / TG.opp_fga.sum())
    L_OREB = float(TG.oreb.sum() / (TG.oreb.sum() + TG.opp_dreb.sum()))
    L_TS   = float((TG.pts / (TG.fga + 0.44 * TG.fta)).mean())

    tg_by_gid_team = {(r.gid, r.team): r for r in TG.itertuples(index=False)}

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

    acc: dict[str, dict] = {}

    # Expanding margin-error stores -- PRIOR GRADED GAMES ONLY (leak-free).
    err_power: list[float] = []
    err_team:  list[float] = []
    err_ff:    list[float] = []

    rows = []
    for gm in games:
        ht, at = gm["ht"], gm["at"]
        acc.setdefault(ht, B._blank_acc())
        acc.setdefault(at, B._blank_acc())
        H = acc[ht]; A = acc[at]
        gradeable = (H["g"] >= B.BURNIN and A["g"] >= B.BURNIN)

        if gradeable:
            prior_df = TG[TG["date"] < gm["date"]].copy()

            # ----- margin POINTS: identical to engine_asof_backtest -----
            p = B._power_asof(ht, at, prior_df, err_power)
            m_pow = p["margin_home"]

            ts_res = B._team_score_asof(ht, at, acc, L_ORTG, L_PACE)
            m_ts = ts_res["margin_home"]

            snap_rows = []
            for team, a_t in acc.items():
                if a_t["g"] < 2:
                    continue
                row_d = dict(team=team)
                denom_ts = a_t["fga"] + 0.44 * a_t["fta"]
                row_d["ts_proxy"] = a_t["pts"] / denom_ts if denom_ts > 0 else L_TS
                row_d["tov_pct"]  = a_t["tov"] / a_t["poss"] if a_t["poss"] > 0 else L_TOV
                orb_n = a_t["oreb"] + a_t["opp_dreb"]
                row_d["oreb_pct"] = a_t["oreb"] / orb_n if orb_n > 0 else L_OREB
                row_d["ft_rate"]  = a_t["fta"] / a_t["fga"] if a_t["fga"] > 0 else L_FTR
                row_d["pts"]  = a_t["pts"]
                row_d["poss"] = a_t["poss"]
                snap_rows.append(row_d)
            snap = pd.DataFrame(snap_rows) if snap_rows else pd.DataFrame()
            c_ts_f, c_tov_f, c_oreb_f, c_ft_f = B._fit_ff_coefs(snap)
            ff_res = B._four_factors_asof(
                ht, at, acc,
                L_ORTG, L_PACE, L_TOV, L_OREB, L_FTR, L_TS,
                c_ts_f, c_tov_f, c_oreb_f, c_ft_f,
                tov_force, ft_force,
            )
            m_ff = ff_res["margin_home"]

            # ----- SD: OFF (constant) vs ON (expanding calibrated, prior-only) -----
            # power_ratings: already calibrated (expanding) in both -- reported as ref.
            sd_pow_on = float(np.std(err_power, ddof=1)) if len(err_power) >= 5 else SIGMA_FALLBACK
            sd_pow_off = sd_pow_on  # power has no constant OFF path

            sd_team_off = OFF_SD_TEAM
            sd_team_on  = float(np.std(err_team, ddof=1)) if len(err_team) >= MIN_PRIOR else OFF_SD_TEAM

            sd_ff_off = OFF_SD_FF
            sd_ff_on  = float(np.std(err_ff, ddof=1)) if len(err_ff) >= MIN_PRIOR else OFF_SD_FF

            actual_margin = gm["home_pts"] - gm["away_pts"]
            rows.append(dict(
                gid=gm["gid"], date=gm["date"], home_win=gm["home_win"], margin=actual_margin,
                m_power=m_pow, m_team=m_ts, m_ff=m_ff,
                sd_power_off=sd_pow_off, sd_power_on=sd_pow_on,
                sd_team_off=sd_team_off, sd_team_on=sd_team_on,
                sd_ff_off=sd_ff_off, sd_ff_on=sd_ff_on,
            ))

            # update expanding error stores AFTER predicting (leak-free)
            err_power.append(actual_margin - m_pow)
            err_team.append(actual_margin - m_ts)
            err_ff.append(actual_margin - m_ff)

        hr_row = tg_by_gid_team.get((gm["gid"], ht))
        ar_row = tg_by_gid_team.get((gm["gid"], at))
        if hr_row is not None:
            B._update_acc(acc[ht], hr_row)
        if ar_row is not None:
            B._update_acc(acc[at], ar_row)

    return pd.DataFrame(rows)


def _brier(margin, sd, y):
    sd = np.maximum(sd, 1.0)
    wp = np.array([_phi(m / s) for m, s in zip(margin, sd)])
    wp = np.clip(wp, 1e-6, 1 - 1e-6)
    return float(np.mean((wp - y) ** 2)), wp


def per_engine_off_on(P: pd.DataFrame) -> dict:
    y = P.home_win.values.astype(float)
    out = {}
    for name, mcol, sdoff, sdon in [
        ("power_ratings", "m_power", "sd_power_off", "sd_power_on"),
        ("team_score",    "m_team",  "sd_team_off",  "sd_team_on"),
        ("four_factors",  "m_ff",    "sd_ff_off",    "sd_ff_on"),
    ]:
        m = P[mcol].values
        b_off, wp_off = _brier(m, P[sdoff].values, y)
        b_on, wp_on   = _brier(m, P[sdon].values,  y)
        acc_off = float(np.mean((wp_off >= 0.5) == y))
        acc_on  = float(np.mean((wp_on >= 0.5) == y))
        out[name] = dict(
            brier_off=round(b_off, 6), brier_on=round(b_on, 6),
            delta=round(b_on - b_off, 6),
            acc_off=round(acc_off, 4), acc_on=round(acc_on, 4),
            mean_sd_off=round(float(P[sdoff].mean()), 3),
            mean_sd_on=round(float(P[sdon].mean()), 3),
        )
    return out


def fusion_off_vs_on(P: pd.DataFrame) -> dict:
    """Equal-weight vs reliability-weight (inverse-variance + SLSQP), with the ON
    (calibrated) SDs.  Time-blocked 60/40 holdout, identical scheme to the shipped
    engine_asof_backtest.learn_weights so the comparison is apples-to-apples."""
    y = P.home_win.values.astype(float)
    n = len(P)
    margins = np.stack([P.m_power.values, P.m_team.values, P.m_ff.values], axis=1)
    sds_on  = np.stack([P.sd_power_on.values, P.sd_team_on.values, P.sd_ff_on.values], axis=1)
    sds_off = np.stack([P.sd_power_off.values, P.sd_team_off.values, P.sd_ff_off.values], axis=1)

    def _fus_brier(w, m, sd, yy):
        w = np.abs(w); w = w / w.sum()
        m_fus = (m * w).sum(axis=1)
        sd_pool = np.sqrt((w * sd ** 2).sum(axis=1))
        wp = np.array([_phi(a / max(b, 1.0)) for a, b in zip(m_fus, sd_pool)])
        wp = np.clip(wp, 1e-6, 1 - 1e-6)
        return float(np.mean((wp - yy) ** 2))

    def _corr_report(sd_stack):
        # margin correlation across engines (redundancy check)
        c = np.corrcoef(margins.T)
        return float(np.mean([c[0, 1], c[0, 2], c[1, 2]]))

    mean_margin_corr = _corr_report(sds_on)

    results = {}
    for tag, sds in [("on", sds_on), ("off", sds_off)]:
        split = int(0.6 * n)
        m_tr, sd_tr, y_tr = margins[:split], sds[:split], y[:split]
        m_ho, sd_ho, y_ho = margins[split:], sds[split:], y[split:]

        w0 = np.array([1/3, 1/3, 1/3])
        cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
        bnds = [(0.0, 1.0)] * 3
        res = minimize(lambda w: _fus_brier(w, m_tr, sd_tr, y_tr), w0,
                       method="SLSQP", bounds=bnds, constraints=cons,
                       options={"maxiter": 500, "ftol": 1e-9})
        w_slsqp = np.abs(res.x); w_slsqp = w_slsqp / w_slsqp.sum()

        # inverse-variance: weight each engine by 1 / (its mean train SD)^2
        iv_raw = 1.0 / np.maximum(sd_tr.mean(axis=0), 1e-6) ** 2
        iv_w = iv_raw / iv_raw.sum()

        b_eq      = _fus_brier(np.array([1/3, 1/3, 1/3]), m_ho, sd_ho, y_ho)
        b_slsqp   = _fus_brier(w_slsqp, m_ho, sd_ho, y_ho)
        b_iv      = _fus_brier(iv_w, m_ho, sd_ho, y_ho)
        results[tag] = dict(
            holdout_brier_equal=round(b_eq, 6),
            holdout_brier_slsqp=round(b_slsqp, 6),
            holdout_brier_invvar=round(b_iv, 6),
            slsqp_weights=[round(x, 4) for x in w_slsqp],
            iv_weights=[round(x, 4) for x in iv_w],
            slsqp_beats_equal=bool(b_slsqp < b_eq - 1e-9),
            invvar_beats_equal=bool(b_iv < b_eq - 1e-9),
        )
    results["mean_margin_corr"] = round(mean_margin_corr, 4)
    results["n_graded"] = n
    return results


def main():
    print("=" * 74)
    print("CV_ENGINE_SD_CALIB  OFF vs ON  as-of win-prob reliability eval (V0b)")
    print("honesty_class=research | leak-free expanding prior-only calibrated SD")
    print("=" * 74)

    P = run_asof()
    print(f"\nN graded games: {len(P)}  | home-win base rate: {P.home_win.mean():.3f}")

    pe = per_engine_off_on(P)
    print(f"\n{'engine':16s} {'BrierOFF':>9s} {'BrierON':>9s} {'delta':>9s} "
          f"{'accOFF':>7s} {'accON':>7s} {'sdOFF':>7s} {'sdON':>7s}")
    for name, d in pe.items():
        print(f"{name:16s} {d['brier_off']:9.5f} {d['brier_on']:9.5f} {d['delta']:+9.5f} "
              f"{d['acc_off']:7.4f} {d['acc_on']:7.4f} {d['mean_sd_off']:7.2f} {d['mean_sd_on']:7.2f}")

    fu = fusion_off_vs_on(P)
    print(f"\nmean pairwise margin correlation across 3 engines: {fu['mean_margin_corr']:.4f}")
    for tag in ["off", "on"]:
        r = fu[tag]
        print(f"\n--- FUSION [{tag.upper()} SDs] (60/40 time-blocked holdout) ---")
        print(f"  equal-weight Brier : {r['holdout_brier_equal']:.6f}")
        print(f"  SLSQP Brier        : {r['holdout_brier_slsqp']:.6f}  w={r['slsqp_weights']}  beats_eq={r['slsqp_beats_equal']}")
        print(f"  inv-var Brier      : {r['holdout_brier_invvar']:.6f}  w={r['iv_weights']}  beats_eq={r['invvar_beats_equal']}")

    out = dict(per_engine=pe, fusion=fu, n_graded=len(P), honesty_class="research",
               leakfree=True, asof=True,
               note=("calibrated SD = expanding prior-only empirical margin-error SD "
                     "(same residual approach as engine_power_ratings); margin POINT identical OFF/ON"))
    outp = os.path.join(TS, "engine_sd_calib_asof_eval.json")
    with open(outp, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {outp}")
    return out


if __name__ == "__main__":
    main()
