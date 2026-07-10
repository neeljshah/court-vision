"""domains.mlb.knowledge.validate_staff_dayafter_chain -- C18: after a team's
high-pitch-count day (whole pitching staff heavily used), does its run
prevention degrade the very NEXT calendar day?

PREMISE CHECK (run before designing this): neither savant_full__*.parquet nor
bullpen_relief_chains.parquet has a literal `pitch_count` column. savant_full
IS pitch-level (one row per pitch thrown), so a team's daily pitch count is a
plain row-count: group by pitching team (home team pitches when
inning_topbot=="Top", away team when =="Bot") and game_date. This is a
straightforward aggregation, not a fictitious-column workaround, so the
mechanism is TESTABLE as designed below (not NOT_TESTABLE at the premise
stage).

Leak audit: the predictor (team's total staff pitches on day d) is fully
known at the close of day d, strictly before day d+1 starts. The outcome
(runs allowed on day d+1, from post_home_score/post_away_score) is observed
only as day d+1 unfolds. Pairs are restricted to gap_days==1 (a true
back-to-back calendar pair, no off-day in between) so the effect isolates
"day after a heavy staff day", not generic schedule fatigue.

Corpora: 2023/2024/2025 seasons are independent replication corpora (same
convention as validate_reliever_b2b_fatigue.py). Affirmative requires the
same-direction (more prior-day pitches -> MORE runs allowed next day)
significant effect in >=2 of 3 seasons for CONFIRMED_LOCAL, 1 for
PROVISIONAL, else NULL_LOCAL/NOT_TESTABLE.

Run: python -m domains.mlb.knowledge.validate_staff_dayafter_chain
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge._data import LEDGER_PATH, load_season
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
SEASONS = [2023, 2024, 2025]
MIN_GROUP_N = 20
HIGH_Q, LOW_Q = 0.75, 0.25


def _verdict(p, min_abs_effect: float, effect) -> str:
    if p is None or effect is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def team_day_table(pitch: pd.DataFrame) -> pd.DataFrame:
    """One row per (team, game_date): total staff pitches thrown that day
    (row-count = pitch-count at pitch-level grain) and runs allowed that day
    (doubleheader games summed into the same team-day)."""
    d = pitch.copy()
    d["game_date"] = pd.to_datetime(d["game_date"])
    d["pitching_team"] = np.where(d["inning_topbot"] == "Top", d["home_team"], d["away_team"])
    pitches = (d.groupby(["pitching_team", "game_date"]).size()
               .rename("pitches").reset_index().rename(columns={"pitching_team": "team"}))

    final = d.groupby("game_pk").agg(game_date=("game_date", "first"), home_team=("home_team", "first"),
                                      away_team=("away_team", "first"),
                                      home_score=("post_home_score", "max"),
                                      away_score=("post_away_score", "max")).reset_index()
    allowed = pd.concat([
        final[["game_date"]].assign(team=final["home_team"], runs_allowed=final["away_score"]),
        final[["game_date"]].assign(team=final["away_team"], runs_allowed=final["home_score"]),
    ], ignore_index=True)
    runs = allowed.groupby(["team", "game_date"])["runs_allowed"].sum().reset_index()
    return pitches.merge(runs, on=["team", "game_date"], how="inner")


def build_dayafter_pairs(team_day: pd.DataFrame) -> pd.DataFrame:
    """(prior_day_pitches, next_runs_allowed) restricted to true back-to-back
    calendar days (gap_days==1, no off-day between)."""
    d = team_day.sort_values(["team", "game_date"]).copy()
    d["next_date"] = d.groupby("team")["game_date"].shift(-1)
    d["next_runs_allowed"] = d.groupby("team")["runs_allowed"].shift(-1)
    d["gap_days"] = (d["next_date"] - d["game_date"]).dt.days
    b2b = d[d["gap_days"] == 1].copy()
    return b2b.rename(columns={"pitches": "prior_day_pitches"})[
        ["team", "game_date", "prior_day_pitches", "next_runs_allowed"]]


def _compare(pairs: pd.DataFrame, season: int) -> Dict[str, Any]:
    if len(pairs) < 2 * MIN_GROUP_N:
        return {"hypothesis": "staff_dayafter_fatigue_chain", "n": int(len(pairs)), "effect": None, "p": None,
                "verdict": "NOT_TESTABLE", "note": "insufficient n=%d, season=%d" % (len(pairs), season)}
    q_hi, q_lo = pairs["prior_day_pitches"].quantile(HIGH_Q), pairs["prior_day_pitches"].quantile(LOW_Q)
    high = pairs[pairs["prior_day_pitches"] >= q_hi]["next_runs_allowed"]
    low = pairs[pairs["prior_day_pitches"] <= q_lo]["next_runs_allowed"]
    if len(high) < MIN_GROUP_N or len(low) < MIN_GROUP_N:
        return {"hypothesis": "staff_dayafter_fatigue_chain", "n": int(len(pairs)), "effect": None, "p": None,
                "verdict": "NOT_TESTABLE",
                "note": "insufficient group n after quartile split (%d high / %d low), season=%d"
                        % (len(high), len(low), season)}
    t, p = stats.ttest_ind(high, low, equal_var=False)
    eff = float(high.mean() - low.mean())
    return {"hypothesis": "staff_dayafter_fatigue_chain", "n": int(len(high) + len(low)), "effect": round(eff, 4),
            "p": float(p), "verdict": _verdict(p, 0.1, eff),
            "note": "mean runs allowed next day, prior-day-pitches>=q75(%.0f) (%.3f, n=%d) vs <=q25(%.0f) "
                    "(%.3f, n=%d), season=%d" % (q_hi, high.mean(), len(high), q_lo, low.mean(), len(low), season)}


def _combine(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Same convention as validate_reliever_b2b_fatigue._combine: only a
    positive significant effect (heavy prior-day staff use -> MORE runs
    allowed next day) counts as support; a significant negative effect is
    reported but never counted (more plausibly a schedule/opponent-quality
    confound than staff fatigue)."""
    testable = [r for r in rows if r["verdict"] != "NOT_TESTABLE"]
    sig_support = [r for r in testable if r["p"] < ALPHA and r["effect"] > 0]
    sig_reverse = [r for r in testable if r["p"] < ALPHA and r["effect"] < 0]
    if len(testable) < 2:
        verdict = "NOT_TESTABLE"
    elif len(sig_support) >= 2:
        verdict = "CONFIRMED_LOCAL"
    elif len(sig_support) == 1:
        verdict = "PROVISIONAL"
    else:
        verdict = "NULL_LOCAL"
    seasons_note = "; ".join("%d:%s(p=%s,eff=%s)" % (s, r["verdict"], r["p"], r["effect"])
                              for s, r in zip(SEASONS, rows))
    reverse_note = (" -- %d season(s) significant REVERSE direction (not counted as support)" % len(sig_reverse)
                     if sig_reverse else "")
    return {"hypothesis": "staff_dayafter_fatigue_chain__combined", "n": int(sum(r["n"] for r in rows)),
            "effect": None, "p": None, "verdict": verdict,
            "note": "cross-season replication (%d independent season corpora): %s%s"
                     % (len(SEASONS), seasons_note, reverse_note)}


def run() -> List[Dict[str, Any]]:
    rows = []
    for season in SEASONS:
        pairs = build_dayafter_pairs(team_day_table(load_season(season)))
        rows.append(_compare(pairs, season))
    out = rows + [_combine(rows)]
    for r in out:
        r["sport"] = "mlb"
        r["corpus"] = "savant_full__2023-2025_team_day_pitchcount"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return out


def main() -> int:
    for r in run():
        print("%-34s %-16s n=%-6s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
