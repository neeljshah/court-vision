"""domains.tennis.knowledge.validate_research_wave5 -- the 1 tennis
literature-sourced UNTESTED row seeded 2026-07-10 by the round-5 research-
wave commit (29628281, mechanisms.md row #40): return-depth aggressiveness
persistence.

PREMISE CHECK (hard, this session, fresh): `data/domains/tennis/_raw/
sackmann_pbp_repos/tennis_MatchChartingProject/charting-m-stats-
ReturnDepth.csv` confirmed -- columns match_id/player/row/returnable/
shallow/deep/very_deep present; `row`=='Total' subset: 15,115 player-match
rows across 7,545 matches, 1,002 distinct players (matches the row's premise
numbers exactly). Every `match_id` starts with an 8-digit YYYYMMDD date
prefix (verified 100% on the Total subset) -- used directly for split-half
date ordering instead of an extra join to charting-m-matches.csv's Date
column (same information already embedded, no separate file read needed).

Mirrors the split-half persistence design already used by CONFIRMED #18 and
NULL #30/#32: groupby (player, half) with a >=5-matches/half floor, unstack,
require >=15 players in BOTH halves, raw split-half Pearson r.

Run: python -m domains.tennis.knowledge.validate_research_wave5
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
from scipy import stats

from domains.tennis.knowledge._data import LEDGER_PATH, REPO
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_ABS_R = 0.15
MIN_MATCHES_PER_HALF = 5
MIN_PLAYERS = 15
RETURN_DEPTH_PATH = (REPO / "data" / "domains" / "tennis" / "_raw" / "sackmann_pbp_repos" /
                      "tennis_MatchChartingProject" / "charting-m-stats-ReturnDepth.csv")


def _verdict(p, effect) -> str:
    if p is None or effect is None or p != p:
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= MIN_ABS_R) else "NULL_LOCAL"


def _add_deep_rate_and_date(df: pd.DataFrame) -> pd.DataFrame:
    """Pure helper: Total-row subset with deep_rate = (deep+very_deep)/
    returnable per player-match, and date parsed from the match_id's
    embedded YYYYMMDD prefix. Rows with returnable==0 are dropped (rate
    undefined)."""
    tot = df[(df["row"] == "Total") & (df["returnable"] > 0)].copy()
    tot["deep_rate"] = (tot["deep"] + tot["very_deep"]) / tot["returnable"]
    tot["date"] = pd.to_datetime(tot["match_id"].str[:8], format="%Y%m%d", errors="coerce")
    return tot.dropna(subset=["date"])


def load_return_depth_totals(path: Path = RETURN_DEPTH_PATH) -> pd.DataFrame:
    return _add_deep_rate_and_date(pd.read_csv(path))


def return_depth_aggressiveness_persistence(tot: pd.DataFrame) -> Dict[str, Any]:
    mid = tot["date"].median()
    half = np.where(tot["date"] < mid, "A", "B")
    g = tot.assign(half=half).groupby(["player", "half"]).agg(
        deep_rate=("deep_rate", "mean"), n=("deep_rate", "size"))
    g = g[g["n"] >= MIN_MATCHES_PER_HALF]
    piv = g["deep_rate"].unstack("half").dropna()
    if len(piv) < MIN_PLAYERS:
        return {"hypothesis": "return_depth_aggressiveness_persistence", "n": int(len(piv)), "effect": None,
                "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than %d players with >=%d matches in BOTH date-halves" % (MIN_PLAYERS, MIN_MATCHES_PER_HALF)}
    r, p = stats.pearsonr(piv["A"], piv["B"])
    return {"hypothesis": "return_depth_aggressiveness_persistence", "n": int(len(piv)), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, r),
            "note": "split-half pearson r, per-player deep-return rate (deep+very_deep)/returnable, "
                    "n=%d players (>=%d matches/half)" % (len(piv), MIN_MATCHES_PER_HALF)}


def run() -> list:
    tot = load_return_depth_totals()
    rows = [return_depth_aggressiveness_persistence(tot)]
    for r in rows:
        r["sport"] = "tennis"
        r["corpus"] = "match_charting_project_return_depth"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-40s %-16s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.2) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.2) == "NULL_LOCAL"
    assert _verdict(0.001, 0.05) == "NULL_LOCAL"  # below MIN_ABS_R
    assert _verdict(None, 0.2) == "NOT_TESTABLE"

    df = pd.DataFrame({
        "row": ["Total", "Total", "Header"], "player": ["A", "A", "A"],
        "returnable": [50, 0, 50], "deep": [10, 5, 5], "very_deep": [0, 0, 0],
        "match_id": ["20200101-x", "20220101-x", "20220101-x"],
    })
    tot = _add_deep_rate_and_date(df)
    assert len(tot) == 1  # Header row filtered, returnable==0 row dropped
    assert tot.iloc[0]["deep_rate"] == 0.2
    assert tot.iloc[0]["date"] == pd.Timestamp("2020-01-01")
    print("self-check OK")
