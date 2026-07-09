"""domains.basketball_nba.knowledge.validate_schedule_fatigue -- 3 UNTESTED
schedule/rest mechanisms against the 2024-25 + 2025-26 player_boxscores
corpus (2,381 games). Leak audit: rest_days and the 3-in-4 flag are both
computed from the SCHEDULE alone (calendar gaps between a team's own games),
known well before tipoff -- no outcome leaks into either predictor.

Run: python -m domains.basketball_nba.knowledge.validate_schedule_fatigue
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
from scipy import stats

from domains.basketball_nba.knowledge._data import LEDGER_PATH, load_player_boxscores, team_game_frame
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def b2b_rest_penalty(tg) -> Dict[str, Any]:
    d = tg.dropna(subset=["rest_days"])
    b2b = d[d["rest_days"] == 0]["margin"]
    rested = d[d["rest_days"] >= 1]["margin"]
    t, p = stats.ttest_ind(b2b, rested, equal_var=False)
    return {"hypothesis": "b2b_rest_penalty", "n": int(len(d)),
            "effect": round(float(b2b.mean() - rested.mean()), 3), "p": float(p),
            "verdict": _verdict(p, b2b.mean() - rested.mean(), 0.5),
            "note": "avg margin on 0-rest (%.2f, n=%d) vs >=1-day rest (%.2f, n=%d)"
                    % (b2b.mean(), len(b2b), rested.mean(), len(rested))}


def three_in_four_fatigue(tg) -> Dict[str, Any]:
    d = tg.sort_values(["team", "date"]).copy()
    d["games_last4d"] = 0
    for team, grp in d.groupby("team"):
        dates = grp["date"].values
        counts = [int(((dates >= (dt - np.timedelta64(3, "D"))) & (dates <= dt)).sum()) for dt in dates]
        d.loc[grp.index, "games_last4d"] = counts
    fatigued = d[d["games_last4d"] >= 3]["margin"]
    fresh = d[d["games_last4d"] < 3]["margin"]
    t, p = stats.ttest_ind(fatigued, fresh, equal_var=False)
    return {"hypothesis": "three_in_four_fatigue", "n": int(len(d)),
            "effect": round(float(fatigued.mean() - fresh.mean()), 3), "p": float(p),
            "verdict": _verdict(p, fatigued.mean() - fresh.mean(), 0.5),
            "note": "avg margin 3-in-4 (%.2f, n=%d) vs not (%.2f, n=%d)"
                    % (fatigued.mean(), len(fatigued), fresh.mean(), len(fresh))}


def home_court_advantage_magnitude(tg) -> Dict[str, Any]:
    home = tg[tg["is_home"] == 1]["margin"]
    away = tg[tg["is_home"] == 0]["margin"]
    t, p = stats.ttest_ind(home, away, equal_var=False)
    return {"hypothesis": "home_court_advantage_magnitude", "n": int(len(tg)),
            "effect": round(float(home.mean() - away.mean()), 3), "p": float(p),
            "verdict": _verdict(p, home.mean() - away.mean(), 0.5),
            "note": "avg margin home (%.2f, n=%d) vs away (%.2f, n=%d); home win%%=%.3f"
                    % (home.mean(), len(home), away.mean(), len(away), tg[tg["is_home"] == 1]["win"].mean())}


def run() -> List[Dict[str, Any]]:
    tg = team_game_frame(load_player_boxscores())
    rows = [b2b_rest_penalty(tg), three_in_four_fatigue(tg), home_court_advantage_magnitude(tg)]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "player_boxscores_2024_25_2025_26"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-32s %-16s n=%-6d effect=%+.3f p=%.4g -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 1.0, 0.5) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 1.0, 0.5) == "NULL_LOCAL"
    print("self-check OK")
