"""domains.mlb.knowledge.validate_contact_park -- 3 UNTESTED park/contact
mechanisms against one local Statcast season. Leak audit: park-factor and
contact-quality checks are SPLIT-HALF reliability tests (first-half-of-season
vs second-half-of-season correlation) -- a within-season internal-consistency
check, not a forecast, so there is no future-into-past leak. The shift check
is a contemporaneous group comparison (alignment vs outcome on the SAME
batted ball), also leak-free by construction.

Run: python -m domains.mlb.knowledge.validate_contact_park
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge._data import DEFAULT_SEASON, LEDGER_PATH, load_season
from scripts.platformkit.io_atomic import append_jsonl_atomic

HIT_EVENTS = {"single", "double", "triple", "home_run"}
OUT_EVENTS = {"field_out", "force_out", "double_play", "grounded_into_double_play",
              "fielders_choice_out", "triple_play", "field_error", "fielders_choice"}
MIN_BATTED_HALF = 20
ALPHA = 0.01


def park_factor_split_half(df: pd.DataFrame) -> Dict[str, Any]:
    """Per-park (home_team) average total runs/game, first half of season's
    dates vs second half -- Pearson r across parks measures whether the park
    run environment is a stable, repeatable signal or half-to-half noise."""
    last = df.sort_values(["game_pk", "at_bat_number", "pitch_number"]).groupby(
        "game_pk", sort=False).tail(1)
    last = last.dropna(subset=["post_home_score", "post_away_score", "game_date", "home_team"])
    last["total_runs"] = last["post_home_score"] + last["post_away_score"]
    last["game_date"] = pd.to_datetime(last["game_date"])
    mid = last["game_date"].median()
    h1 = last[last["game_date"] <= mid].groupby("home_team")["total_runs"].mean()
    h2 = last[last["game_date"] > mid].groupby("home_team")["total_runs"].mean()
    joined = pd.concat([h1, h2], axis=1, keys=["h1", "h2"]).dropna()
    r, p = stats.pearsonr(joined["h1"], joined["h2"])
    return {"hypothesis": "park_factor_run_modulation_split_half", "n": int(len(joined)),
            "effect": round(float(r), 4), "p": float(p),
            "note": "split-half Pearson r of park avg total-runs/game across %d parks" % len(joined)}


def infield_shift_suppresses_gb_babip(df: pd.DataFrame) -> Dict[str, Any]:
    d = df[(df["bb_type"] == "ground_ball") & df["if_fielding_alignment"].notna()]
    d = d[d["events"].isin(HIT_EVENTS | OUT_EVENTS)]
    is_hit = d["events"].isin(HIT_EVENTS).astype(int)
    shifted = d["if_fielding_alignment"].isin(["Infield shade", "Strategic"])
    a, b = is_hit[shifted], is_hit[~shifted]
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return {"hypothesis": "infield_shift_suppresses_gb_babip", "n": int(len(d)),
            "effect": round(float(a.mean() - b.mean()), 5), "p": float(p),
            "note": "GB hit-rate shifted/strategic (%.4f, n=%d) vs standard (%.4f, n=%d)"
                    % (a.mean(), int(shifted.sum()), b.mean(), int((~shifted).sum()))}


def contact_quality_persists_split_half(df: pd.DataFrame) -> Dict[str, Any]:
    d = df.dropna(subset=["launch_speed", "game_date", "batter"]).copy()
    d["game_date"] = pd.to_datetime(d["game_date"])
    mid = d["game_date"].median()
    h1 = d[d["game_date"] <= mid].groupby("batter")["launch_speed"].agg(["mean", "count"])
    h2 = d[d["game_date"] > mid].groupby("batter")["launch_speed"].agg(["mean", "count"])
    h1 = h1[h1["count"] >= MIN_BATTED_HALF]
    h2 = h2[h2["count"] >= MIN_BATTED_HALF]
    joined = pd.concat([h1["mean"], h2["mean"]], axis=1, keys=["h1", "h2"]).dropna()
    r, p = stats.pearsonr(joined["h1"], joined["h2"])
    return {"hypothesis": "contact_quality_persists_split_half", "n": int(len(joined)),
            "effect": round(float(r), 4), "p": float(p),
            "note": "split-half Pearson r of mean launch_speed across %d batters (>=%d BBE/half)"
                    % (len(joined), MIN_BATTED_HALF)}


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def run(season: int = DEFAULT_SEASON) -> List[Dict[str, Any]]:
    df = load_season(season)
    specs = [(park_factor_split_half, 0.15), (infield_shift_suppresses_gb_babip, 0.01),
             (contact_quality_persists_split_half, 0.15)]
    rows = []
    for fn, min_eff in specs:
        r = fn(df)
        r["verdict"] = _verdict(r["p"], r["effect"], min_eff)
        r["sport"] = "mlb"
        r["corpus"] = "savant_full__%d" % season
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
        rows.append(r)
    return rows


def main() -> int:
    for r in run():
        print("%-42s %-16s n=%-8d effect=%+.4f p=%.4g -- %s" % (
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
