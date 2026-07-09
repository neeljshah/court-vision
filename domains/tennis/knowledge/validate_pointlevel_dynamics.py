"""domains.tennis.knowledge.validate_pointlevel_dynamics -- 3 UNTESTED
within-match point/game mechanisms (mechanisms.md #16 point-to-point
momentum, #20 deuce-game-length next-same-server fatigue, #26 break-point
conversion by set number) against slam_points.parquet (2011-2015, no
player-identity column exists on this corpus -- every check below uses only
server-slot (1/2) identity WITHIN one match, never a cross-match player
join). Leak audit: every comparison is strictly WITHIN one match's already-
played point sequence -- descriptive, not a forecast into a future match.

Run: python -m domains.tennis.knowledge.validate_pointlevel_dynamics
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.tennis.knowledge._data import LEDGER_PATH, load_slam_points
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
SCORE_RANK = {"0": 0, "15": 1, "30": 2, "40": 3, "AD": 4}


def _verdict(p, min_abs_effect: float, effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _clean_points(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["point_server"].isin([1, 2]) & df["point_winner"].isin([1, 2])].copy()
    return d.sort_values(["match_id", "set_no", "game_no", "point_number"])


def point_to_point_momentum(df: pd.DataFrame) -> Dict[str, Any]:
    """Same-server, same-game: does winning point i predict winning point
    i+1? (server is constant within a game, so this isolates a pure
    point-to-point streak effect without needing player identity.)"""
    d = _clean_points(df)
    d["server_won"] = (d["point_winner"] == d["point_server"]).astype(int)
    key = d["match_id"].astype(str) + "|" + d["set_no"].astype(str) + "|" + d["game_no"].astype(str)
    d["prev_won"] = d.groupby(key)["server_won"].shift(1)
    d = d.dropna(subset=["prev_won"])
    a = d.loc[d["prev_won"] == 1, "server_won"]
    b = d.loc[d["prev_won"] == 0, "server_won"]
    t, p = stats.ttest_ind(a, b, equal_var=False)
    eff = float(a.mean() - b.mean())
    return {"hypothesis": "point_to_point_momentum", "n": int(len(d)), "effect": round(eff, 4), "p": float(p),
            "verdict": _verdict(p, 0.01, eff),
            "note": "same-server-same-game momentum: server_won rate after winning prev point (%.4f, n=%d) "
                    "vs after losing prev point (%.4f, n=%d)" % (a.mean(), len(a), b.mean(), len(b))}


def deuce_game_length_next_server_fatigue(df: pd.DataFrame) -> Dict[str, Any]:
    d = _clean_points(df)
    games = d.groupby(["match_id", "set_no", "game_no"]).agg(
        n_points=("point_number", "size"), server=("point_server", "first"),
        last_winner=("point_winner", "last")).reset_index()
    games["held"] = (games["last_winner"] == games["server"]).astype(int)
    games = games.sort_values(["match_id", "set_no", "game_no"])
    games["next_game_no"] = games["game_no"] + 2
    nxt = games[["match_id", "set_no", "game_no", "server", "held"]].rename(
        columns={"game_no": "next_game_no", "server": "next_server", "held": "next_held"})
    m = games.merge(nxt, on=["match_id", "set_no", "next_game_no"])
    m = m[m["server"] == m["next_server"]]  # same server confirmed (should always hold, defensive check)
    m["long_game"] = m["n_points"] >= 8
    a = m.loc[m["long_game"], "next_held"]
    b = m.loc[~m["long_game"], "next_held"]
    t, p = stats.ttest_ind(a, b, equal_var=False)
    eff = float(a.mean() - b.mean())
    return {"hypothesis": "deuce_game_length_next_server_fatigue", "n": int(len(m)), "effect": round(eff, 4),
            "p": float(p), "verdict": _verdict(p, 0.01, eff),
            "note": "next-hold-rate for the SAME server 2 games later, after a long (>=8pt) game (%.4f, "
                    "n=%d) vs a short game (%.4f, n=%d)" % (a.mean(), len(a), b.mean(), len(b))}


def _break_point_flags(d: pd.DataFrame) -> pd.DataFrame:
    key = d["match_id"].astype(str) + "|" + d["set_no"].astype(str) + "|" + d["game_no"].astype(str)
    before_p1 = d.groupby(key)["p1_score"].shift(1).fillna("0")
    before_p2 = d.groupby(key)["p2_score"].shift(1).fillna("0")
    r1 = before_p1.map(SCORE_RANK)
    r2 = before_p2.map(SCORE_RANK)
    d = d[r1.notna() & r2.notna()].copy()
    r1, r2 = r1[r1.notna() & r2.notna()], r2[r1.notna() & r2.notna()]
    is_p1_server = d["point_server"] == 1
    returner_rank = np.where(is_p1_server, r2, r1)
    server_rank = np.where(is_p1_server, r1, r2)
    d["break_point"] = (returner_rank >= 3) & (returner_rank > server_rank)
    d["bp_converted"] = (d["break_point"] & (d["point_winner"] != d["point_server"])).astype(float)
    return d


def break_point_conversion_by_set_number(df: pd.DataFrame) -> Dict[str, Any]:
    d = _break_point_flags(_clean_points(df))
    bp = d[d["break_point"]]
    set1 = bp[bp["set_no"] == 1]["bp_converted"]
    set3plus = bp[bp["set_no"] >= 3]["bp_converted"]
    t, p = stats.ttest_ind(set3plus, set1, equal_var=False)
    eff = float(set3plus.mean() - set1.mean())
    return {"hypothesis": "break_point_conversion_by_set_number", "n": int(len(set1) + len(set3plus)),
            "effect": round(eff, 4), "p": float(p), "verdict": _verdict(p, 0.01, eff),
            "note": "break-point conversion rate, set>=3 (%.4f, n=%d) vs set==1 (%.4f, n=%d)"
                    % (set3plus.mean(), len(set3plus), set1.mean(), len(set1))}


def run() -> List[Dict[str, Any]]:
    df = load_slam_points()
    rows = [point_to_point_momentum(df), deuce_game_length_next_server_fatigue(df),
            break_point_conversion_by_set_number(df)]
    for r in rows:
        r["sport"] = "tennis"
        r["corpus"] = "slam_points_2011_2015"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-38s %-16s n=%-8d effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.02, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.02, 0.1) == "NULL_LOCAL"
    print("self-check OK")
