"""domains.mlb.knowledge.validate_count_zone -- 3 UNTESTED count/zone mechanisms
against one local season of Statcast pitch-level data (leak-free: every test is
a WITHIN-PA / WITHIN-PITCH descriptive comparison, nothing predicts a future PA
from a later one). Run: python -m domains.mlb.knowledge.validate_count_zone

Mechanisms tested (see domains/mlb/knowledge/mechanisms.md for the full spec):
  1. edge_zone_widens_with_two_strikes  -- pitchers work the shadow/chase zone
     (Statcast zone 11-14) more often once the count reaches 2 strikes.
  2. two_strike_chase_rate_rises        -- batters swing at out-of-zone pitches
     more often at 2 strikes than at <2 strikes (zone expansion).
  3. first_pitch_strike_suppresses_bb   -- a first-pitch strike lowers the
     walk rate for the rest of that plate appearance.

Verdict rule (declared before running, same spirit as the interaction factory):
p < 0.01 and |effect| meaningful -> CONFIRMED_LOCAL; else NULL_LOCAL.
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge._data import DEFAULT_SEASON, LEDGER_PATH, load_season
from scripts.platformkit.io_atomic import append_jsonl_atomic

EDGE_ZONES = {11, 12, 13, 14}
SWING_DESC = {"swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play"}
ALPHA = 0.01


def _verdict(p: float, effect: float, min_abs_effect: float = 0.0) -> str:
    if p is None or np.isnan(p):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def edge_zone_widens_with_two_strikes(df: pd.DataFrame) -> Dict[str, Any]:
    d = df.dropna(subset=["zone", "strikes"])
    is_edge = d["zone"].isin(EDGE_ZONES)
    two_strike = d["strikes"] == 2
    rate_2k = is_edge[two_strike].mean()
    rate_other = is_edge[~two_strike].mean()
    a = is_edge[two_strike].astype(int)
    b = is_edge[~two_strike].astype(int)
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return {"hypothesis": "edge_zone_widens_with_two_strikes", "n": int(len(d)),
            "effect": round(float(rate_2k - rate_other), 5), "p": float(p),
            "note": "edge-zone(11-14) rate at strikes==2 (%.4f) vs strikes<2 (%.4f)" % (rate_2k, rate_other)}


def two_strike_chase_rate_rises(df: pd.DataFrame) -> Dict[str, Any]:
    d = df.dropna(subset=["zone", "strikes", "description"])
    swung = d["description"].isin(SWING_DESC)
    out_of_zone = ~d["zone"].isin(set(range(1, 10)))
    chase = swung & out_of_zone
    two_strike = d["strikes"] == 2
    rate_2k = chase[two_strike].mean()
    rate_other = chase[~two_strike].mean()
    t, p = stats.ttest_ind(chase[two_strike].astype(int), chase[~two_strike].astype(int), equal_var=False)
    return {"hypothesis": "two_strike_chase_rate_rises", "n": int(len(d)),
            "effect": round(float(rate_2k - rate_other), 5), "p": float(p),
            "note": "chase rate at strikes==2 (%.4f) vs strikes<2 (%.4f)" % (rate_2k, rate_other)}


def first_pitch_strike_suppresses_bb(df: pd.DataFrame) -> Dict[str, Any]:
    d = df.dropna(subset=["events"], how="all")
    first = df[df["pitch_number"] == 1][["game_pk", "at_bat_number", "description"]].copy()
    first["fp_strike"] = first["description"].isin(SWING_DESC | {"called_strike"})
    npitches = df.groupby(["game_pk", "at_bat_number"])["pitch_number"].max().rename("n_pitches")
    final = df.sort_values(["game_pk", "at_bat_number", "pitch_number"]).groupby(
        ["game_pk", "at_bat_number"], sort=False).tail(1)[["game_pk", "at_bat_number", "events"]]
    m = first.merge(npitches, on=["game_pk", "at_bat_number"]).merge(
        final, on=["game_pk", "at_bat_number"])
    m = m[m["n_pitches"] >= 2]  # PA must have continued past pitch 1 to measure a BB outcome
    m["is_bb"] = (m["events"] == "walk").astype(int)
    a = m.loc[m["fp_strike"], "is_bb"]
    b = m.loc[~m["fp_strike"], "is_bb"]
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return {"hypothesis": "first_pitch_strike_suppresses_bb", "n": int(len(m)),
            "effect": round(float(a.mean() - b.mean()), 5), "p": float(p),
            "note": "BB rate after 1st-pitch strike (%.4f) vs 1st-pitch ball/other (%.4f)" % (a.mean(), b.mean())}


def run(season: int = DEFAULT_SEASON) -> List[Dict[str, Any]]:
    df = load_season(season)
    checks = [edge_zone_widens_with_two_strikes, two_strike_chase_rate_rises, first_pitch_strike_suppresses_bb]
    rows = []
    for fn in checks:
        r = fn(df)
        r["verdict"] = _verdict(r["p"], r["effect"], min_abs_effect=0.005)
        r["sport"] = "mlb"
        r["corpus"] = "savant_full__%d" % season
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
        rows.append(r)
    return rows


def main() -> int:
    for r in run():
        print("%-40s %-16s n=%-8d effect=%+.5f p=%.4g -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict rule + edge-zone set are internally
    consistent on a synthetic frame (no parquet needed)."""
    fake = pd.DataFrame({
        "zone": [1, 11, 12, 5, 13, 2] * 20,
        "strikes": ([2] * 3 + [0] * 3) * 20,
        "description": (["swinging_strike", "foul", "ball"] * 2) * 20,
        "game_pk": [1] * 120, "at_bat_number": list(range(120)),
        "events": [None] * 120, "pitch_number": [1] * 120,
    })
    r = edge_zone_widens_with_two_strikes(fake)
    assert "effect" in r and "p" in r
    assert _verdict(0.001, 0.02, 0.005) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.02, 0.005) == "NULL_LOCAL"
    print("self-check OK")
