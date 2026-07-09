"""domains.mlb.knowledge.validate_persistence_skill -- 6 UNTESTED skill/
persistence mechanisms (mechanisms.md #24 ISO/strand-variance compression,
#26 defensive-efficiency conversion, #27 pitch-efficiency/durability, #32
catcher game-calling persistence, #33 spin-rate deception, #34 sweet-spot
consistency) against one local Statcast season. Leak audit: split-half
designs reuse the #15 pattern (descriptive within-season stability, not a
forecast feature); cross-sectional team/pitcher aggregates are season-level
comparisons across entities, not per-game features.

Run: python -m domains.mlb.knowledge.validate_persistence_skill
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge._data import DEFAULT_SEASON, LEDGER_PATH, load_season, pa_final_pitch
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
BREAKING = {"SL", "ST", "CU", "KC", "SV", "CS"}
SWING_DESC = {"swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play"}
WHIFF_DESC = {"swinging_strike", "swinging_strike_blocked"}
HIT_EVENTS = {"single", "double", "triple", "home_run"}


def _verdict(p, min_abs_effect: float, effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _bat_team(d: pd.DataFrame) -> pd.Series:
    return np.where(d["inning_topbot"] == "Top", d["away_team"], d["home_team"])


def iso_strand_variance_compression(pitch: pd.DataFrame) -> Dict[str, Any]:
    pa = pa_final_pitch(pitch)
    pa = pa.copy()
    pa["bat_team"] = _bat_team(pa)
    ab_events = {"single", "double", "triple", "home_run", "field_out", "strikeout", "force_out",
                 "grounded_into_double_play", "fielders_choice", "fielders_choice_out",
                 "double_play", "strikeout_double_play", "field_error"}
    ab = pa[pa["events"].isin(ab_events)]
    tb = ab["events"].map({"single": 1, "double": 2, "triple": 3, "home_run": 4}).fillna(0)
    team_iso = ((tb.groupby(ab["bat_team"]).sum() - ab.groupby("bat_team")["events"].apply(
        lambda s: (s == "single").sum())) / ab.groupby("bat_team").size())
    runs = pa.copy()
    runs["bat_team_post"] = np.where(runs["inning_topbot"] == "Top", runs["post_away_score"], runs["post_home_score"])
    game_runs = runs.groupby(["game_pk", "bat_team"]).apply(
        lambda g: g.sort_values("at_bat_number")["bat_team_post"].iloc[-1] -
        g.sort_values("at_bat_number")["bat_score"].iloc[0], include_groups=False)
    game_runs_var = game_runs.groupby(level="bat_team").std().rename("runs_std")
    m = pd.concat([team_iso.rename("iso"), game_runs_var], axis=1).dropna()
    r, p = stats.pearsonr(m["iso"], m["runs_std"])
    return {"hypothesis": "iso_strand_variance_compression", "n": int(len(m)), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.15, r),
            "note": "team ISO vs game-level runs-scored std (proxy for strand-rate variance -- no LOB/strand "
                    "field exists locally so runs-per-game std substitutes), n=%d teams" % len(m)}


def defensive_efficiency_conversion(pitch: pd.DataFrame) -> Dict[str, Any]:
    d = pitch.dropna(subset=["launch_speed", "launch_angle", "bb_type"]).copy()
    d = d[d["events"].isin(HIT_EVENTS | {"field_out", "force_out", "fielders_choice", "fielders_choice_out"})]
    d["is_hit"] = d["events"].isin(HIT_EVENTS)
    d["speed_bin"] = pd.qcut(d["launch_speed"], 8, duplicates="drop")
    d["angle_bin"] = pd.cut(d["launch_angle"], [-90, -10, 0, 10, 20, 32, 50, 90])
    exp = d.groupby(["speed_bin", "angle_bin"], observed=True)["is_hit"].transform("mean")
    d["residual"] = d["is_hit"].astype(float) - exp
    d["fielding_team"] = np.where(d["inning_topbot"] == "Top", d["home_team"], d["away_team"])
    gd = pd.to_datetime(d["game_date"])
    d["half"] = np.where(gd < gd.median(), "A", "B")
    piv = d.groupby(["fielding_team", "half"])["residual"].mean().unstack("half").dropna()
    r, p = stats.pearsonr(piv["A"], piv["B"])
    return {"hypothesis": "defensive_efficiency_conversion", "n": int(len(piv)), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.1, r),
            "note": "split-half pearson r, team residual-BABIP (actual - launch-condition-bin expected hit "
                    "rate), n=%d teams" % len(piv)}


def pitch_efficiency_durability(pitch: pd.DataFrame) -> Dict[str, Any]:
    d = pitch.copy()
    d["fielding_team"] = np.where(d["inning_topbot"] == "Top", d["home_team"], d["away_team"])
    first = d[(d["inning"] == 1)].sort_values("at_bat_number").groupby(
        ["game_pk", "fielding_team"]).head(1)[["game_pk", "fielding_team", "pitcher"]]
    starters = set(zip(first["game_pk"], first["pitcher"]))
    d["is_starter_game"] = d.apply(lambda r: (r["game_pk"], r["pitcher"]) in starters, axis=1)
    starts = d[d["is_starter_game"]]
    per_start = starts.groupby(["game_pk", "pitcher"]).agg(
        pitches=("pitch_number", "size"), pa=("at_bat_number", "nunique"), innings=("inning", "nunique"))
    per_start["pitches_per_pa"] = per_start["pitches"] / per_start["pa"]
    season = per_start.groupby("pitcher").agg(
        avg_pitches_per_pa=("pitches_per_pa", "mean"), avg_innings=("innings", "mean"),
        n_starts=("pitches", "size"))
    season = season[season["n_starts"] >= 8]
    r, p = stats.pearsonr(season["avg_pitches_per_pa"], season["avg_innings"])
    return {"hypothesis": "pitch_efficiency_durability", "n": int(len(season)), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.1, r),
            "note": "pearson r, starter-season avg pitches/PA vs avg innings-reached/start, n=%d starters "
                    "(>=8 starts); bullpen-vs-rotation ERA-gap sub-claim not tested this session" % len(season)}


def catcher_game_calling_persistence(pitch: pd.DataFrame) -> Dict[str, Any]:
    pa = pa_final_pitch(pitch).dropna(subset=["estimated_woba_using_speedangle", "game_date"]).copy()
    gd = pd.to_datetime(pa["game_date"])
    pa["half"] = np.where(gd < gd.median(), "A", "B")
    cnt = pa.groupby(["fielder_2", "half"]).size().unstack("half").fillna(0)
    ok_catchers = cnt[(cnt.get("A", 0) >= 100) & (cnt.get("B", 0) >= 100)].index
    d = pa[pa["fielder_2"].isin(ok_catchers)]
    piv = d.groupby(["fielder_2", "half"])["estimated_woba_using_speedangle"].mean().unstack("half").dropna()
    if len(piv) < 15:
        return {"hypothesis": "catcher_game_calling_persistence", "n": int(len(piv)), "effect": None, "p": None,
                "verdict": "NOT_TESTABLE", "note": "fewer than 15 catchers with >=100 PA caught per half"}
    r, p = stats.pearsonr(piv["A"], piv["B"])
    return {"hypothesis": "catcher_game_calling_persistence", "n": int(len(piv)), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.1, r),
            "note": "split-half pearson r, catcher's mean xwOBA-allowed while catching (raw, not "
                    "pitcher/batter-adjusted), n=%d catchers (>=100 PA/half)" % len(piv)}


def spin_rate_deception(pitch: pd.DataFrame) -> Dict[str, Any]:
    d = pitch[pitch["pitch_type"].isin(BREAKING)].dropna(
        subset=["release_spin_rate", "release_speed", "description"])
    d = d[d["description"].isin(SWING_DESC)].copy()
    d["whiff"] = d["description"].isin(WHIFF_DESC).astype(float)
    X = np.column_stack([np.ones(len(d)), d["release_spin_rate"], d["release_speed"]])
    beta, *_ = np.linalg.lstsq(X, d["whiff"], rcond=None)
    resid = d["whiff"].values - X @ beta
    dof = len(d) - 3
    sigma2 = float((resid @ resid) / dof)
    cov = sigma2 * np.linalg.inv(X.T @ X)
    se = float(np.sqrt(cov[1, 1]))
    t = beta[1] / se
    p = float(2 * (1 - stats.t.cdf(abs(t), df=dof)))
    return {"hypothesis": "spin_rate_deception", "n": int(len(d)), "effect": round(float(beta[1]), 8), "p": p,
            "verdict": _verdict(p, 1e-6, beta[1]),
            "note": "OLS whiff ~ release_spin_rate + release_speed (breaking pitches, swings only), "
                    "spin coef=%.2e, n=%d" % (beta[1], len(d))}


def sweet_spot_consistency(pitch: pd.DataFrame) -> Dict[str, Any]:
    d = pitch.dropna(subset=["launch_angle", "game_date"]).copy()
    d["sweet_spot"] = d["launch_angle"].between(8, 32)
    gd = pd.to_datetime(d["game_date"])
    d["half"] = np.where(gd < gd.median(), "A", "B")
    cnt = d.groupby(["batter", "half"]).size().unstack("half").fillna(0)
    ok = cnt[(cnt.get("A", 0) >= 20) & (cnt.get("B", 0) >= 20)].index
    dd = d[d["batter"].isin(ok)]
    piv = dd.groupby(["batter", "half"])["sweet_spot"].mean().unstack("half").dropna()
    r, p = stats.pearsonr(piv["A"], piv["B"])
    return {"hypothesis": "sweet_spot_consistency", "n": int(len(piv)), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.1, r),
            "note": "split-half pearson r, batter sweet-spot(8-32deg) rate, n=%d batters (>=20 BBE/half)"
                    % len(piv)}


def run(season: int = DEFAULT_SEASON) -> List[Dict[str, Any]]:
    df = load_season(season)
    rows = [iso_strand_variance_compression(df), defensive_efficiency_conversion(df),
            pitch_efficiency_durability(df), catcher_game_calling_persistence(df),
            spin_rate_deception(df), sweet_spot_consistency(df)]
    for r in rows:
        r["sport"] = "mlb"
        r["corpus"] = "savant_full__%d" % season
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-32s %-16s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.02, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.02, 0.1) == "NULL_LOCAL"
    print("self-check OK")
