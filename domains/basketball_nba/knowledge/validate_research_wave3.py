"""domains.basketball_nba.knowledge.validate_research_wave3 -- validates the
2 NBA literature-sourced UNTESTED rows appended 2026-07-10 (commit 31fd7615,
"research-wave 3", rows #49-50 in mechanisms.md):

  starter_minutes_vs_margin        (row #49) -- player_boxscores.parquet
    starter-minutes summed per team-game vs |final margin| bucket (season-
    level final-margin proxy for garbage time; NOT live-threshold personnel
    tracking, which this corpus does not carry -- the row's own scope
    reduction, replicated here as stated).
  b2b_x_margin_starter_minutes     (row #50) -- same starter-minutes
    ingredient x is_b2b (rest_days==0, #14's own definition) interaction.

PREMISE CHECK (this session): player_boxscores.parquet 77,744 rows on disk,
columns game_id/team/starter(bool)/min(float) confirmed. team_game_frame(...)
= 7222 team-games (matches wave2's own stated count); starter-minutes sum
joins onto all 7222 rows with zero nulls, 7192 with non-null rest_days
(matches wave2's #48 count exactly).

SPEC NOTE (row #50): the row's declared bar is stated as an unsigned
magnitude ("|interaction coef|>=0.05 AND p<0.01") even though the row's own
causal story predicts a NEGATIVE interaction (b2b teams' starter-minutes
should fall FASTER per margin-point). Implemented literally as declared
(unsigned) -- observed sign is reported in the note either way, not silently
tightened into a signed bar the row didn't declare.

HONESTY: both rows get a split-half-by-date replication (2 groups) inside
this single run, mirroring wave2's >=2-corpora discipline for an affirmative.

Run: python -m domains.basketball_nba.knowledge.validate_research_wave3
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from domains.basketball_nba.knowledge._data import LEDGER_PATH, load_player_boxscores, team_game_frame
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_GROUP_N = 20
MIN_TREND_SLOPE = 0.05    # row #49's declared bar, min/margin-point (bar itself is signed <=-0.05)
MIN_INTERACTION = 0.05    # row #50's declared bar, |coef| threshold (unsigned, see SPEC NOTE)
MARGIN_BANDS = [(0, 10), (10, 20), (20, 30), (30, np.inf)]
BAND_MIDPOINTS = {0: 5.0, 1: 14.5, 2: 24.5, 3: 35.0}


def _combine_halves(rows: List[Dict[str, Any]], hyp: str) -> Dict[str, Any]:
    """Both halves must independently clear the row's own p+effect bar (i.e.
    verdict==CONFIRMED_LOCAL), same sign, else NULL/PROVISIONAL/NOT_TESTABLE."""
    testable = [r for r in rows if r["verdict"] != "NOT_TESTABLE"]
    confirmed = [r for r in testable if r["verdict"] == "CONFIRMED_LOCAL"]
    if len(testable) < 2:
        verdict = "NOT_TESTABLE"
    elif len(confirmed) == 2 and len({1 if r["effect"] > 0 else -1 for r in confirmed}) == 1:
        verdict = "CONFIRMED_LOCAL"
    elif len(confirmed) == 1:
        verdict = "PROVISIONAL"
    else:
        verdict = "NULL_LOCAL"
    return {"hypothesis": hyp + "__combined", "n": int(sum(r["n"] for r in rows)), "effect": None, "p": None,
            "verdict": verdict,
            "note": "split-half-by-date replication: %s"
                    % "; ".join("%s(verdict=%s,p=%s,eff=%s)" % (r["hypothesis"], r["verdict"], r["p"], r["effect"])
                                for r in rows)}


def build_dataset() -> pd.DataFrame:
    box = load_player_boxscores()
    tg = team_game_frame(box)
    starter_min = (box[box["starter"] == True]
                   .groupby(["game_id", "team"], as_index=False)["min"].sum()
                   .rename(columns={"min": "starter_minutes"}))
    d = tg.merge(starter_min, on=["game_id", "team"], how="inner")
    d["abs_margin"] = d["margin"].abs()
    return d


def _band(m: float) -> Optional[int]:
    for i, (lo, hi) in enumerate(MARGIN_BANDS):
        if lo <= m < hi:
            return i
    return None


# ---------------------------------------------------------------- row #49 --
def _trend_verdict(d: pd.DataFrame, half: str) -> Dict[str, Any]:
    hyp = "starter_minutes_vs_margin__%s" % half
    if len(d) < MIN_GROUP_N:
        return {"hypothesis": hyp, "n": int(len(d)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "insufficient team-games (n=%d, need >=%d), half=%s" % (len(d), MIN_GROUP_N, half)}
    d = d.copy()
    d["band"] = d["abs_margin"].apply(_band)
    band_groups = [g["starter_minutes"].values for _, g in d.groupby("band") if len(g) >= MIN_GROUP_N]
    if len(band_groups) < 2:
        return {"hypothesis": hyp, "n": int(len(d)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 2 margin bands with >=%d team-games, half=%s" % (MIN_GROUP_N, half)}
    kw_h, kw_p = stats.kruskal(*band_groups)
    band_means = d.groupby("band")["starter_minutes"].mean()
    mids = [BAND_MIDPOINTS[int(b)] for b in band_means.index]
    slope, intercept, r, trend_p, se = stats.linregress(mids, band_means.values)
    verdict = "CONFIRMED_LOCAL" if (trend_p < ALPHA and slope <= -MIN_TREND_SLOPE) else "NULL_LOCAL"
    return {"hypothesis": hyp, "n": int(len(d)), "effect": round(float(slope), 4), "p": float(trend_p),
            "verdict": verdict,
            "note": "band-midpoint trend slope=%.4f min/margin-pt p=%.4g (n=%d bands); Kruskal-Wallis "
                    "across raw bands H=%.2f p=%.4g, half=%s" % (slope, trend_p, len(mids), kw_h, kw_p, half)}


def starter_minutes_vs_margin(d: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
    d = d if d is not None else build_dataset()
    if d.empty:
        return [{"hypothesis": "starter_minutes_vs_margin__combined", "n": 0, "effect": None, "p": None,
                  "verdict": "NOT_TESTABLE", "note": "no team-games with a starter-minutes ingredient"}]
    mid = d["date"].median()
    h1 = _trend_verdict(d[d["date"] <= mid], "h1")
    h2 = _trend_verdict(d[d["date"] > mid], "h2")
    return [h1, h2, _combine_halves([h1, h2], "starter_minutes_vs_margin")]


# ---------------------------------------------------------------- row #50 --
def _interaction_verdict(d: pd.DataFrame, half: str) -> Dict[str, Any]:
    hyp = "b2b_x_margin_starter_minutes__%s" % half
    if len(d) < MIN_GROUP_N * 2 or d["is_b2b"].nunique() < 2:
        return {"hypothesis": hyp, "n": int(len(d)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "insufficient rows or degenerate is_b2b (n=%d), half=%s" % (len(d), half)}
    term = "abs_margin:is_b2b"
    res = smf.ols("starter_minutes ~ abs_margin + is_b2b + abs_margin:is_b2b", data=d).fit()
    eff, p = float(res.params[term]), float(res.pvalues[term])
    verdict = "CONFIRMED_LOCAL" if (p < ALPHA and abs(eff) >= MIN_INTERACTION) else "NULL_LOCAL"
    return {"hypothesis": hyp, "n": int(len(d)), "effect": round(eff, 4), "p": p, "verdict": verdict,
            "note": "OLS starter_minutes~abs_margin+is_b2b+abs_margin:is_b2b, interaction coef=%.4f p=%.4g "
                    "(n=%d, b2b=%d) half=%s" % (eff, p, len(d), int(d["is_b2b"].sum()), half)}


def b2b_x_margin_starter_minutes(d: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
    d = d if d is not None else build_dataset()
    d = d.dropna(subset=["rest_days"]).copy()
    if d.empty:
        return [{"hypothesis": "b2b_x_margin_starter_minutes__combined", "n": 0, "effect": None, "p": None,
                  "verdict": "NOT_TESTABLE", "note": "no team-games with non-null rest_days"}]
    d["is_b2b"] = (d["rest_days"] == 0).astype(int)
    mid = d["date"].median()
    h1 = _interaction_verdict(d[d["date"] <= mid], "h1")
    h2 = _interaction_verdict(d[d["date"] > mid], "h2")
    return [h1, h2, _combine_halves([h1, h2], "b2b_x_margin_starter_minutes")]


def run() -> List[Dict[str, Any]]:
    d = build_dataset()
    r49 = starter_minutes_vs_margin(d)
    for r in r49:
        r["corpus"] = "player_boxscores_team_game_frame_7222_teamgames (split-half by date)"
    r50 = b2b_x_margin_starter_minutes(d)
    for r in r50:
        r["corpus"] = "player_boxscores_team_game_frame_7192_teamgames_nonnull_rest (split-half by date)"
    rows = r49 + r50
    for r in rows:
        r["sport"] = "basketball_nba"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-42s %-16s n=%-6s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r.get("n"), r.get("effect"), r.get("p"), r.get("note")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: band assignment, trend/interaction verdict
    thresholds, and combine-halves sign logic."""
    assert _band(5) == 0 and _band(15) == 1 and _band(25) == 2 and _band(35) == 3
    d = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01"] * 30 + ["2026-01-02"] * 30 + ["2026-01-03"] * 30 + ["2026-01-04"] * 30),
        "abs_margin": [5.0] * 30 + [15.0] * 30 + [25.0] * 30 + [35.0] * 30,
        "starter_minutes": [160.0] * 30 + [150.0] * 30 + [140.0] * 30 + [125.0] * 30,
    })
    r = _trend_verdict(d, "h1")
    assert r["verdict"] == "CONFIRMED_LOCAL" and r["effect"] < 0
    small = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"] * 5), "abs_margin": [5.0] * 5,
                           "starter_minutes": [160.0] * 5})
    assert _trend_verdict(small, "h1")["verdict"] == "NOT_TESTABLE"
    out = _combine_halves(
        [{"hypothesis": "x__h1", "n": 30, "effect": -0.5, "p": 0.001, "verdict": "CONFIRMED_LOCAL"},
         {"hypothesis": "x__h2", "n": 30, "effect": 0.5, "p": 0.001, "verdict": "CONFIRMED_LOCAL"}], "x")
    assert out["verdict"] == "NULL_LOCAL"  # opposite signs -- not a real replication
    print("self-check OK")
