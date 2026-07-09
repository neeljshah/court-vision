"""domains.tennis.knowledge.validate_point_dynamics -- 5 UNTESTED point-level
mechanisms against the 2011-2015 Grand Slam point-by-point corpus. Leak audit:
every test here is a CONTEMPORANEOUS or WITHIN-MATCH descriptive comparison
(surface vs point outcome on the same point; first-half-of-match vs
second-half-of-match speed on the same match) -- a mechanism-existence check,
not a live forecasting feature, so there is no future-into-past leak. This is
explicitly NOT re-testing the CLOSED point-level state-conditioning class from
domains/tennis/point_engine (commit 989ef60c: points ~iid given server) --
these are surface/fatigue/set-position mechanisms, a different question.

Run: python -m domains.tennis.knowledge.validate_point_dynamics
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.tennis.knowledge._data import LEDGER_PATH, load_slam_points
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_HALF_POINTS = 10


def serve_advantage_by_surface(df: pd.DataFrame) -> Dict[str, Any]:
    """Server win-rate on Clay vs Hard+Grass combined -- clay's slower bounce
    is expected to erode serve advantage relative to faster surfaces."""
    d = df.dropna(subset=["surface", "point_server", "point_winner"])
    d = d[d["point_number"] >= 1]
    won = (d["point_winner"] == d["point_server"]).astype(int)
    clay = won[d["surface"] == "Clay"]
    fast = won[d["surface"] != "Clay"]
    t, p = stats.ttest_ind(clay, fast, equal_var=False)
    return {"hypothesis": "serve_advantage_by_surface", "n": int(len(d)),
            "effect": round(float(clay.mean() - fast.mean()), 5), "p": float(p),
            "note": "server win-rate Clay %.4f (n=%d) vs Hard+Grass %.4f (n=%d)"
                    % (clay.mean(), len(clay), fast.mean(), len(fast))}


def rally_length_clay_vs_grass(df: pd.DataFrame) -> Dict[str, Any]:
    """Rally length (shot count) Clay vs Grass -- clay's slower ball should
    produce measurably longer points than grass's low, fast bounce."""
    d = df.dropna(subset=["rally", "surface"])
    d = d[d["surface"].isin(["Clay", "Grass"])]
    clay, grass = d.loc[d["surface"] == "Clay", "rally"], d.loc[d["surface"] == "Grass", "rally"]
    t, p = stats.ttest_ind(clay, grass, equal_var=False)
    return {"hypothesis": "rally_length_clay_vs_grass", "n": int(len(d)),
            "effect": round(float(clay.mean() - grass.mean()), 4), "p": float(p),
            "note": "mean rally shots Clay %.3f (n=%d) vs Grass %.3f (n=%d)"
                    % (clay.mean(), len(clay), grass.mean(), len(grass))}


def serve_speed_decay_within_match(df: pd.DataFrame) -> Dict[str, Any]:
    """Paired within-match test: mean serve speed in the second half of a
    match's points vs the first half. Fatigue predicts a negative diff."""
    d = df[df["speed_kmh"] > 0].sort_values(["match_id", "set_no", "game_no", "point_number"])
    d = d.copy()
    d["ord"] = d.groupby("match_id").cumcount()
    cnt = d.groupby("match_id")["ord"].transform("count")
    mid = d.groupby("match_id")["ord"].transform("median")
    half = np.where(d["ord"] <= mid, "h1", "h2")
    d["half"] = half
    g = d.groupby(["match_id", "half"])["speed_kmh"].agg(["mean", "count"]).unstack("half")
    g.columns = ["h1_mean", "h2_mean", "h1_n", "h2_n"]
    g = g.dropna()
    g = g[(g["h1_n"] >= MIN_HALF_POINTS) & (g["h2_n"] >= MIN_HALF_POINTS)]
    diff = g["h2_mean"] - g["h1_mean"]
    t, p = stats.ttest_1samp(diff, 0.0)
    return {"hypothesis": "serve_speed_decay_within_match", "n": int(len(diff)),
            "effect": round(float(diff.mean()), 4), "p": float(p),
            "note": "mean per-match (2nd-half - 1st-half) serve speed km/h across %d matches"
                    % len(diff)}


def double_fault_rate_by_set_number(df: pd.DataFrame) -> Dict[str, Any]:
    """Combined double-fault rate (both players) in set 1 vs set 3+, a fresh
    fatigue/pressure angle distinct from the already-adjudicated break-point
    double-fault claim (see mechanisms.md pre-adjudicated #3)."""
    d = df.dropna(subset=["set_no", "p1_double_fault", "p2_double_fault"])
    df_rate = (d["p1_double_fault"] + d["p2_double_fault"]).clip(upper=1)
    early, late = df_rate[d["set_no"] == 1], df_rate[d["set_no"] >= 3]
    t, p = stats.ttest_ind(late, early, equal_var=False)
    return {"hypothesis": "double_fault_rate_by_set_number", "n": int(len(d)),
            "effect": round(float(late.mean() - early.mean()), 5), "p": float(p),
            "note": "DF rate set>=3 %.4f (n=%d) vs set==1 %.4f (n=%d)"
                    % (late.mean(), len(late), early.mean(), len(early))}


def deciding_set_hold_rate_shift(df: pd.DataFrame) -> Dict[str, Any]:
    """Server win-rate (hold proxy) in a match's FINAL set vs its first set --
    tests whether serve dominance shifts under decisive-set pressure/fatigue."""
    d = df.dropna(subset=["set_no", "point_server", "point_winner"]).copy()
    d = d[d["point_number"] >= 1]
    final_set = d.groupby("match_id")["set_no"].transform("max")
    won = (d["point_winner"] == d["point_server"]).astype(int)
    last = won[(d["set_no"] == final_set) & (final_set > 1)]
    first = won[d["set_no"] == 1]
    t, p = stats.ttest_ind(last, first, equal_var=False)
    return {"hypothesis": "deciding_set_hold_rate_shift", "n": int(len(last) + len(first)),
            "effect": round(float(last.mean() - first.mean()), 5), "p": float(p),
            "note": "server win-rate final-set %.4f (n=%d) vs set-1 %.4f (n=%d)"
                    % (last.mean(), len(last), first.mean(), len(first))}


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def run() -> List[Dict[str, Any]]:
    df = load_slam_points()
    specs = [
        (serve_advantage_by_surface, 0.01),
        (rally_length_clay_vs_grass, 0.3),
        (serve_speed_decay_within_match, 0.5),
        (double_fault_rate_by_set_number, 0.005),
        (deciding_set_hold_rate_shift, 0.01),
    ]
    rows = []
    for fn, min_eff in specs:
        r = fn(df)
        r["verdict"] = _verdict(r["p"], r["effect"], min_eff)
        r["sport"] = "tennis"
        r["corpus"] = "slam_points_2011_2015"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
        rows.append(r)
    return rows


def main() -> int:
    for r in run():
        print("%-38s %-16s n=%-8d effect=%+.4f p=%.4g -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict thresholds behave as declared."""
    assert _verdict(0.001, 0.5, 0.15) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.15) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.15) == "NOT_TESTABLE"
    print("self-check OK")
