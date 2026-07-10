"""domains.tennis.knowledge.validate_travel_altitude -- 2 UNTESTED mechanisms
(seed C7) against `travel_scouting.parquet` (55,446 rows, 27,723 events,
2015-2025) joined to `match_stats.parquet` and `matches.parquet`. Leak audit:
`venue_altitude_m` is a static venue fact known long before the match;
`miles_flown_in` is the distance flown INTO the venue city, a pre-match-known
travel fact (not a post-match outcome). The `event_id` + `is_p1` join between
`travel_scouting.parquet` and `matches.parquet` was verified this session:
100% event_id overlap with both matches.parquet and match_stats.parquet,
exactly one True/one False `is_p1` row per event, and a 100% name-match rate
between `travel_scouting`'s (event_id, is_p1) -> player and `matches.parquet`'s
p1_name/p2_name for the same event_id -- so no fuzzy name matching is needed,
the (event_id, is_p1) pair maps directly onto matches.parquet's p1/p2 slots.

Run: python -m domains.tennis.knowledge.validate_travel_altitude
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from domains.tennis.knowledge._data import LEDGER_PATH, TENNIS_DIR, load_matches
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
ALTITUDE_HIGH_M = 500.0  # real high-altitude tour venues clear this (Madrid 667m,
                          # Sofia 550m, Bogota 2640m, Quito 2850m -- verified in data)


def load_travel_scouting() -> pd.DataFrame:
    """event_id, player, is_p1, miles_flown_in, venue_altitude_m. One row per
    (event, perspective) -- not added to _data.py since only this validator
    needs it."""
    return pd.read_parquet(TENNIS_DIR / "travel_scouting.parquet")


def load_match_stats() -> pd.DataFrame:
    """event_id -> p1/p2 serve stats (ace_rate, 1stWon, 2ndWon, svpt, ...).
    Not added to _data.py -- same reasoning as load_travel_scouting."""
    return pd.read_parquet(TENNIS_DIR / "match_stats.parquet")


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def altitude_effect_on_serve_ace_rate(travel: pd.DataFrame, stats_df: pd.DataFrame) -> Dict[str, Any]:
    """Does venue altitude shift combined ace rate? Thin-air folklore says
    altitude should raise ace rate (less drag); tests the direction without
    assuming it."""
    ea = travel.drop_duplicates("event_id")[["event_id", "venue_altitude_m"]]
    s = stats_df.copy()
    s["combined_ace_rate"] = (s["p1_ace_rate"] + s["p2_ace_rate"]) / 2.0
    d = ea.merge(s[["event_id", "combined_ace_rate"]], on="event_id").dropna()
    high = d.loc[d["venue_altitude_m"] >= ALTITUDE_HIGH_M, "combined_ace_rate"]
    low = d.loc[d["venue_altitude_m"] < ALTITUDE_HIGH_M, "combined_ace_rate"]
    t, p = stats.ttest_ind(high, low, equal_var=False)
    eff = float(high.mean() - low.mean())
    return {"hypothesis": "altitude_effect_on_serve_ace_rate", "n": int(len(d)),
            "effect": round(eff, 4), "p": float(p),
            "note": "combined ace rate >= %dm altitude %.4f (n=%d) vs < %dm %.4f (n=%d)"
                    % (int(ALTITUDE_HIGH_M), high.mean(), len(high), int(ALTITUDE_HIGH_M), low.mean(), len(low))}


def _travel_matches_frame(travel: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    tp1 = travel[travel["is_p1"]][["event_id", "miles_flown_in"]].rename(columns={"miles_flown_in": "p1_miles"})
    tp2 = travel[~travel["is_p1"]][["event_id", "miles_flown_in"]].rename(columns={"miles_flown_in": "p2_miles"})
    d = matches.dropna(subset=["p1_rank", "p2_rank", "winner"]).merge(tp1, on="event_id").merge(tp2, on="event_id")
    d = d.dropna(subset=["p1_miles", "p2_miles"]).copy()
    d["rank_diff"] = d["p2_rank"] - d["p1_rank"]
    d["p1_win"] = (d["winner"] == 1).astype(int)
    d["travel_diff_1000mi"] = (d["p1_miles"] - d["p2_miles"]) / 1000.0
    return d


def long_travel_effect_on_win_prob_partial(travel: pd.DataFrame, matches: pd.DataFrame) -> Dict[str, Any]:
    """Does traveling further than your opponent (miles_flown_in gap) lower
    win probability, controlling for the ranking gap (partial effect, not a
    raw rank-close bucket comparison -- uses the full matched sample)."""
    d = _travel_matches_frame(travel, matches)
    res = smf.logit("p1_win ~ travel_diff_1000mi + rank_diff", data=d).fit(disp=0)
    eff = float(res.params["travel_diff_1000mi"])
    p = float(res.pvalues["travel_diff_1000mi"])
    return {"hypothesis": "long_travel_effect_on_win_prob_partial", "n": int(len(d)),
            "effect": round(eff, 4), "p": p,
            "note": "logit p1_win ~ travel_diff_1000mi + rank_diff, travel coef=%.4f (per 1000mi p1 "
                    "traveled more than p2), n=%d, controls for rank_diff so this is net of the ranking gap"
                    % (eff, len(d))}


def run() -> List[Dict[str, Any]]:
    travel = load_travel_scouting()
    stats_df = load_match_stats()
    matches = load_matches()
    rows = [
        (altitude_effect_on_serve_ace_rate(travel, stats_df), 0.005),
        (long_travel_effect_on_win_prob_partial(travel, matches), 0.02),
    ]
    out = []
    for r, min_eff in rows:
        r["verdict"] = _verdict(r["p"], r["effect"], min_eff)
        r["sport"] = "tennis"
        r["corpus"] = "travel_scouting_matches_atp_wta_2015_2025"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
        out.append(r)
    return out


def main() -> int:
    for r in run():
        print("%-44s %-16s n=%-8d effect=%+.5f p=%.4g -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict thresholds + the travel-diff frame builder."""
    assert _verdict(0.001, 0.05, 0.02) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.05, 0.02) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.05, 0.02) == "NOT_TESTABLE"
    travel = pd.DataFrame({
        "event_id": ["e1", "e1", "e2", "e2"],
        "player": ["A", "B", "C", "D"],
        "is_p1": [True, False, True, False],
        "miles_flown_in": [1000.0, 0.0, 0.0, 2000.0],
        "venue_altitude_m": [10.0, 10.0, 600.0, 600.0],
    })
    matches = pd.DataFrame({
        "event_id": ["e1", "e2"], "p1_rank": [10, 5], "p2_rank": [20, 15],
        "winner": [1, 2],
    })
    fr = _travel_matches_frame(travel, matches)
    assert len(fr) == 2
    assert fr.loc[fr["event_id"] == "e1", "travel_diff_1000mi"].iloc[0] == 1.0
    print("self-check OK")
