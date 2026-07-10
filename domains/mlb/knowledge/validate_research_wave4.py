"""domains.mlb.knowledge.validate_research_wave4 -- the 1 UNTESTED row seeded
2026-07-10 by the round-4 research-wave commit (mechanisms.md #52 batting-team
baserunning aggression vs opponent outfield-arm reputation). Mirrors
validate_research_wave3's per-file pattern: pure frame-transform helpers + one
hypothesis function + a local _verdict/_combine copy (self-contained, not
shared across waves).

PREMISE CHECK (this session, fresh): `data/domains/mlb/espn_boxscores.parquet`
confirmed 3,880 rows (2025-03-27..2026-07-09), the 6 named columns
(home/away_bat_stolenBases, home/away_bat_caughtStealing,
home/away_fld_outfieldAssists) all present with 3,874 non-null rows on that
subset, combined SB+CS per team-game mean=0.891 std=1.101 max=10 -- matches
the row's own premise-check text exactly. `event_id` has zero duplicates (one
row per game). `home_abbr`/`away_abbr` (31 codes each) are the team keys used
below; the row's premise text did not name them but they are required to
unpivot to team-perspective rows and are the only team-identity columns in
the file.

Not a re-test of #19 (savant_full__2025's `events` column has zero SB/CS
values at all, closed NOT_TESTABLE on a different corpus, verified via
mechanisms.md #19 + validate_data_gaps.py::_sb_not_testable) -- this row uses
espn_boxscores.parquet exclusively. Greped `validation_ledger.jsonl` +
reject_ledger.jsonl fresh this session for `baserun`/`outfield.*arm`: 0 prior
hypothesis-name hits.

Leak audit: fielding team's arm-reputation input is a LEAVE-ONE-OUT season
mean of its own `outfieldAssists` (excludes the target game itself), joined
to the batting team's SB+CS in that same game -- no future information
relative to the game being scored (the LOO mean draws on the team's OTHER
games, which include games both before and after the target date; this is a
same-season descriptive reputation proxy, not a forecast, and the row's own
claim is scoped as a same-season correlation, not an as-of prediction, so
this is consistent with the row's stated design, not a leak into a live
prediction).

Run: python -m domains.mlb.knowledge.validate_research_wave4
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge._data import LEDGER_PATH, REPO
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_EFFECT = {"baserunning_aggression_vs_outfield_arm_deterrence": 0.05}


def _verdict(p, effect, hyp: str) -> str:
    if p is None or effect is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    base = hyp.split("__")[0]
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= MIN_EFFECT[base]) else "NULL_LOCAL"


def _team_game_outfield_assists(df: pd.DataFrame) -> pd.DataFrame:
    """Pure helper: unpivot home/away rows to one row per team-game with that
    team's fielding-side outfieldAssists count for the game."""
    home = df[["event_id", "date", "home_abbr", "home_fld_outfieldAssists"]].rename(
        columns={"home_abbr": "team", "home_fld_outfieldAssists": "outfield_assists"})
    away = df[["event_id", "date", "away_abbr", "away_fld_outfieldAssists"]].rename(
        columns={"away_abbr": "team", "away_fld_outfieldAssists": "outfield_assists"})
    tg = pd.concat([home, away], ignore_index=True)
    return tg.dropna(subset=["outfield_assists"])


def _leave_one_out_arm_rate(tg: pd.DataFrame) -> pd.DataFrame:
    """Pure helper: adds loo_rate = team's season mean outfieldAssists
    EXCLUDING the row's own game (avoids circularity). Teams with only 1
    game in the frame are dropped (LOO undefined)."""
    grp = tg.groupby("team")["outfield_assists"]
    total, count = grp.transform("sum"), grp.transform("count")
    out = tg.copy()
    out["loo_rate"] = (total - out["outfield_assists"]) / (count - 1)
    return out[count > 1]


def _batting_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Pure helper: unpivot to one row per batting-team-game with that
    team's SB+CS attempts and the OPPONENT (fielding) team's code."""
    home = df[["event_id", "date", "home_abbr", "away_abbr",
               "home_bat_stolenBases", "home_bat_caughtStealing"]].rename(
        columns={"home_abbr": "bat_team", "away_abbr": "opp_team",
                 "home_bat_stolenBases": "sb", "home_bat_caughtStealing": "cs"})
    away = df[["event_id", "date", "away_abbr", "home_abbr",
               "away_bat_stolenBases", "away_bat_caughtStealing"]].rename(
        columns={"away_abbr": "bat_team", "home_abbr": "opp_team",
                 "away_bat_stolenBases": "sb", "away_bat_caughtStealing": "cs"})
    b = pd.concat([home, away], ignore_index=True).dropna(subset=["sb", "cs"])
    b["sb_cs"] = b["sb"] + b["cs"]
    return b


def _merged_baserunning_arm(df: pd.DataFrame) -> pd.DataFrame:
    """Join each batting-team-game's sb_cs to the opponent's LOO arm rate for
    that same game (via event_id + opp_team==team)."""
    tg = _leave_one_out_arm_rate(_team_game_outfield_assists(df))
    bat = _batting_rows(df)
    return bat.merge(tg[["event_id", "team", "loo_rate"]],
                      left_on=["event_id", "opp_team"], right_on=["event_id", "team"], how="inner")


def baserunning_aggression_vs_outfield_arm_deterrence(merged: pd.DataFrame, half_label: str) -> Dict[str, Any]:
    hyp = "baserunning_aggression_vs_outfield_arm_deterrence__%s" % half_label
    if len(merged) < 30:
        return {"hypothesis": hyp, "n": int(len(merged)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 30 team-perspective rows", "corpus": "espn_boxscores"}
    r, p = stats.pearsonr(merged["sb_cs"], merged["loo_rate"])
    return {"hypothesis": hyp, "n": int(len(merged)), "effect": round(float(r), 4), "p": float(p),
            "verdict": _verdict(p, r, hyp), "corpus": "espn_boxscores",
            "note": ("Pearson r, batting-team SB+CS attempts vs opponent's leave-one-out season "
                      "outfieldAssists rate (n=%d); declared bar |r|>=0.05 and p<0.01." % len(merged))}


def _combine(base_hyp: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Both halves required, same direction -- mirrors wave3's >=2-corpora
    replication rule (a single significant half is PROVISIONAL, not CONFIRMED)."""
    testable = [r for r in rows if r["verdict"] != "NOT_TESTABLE"]
    sig = [r for r in testable if r["verdict"] == "CONFIRMED_LOCAL"]
    if len(testable) < 2:
        verdict = "NOT_TESTABLE"
    elif len(sig) == 2 and len({1 if r["effect"] > 0 else -1 for r in sig}) == 1:
        verdict = "CONFIRMED_LOCAL"
    elif len(sig) == 1:
        verdict = "PROVISIONAL"
    else:
        verdict = "NULL_LOCAL"
    return {"hypothesis": "%s__combined" % base_hyp, "n": int(sum(r["n"] for r in rows)),
            "effect": None, "p": None, "verdict": verdict,
            "note": "split-half-by-date, both halves required: %s"
                    % "; ".join("%s(p=%s,eff=%s)" % (r["hypothesis"], r["p"], r["effect"]) for r in rows)}


def run() -> List[Dict[str, Any]]:
    df = pd.read_parquet(REPO / "data" / "domains" / "mlb" / "espn_boxscores.parquet")
    merged = _merged_baserunning_arm(df)
    mid = merged["date"].median()
    halves = [baserunning_aggression_vs_outfield_arm_deterrence(merged[merged["date"] <= mid], "h1"),
              baserunning_aggression_vs_outfield_arm_deterrence(merged[merged["date"] > mid], "h2")]
    rows: List[Dict[str, Any]] = list(halves) + [_combine("baserunning_aggression_vs_outfield_arm_deterrence", halves)]

    for r in rows:
        r["sport"] = "mlb"
        r.setdefault("corpus", "espn_boxscores")
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-58s %-16s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict rule + the 3 pure frame-transform
    helpers on synthetic frames -- no parquet needed."""
    assert _verdict(0.001, -0.10, "baserunning_aggression_vs_outfield_arm_deterrence") == "CONFIRMED_LOCAL"
    assert _verdict(0.5, -0.10, "baserunning_aggression_vs_outfield_arm_deterrence") == "NULL_LOCAL"
    assert _verdict(0.001, -0.01, "baserunning_aggression_vs_outfield_arm_deterrence") == "NULL_LOCAL"  # below bar
    assert _verdict(None, -0.10, "baserunning_aggression_vs_outfield_arm_deterrence") == "NOT_TESTABLE"

    df = pd.DataFrame({
        "event_id": [1, 2, 3], "date": pd.to_datetime(["2025-04-01", "2025-04-02", "2025-04-03"]),
        "home_abbr": ["SF", "SF", "LAD"], "away_abbr": ["LAD", "LAD", "SF"],
        "home_fld_outfieldAssists": [0.0, 1.0, 2.0], "away_fld_outfieldAssists": [1.0, 0.0, 0.0],
        "home_bat_stolenBases": [1.0, 0.0, 2.0], "home_bat_caughtStealing": [0.0, 1.0, 0.0],
        "away_bat_stolenBases": [0.0, 1.0, 0.0], "away_bat_caughtStealing": [1.0, 0.0, 1.0],
    })
    tg = _team_game_outfield_assists(df)
    assert len(tg) == 6
    loo = _leave_one_out_arm_rate(tg)
    sf_row1 = loo[(loo["team"] == "SF") & (loo["event_id"] == 1)]
    # SF plays 3 games (home ev1=0.0, home ev2=1.0, away ev3=0.0); LOO for ev1
    # excludes its own 0.0: (1.0-0.0)/(3-1) = 0.5.
    assert sf_row1["loo_rate"].iloc[0] == 0.5

    bat = _batting_rows(df)
    assert len(bat) == 6
    assert set(bat["bat_team"]) == {"SF", "LAD"}

    merged = _merged_baserunning_arm(df)
    assert len(merged) == 6
    assert "loo_rate" in merged.columns

    print("self-check OK")
