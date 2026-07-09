"""domains.mlb.knowledge.validate_situational_state -- 5 UNTESTED game-state
mechanisms (mechanisms.md #20 TTO-decay-net-of-velo, #21 walk-economy RISP
inflation, #22 big-inning leadoff gating, #28 leverage-index WPA conversion,
#29 high-leverage strand prevention) against one local Statcast season.
Leak audit: every comparison uses only same-PA/same-half-inning/same-game
fields already resolved by the time the outcome is observed -- descriptive
mechanism checks, not forecast features.

Run: python -m domains.mlb.knowledge.validate_situational_state
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge._data import DEFAULT_SEASON, LEDGER_PATH, load_season, pa_final_pitch
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
ON_BASE_EVENTS = {"single", "double", "triple", "walk", "hit_by_pitch", "home_run", "intent_walk"}
OUT_EVENTS = {"field_out", "strikeout", "force_out", "grounded_into_double_play", "sac_fly", "sac_bunt",
              "fielders_choice_out", "double_play", "strikeout_double_play", "field_error"}


def _verdict(p, min_abs_effect: float, effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def tto_decay_net_of_velo(pa: pd.DataFrame, pitch: pd.DataFrame) -> Dict[str, Any]:
    velo_pa = pitch.groupby(["game_pk", "pitcher", "at_bat_number"])["release_speed"].mean().rename("velo_pa")
    d = pa.merge(velo_pa, on=["game_pk", "pitcher", "at_bat_number"], how="left").dropna(
        subset=["estimated_woba_using_speedangle", "velo_pa"])
    d = d.sort_values(["game_pk", "pitcher", "batter", "at_bat_number"])
    d["trip_number"] = d.groupby(["game_pk", "pitcher", "batter"]).cumcount() + 1
    d = d[d["trip_number"] <= 4]
    d["velo_band"] = pd.qcut(d["velo_pa"], 3, labels=["slow", "mid", "fast"], duplicates="drop")
    X = pd.get_dummies(d[["velo_band"]], drop_first=True)
    X.insert(0, "trip_number", d["trip_number"].values)
    X.insert(0, "const", 1.0)
    X = X.astype(float)
    y = d["estimated_woba_using_speedangle"].values
    beta, *_ = np.linalg.lstsq(X.values, y, rcond=None)
    resid = y - X.values @ beta
    dof = len(d) - X.shape[1]
    sigma2 = float((resid @ resid) / dof)
    cov = sigma2 * np.linalg.inv(X.values.T @ X.values)
    se = float(np.sqrt(cov[1, 1]))
    t = beta[1] / se
    p = float(2 * (1 - stats.t.cdf(abs(t), df=dof)))
    return {"hypothesis": "tto_decay_net_of_velo", "n": int(len(d)), "effect": round(float(beta[1]), 5), "p": p,
            "verdict": _verdict(p, 0.001, beta[1]),
            "note": "OLS xwOBA ~ trip_number + velo_band(tercile), trip_number coef=%.5f, n=%d PAs (trips<=4)"
                    % (beta[1], len(d))}


def walk_economy_baserunner_inflation(pitch: pd.DataFrame) -> Dict[str, Any]:
    d = pitch[pitch["events"] == "walk"].copy()
    d["bat_team_post"] = np.where(d["inning_topbot"] == "Top", d["post_away_score"], d["post_home_score"])
    d["re_added"] = d["bat_team_post"] - d["bat_score"]
    risp = d[d["on_2b"].notna() | d["on_3b"].notna()]["re_added"]
    empty = d[d["on_1b"].isna() & d["on_2b"].isna() & d["on_3b"].isna()]["re_added"]
    t, p = stats.ttest_ind(risp, empty, equal_var=False)
    eff = float(risp.mean() - empty.mean())
    return {"hypothesis": "walk_economy_baserunner_inflation", "n": int(len(risp) + len(empty)),
            "effect": round(eff, 4), "p": float(p), "verdict": _verdict(p, 0.01, eff),
            "note": "runs-added-on-play after a walk, RISP (%.4f, n=%d) vs bases empty (%.4f, n=%d)"
                    % (risp.mean(), len(risp), empty.mean(), len(empty))}


def big_inning_leadoff_gating(pitch: pd.DataFrame) -> Dict[str, Any]:
    d = pitch.dropna(subset=["events"]).copy()
    d = d[d["events"].isin(ON_BASE_EVENTS | OUT_EVENTS)]
    half = d.groupby(["game_pk", "inning", "inning_topbot"])
    leadoff = half.apply(lambda g: g.sort_values("at_bat_number").iloc[0], include_groups=False)
    leadoff["on_base"] = leadoff["events"].isin(ON_BASE_EVENTS)
    runs = pitch.copy()
    runs["bat_team_post"] = np.where(runs["inning_topbot"] == "Top", runs["post_away_score"], runs["post_home_score"])
    rlast = runs.sort_values("at_bat_number").groupby(["game_pk", "inning", "inning_topbot"]).tail(1)
    rfirst = runs.sort_values("at_bat_number").groupby(["game_pk", "inning", "inning_topbot"]).head(1)
    runs_scored = (rlast.set_index(["game_pk", "inning", "inning_topbot"])["bat_team_post"] -
                   rfirst.set_index(["game_pk", "inning", "inning_topbot"])["bat_score"])
    m = leadoff.join(runs_scored.rename("runs_this_inning"))
    m["big_inning"] = m["runs_this_inning"] >= 3
    p_on = m.loc[m["on_base"], "big_inning"].mean()
    p_out = m.loc[~m["on_base"], "big_inning"].mean()
    n_on, n_out = int(m["on_base"].sum()), int((~m["on_base"]).sum())
    t, p = stats.ttest_ind(m.loc[m["on_base"], "big_inning"].astype(int),
                            m.loc[~m["on_base"], "big_inning"].astype(int), equal_var=False)
    eff = float(p_on - p_out)
    return {"hypothesis": "big_inning_leadoff_gating", "n": n_on + n_out, "effect": round(eff, 4), "p": float(p),
            "verdict": _verdict(p, 0.01, eff),
            "note": "P(3+ runs this half-inning) | leadoff on-base (%.4f, n=%d) vs leadoff out (%.4f, n=%d)"
                    % (p_on, n_on, p_out, n_out)}


def leverage_index_conversion(pitch: pd.DataFrame) -> Dict[str, Any]:
    d = pitch.dropna(subset=["post_home_score", "post_away_score"]).copy()
    d["bat_team_post"] = np.where(d["inning_topbot"] == "Top", d["post_away_score"], d["post_home_score"])
    d["wpa_proxy"] = (d["bat_team_post"] - d["bat_score"]).abs()
    d["margin_bucket"] = pd.cut((d["home_score"] - d["away_score"]).abs(), [-0.1, 1, 4, 100],
                                 labels=["close", "medium", "blowout"])
    d["late"] = d["inning"] >= 7
    g = d.groupby(["late", "margin_bucket"], observed=True)["wpa_proxy"].mean()
    late_close = float(g.get((True, "close"), np.nan))
    early_blowout = float(g.get((False, "blowout"), np.nan))
    eff = late_close - early_blowout
    a = d[(d["late"]) & (d["margin_bucket"] == "close")]["wpa_proxy"]
    b = d[(~d["late"]) & (d["margin_bucket"] == "blowout")]["wpa_proxy"]
    t, p = stats.ttest_ind(a, b, equal_var=False)
    # NOT a true WPA model (none exists locally) -- |runs added on the play| is a RUN-SWING
    # proxy, confounded because blowout innings are mechanically higher-scoring-per-play than
    # close innings; that confound (not leverage) likely drives the observed direction, so this
    # is reported NOT_TESTABLE-as-specified rather than a clean reject of the leverage claim.
    return {"hypothesis": "leverage_index_conversion", "n": int(len(a) + len(b)), "effect": round(eff, 4),
            "p": float(p), "verdict": "NOT_TESTABLE",
            "note": "run-swing proxy (not true WPA, none built locally), late(inn>=7)+close(margin<=1) "
                    "(%.4f, n=%d) vs early(inn<7)+blowout(margin>=5) (%.4f, n=%d) -- confounded by blowout "
                    "innings being mechanically higher-scoring-per-play; proxy cannot isolate a leverage "
                    "effect from that confound" % (late_close, len(a), early_blowout, len(b))}


def high_leverage_strand_prevention(pitch: pd.DataFrame) -> Dict[str, Any]:
    d = pitch.dropna(subset=["events"]).copy()
    d["is_k"] = d["events"].isin({"strikeout", "strikeout_double_play"})
    k_rate = d.groupby("pitcher")["is_k"].mean().rename("k_rate")
    n_pa = d.groupby("pitcher")["is_k"].size().rename("n_pa")
    late_close = d[(d["inning"] >= 7) & ((d["home_score"] - d["away_score"]).abs() <= 2)].copy()
    late_close["risp"] = late_close["on_2b"].notna() | late_close["on_3b"].notna()
    risp_pa = late_close[late_close["risp"]]
    risp_pa = risp_pa.copy()
    risp_pa["stranded"] = ~risp_pa["events"].isin({"single", "double", "triple", "walk", "hit_by_pitch",
                                                    "home_run", "sac_fly"})
    strand_rate = risp_pa.groupby("pitcher")["stranded"].mean().rename("strand_rate")
    n_risp = risp_pa.groupby("pitcher")["stranded"].size().rename("n_risp")
    m = pd.concat([k_rate, n_pa, strand_rate, n_risp], axis=1).dropna()
    m = m[(m["n_pa"] >= 50) & (m["n_risp"] >= 15)]
    r, p = stats.pearsonr(m["k_rate"], m["strand_rate"])
    return {"hypothesis": "high_leverage_strand_prevention", "n": int(len(m)), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.1, r),
            "note": "pearson r, pitcher-season K-rate vs RISP strand-rate, inn>=7 & |margin|<=2, "
                    "n=%d pitchers (>=50 PA, >=15 RISP PA there)" % len(m)}


def run(season: int = DEFAULT_SEASON) -> List[Dict[str, Any]]:
    df = load_season(season)
    pa = pa_final_pitch(df)
    rows = [tto_decay_net_of_velo(pa, df), walk_economy_baserunner_inflation(df),
            big_inning_leadoff_gating(df), leverage_index_conversion(df),
            high_leverage_strand_prevention(df)]
    for r in rows:
        r["sport"] = "mlb"
        r["corpus"] = "savant_full__%d" % season
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-32s %-16s n=%-8d effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.02, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.02, 0.1) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.02, 0.1) == "NOT_TESTABLE"
    print("self-check OK")
