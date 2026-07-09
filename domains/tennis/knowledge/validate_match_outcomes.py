"""domains.tennis.knowledge.validate_match_outcomes -- 5 UNTESTED match-level
mechanisms against the 2015-2025 ATP+WTA match corpus (matches.parquet /
wta_matches.parquet joined to players.parquet hand/dob and
schedule_density.parquet rest_days). Leak audit: p1_rank/p2_rank are the REAL
pre-match ATP/WTA rankings already fixed as-of that tournament (not a
season-final aggregate); hand and dob are static player attributes; rest_days
in schedule_density is computed from matches strictly BEFORE event_id (as-of
by construction in ingest_schedule_density.py). Every test below is a
cross-sectional, same-match comparison -- no future-into-past leak.

Run: python -m domains.tennis.knowledge.validate_match_outcomes
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.tennis.knowledge._data import (
    LEDGER_PATH, load_matches, load_players, load_schedule_density,
)
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
RANK_CLOSE = 50.0
_FIRST_SET_RE = re.compile(r"^(\d+)-(\d+)")


def _with_rank_diff(m: pd.DataFrame) -> pd.DataFrame:
    d = m.dropna(subset=["p1_rank", "p2_rank", "winner"]).copy()
    d["rank_diff"] = d["p2_rank"] - d["p1_rank"]   # positive => p1 is the favorite
    d["p1_win"] = (d["winner"] == 1).astype(int)
    return d


def ranking_gap_nonlinearity(m: pd.DataFrame) -> Dict[str, Any]:
    """Is P(win) linear in ranking gap, or does it flatten at the extremes
    (diminishing returns to an already-decisive gap)? Nested F-test: does a
    quadratic term in rank_diff improve the fit over linear across ranking-
    gap decile bins."""
    d = _with_rank_diff(m)
    bins = pd.qcut(d["rank_diff"], 12, duplicates="drop")
    g = d.groupby(bins, observed=True).agg(x=("rank_diff", "mean"), y=("p1_win", "mean"),
                                            n=("p1_win", "size"))
    if len(g) - 3 <= 0:
        return {"hypothesis": "ranking_gap_nonlinearity", "n": int(len(d)), "effect": 0.0,
                "p": float("nan"), "note": "too few ranking-gap bins for a quadratic F-test"}
    lin = np.polyfit(g["x"], g["y"], 1)
    quad = np.polyfit(g["x"], g["y"], 2)
    rss1 = float(np.sum((g["y"] - np.polyval(lin, g["x"])) ** 2))
    rss2 = float(np.sum((g["y"] - np.polyval(quad, g["x"])) ** 2))
    dfn, dfd = 1, len(g) - 3
    f = ((rss1 - rss2) / dfn) / (rss2 / dfd) if rss2 > 0 else float("inf")
    p = float(stats.f.sf(f, dfn, dfd))
    return {"hypothesis": "ranking_gap_nonlinearity", "n": int(len(d)),
            "effect": round(rss1 - rss2, 6), "p": p,
            "note": "RSS improvement (linear->quadratic) across %d rank-gap bins, rss1=%.5f rss2=%.5f"
                    % (len(g), rss1, rss2)}


def lefty_advantage_on_return(m: pd.DataFrame, players: pd.DataFrame) -> Dict[str, Any]:
    """In rank-controlled mixed-handedness matches, does the right-handed
    player's win rate differ from 0.5 -- i.e. does facing a lefty change
    outcomes net of rank."""
    d = _with_rank_diff(m)
    h = players.set_index("player_id")["hand"]
    h1, h2 = d["p1_id"].map(h), d["p2_id"].map(h)
    mixed = d[(h1.isin(["R", "L"])) & (h2.isin(["R", "L"])) & (h1 != h2)
              & (d["rank_diff"].abs() <= RANK_CLOSE)]
    if mixed.empty:
        return {"hypothesis": "lefty_advantage_on_return", "n": 0, "effect": 0.0,
                "p": float("nan"), "note": "no rank-close mixed-handedness matches"}
    r_is_p1 = h1.loc[mixed.index] == "R"
    r_won = np.where(r_is_p1, mixed["p1_win"] == 1, mixed["p1_win"] == 0).astype(int)
    t, p = stats.ttest_1samp(r_won, 0.5)
    return {"hypothesis": "lefty_advantage_on_return", "n": int(len(mixed)),
            "effect": round(float(r_won.mean() - 0.5), 4), "p": float(p),
            "note": "right-handed player win-rate vs left-handed opponent %.4f (n=%d, |rank_diff|<=%d)"
                    % (r_won.mean(), len(mixed), int(RANK_CLOSE))}


def age_prime_band_advantage(m: pd.DataFrame, players: pd.DataFrame) -> Dict[str, Any]:
    """Population-level (not opponent-matched) win-rate comparison: players in
    a 24-29 'prime' age band vs everyone else."""
    dob = pd.to_datetime(players.set_index("player_id")["dob"])
    d = m.dropna(subset=["winner", "date"]).copy()
    d["date"] = pd.to_datetime(d["date"])
    rows = []
    for slot, opp_win in ((1, 1), (2, 2)):
        age = (d["date"] - d["p%d_id" % slot].map(dob)).dt.days / 365.25
        rows.append(pd.DataFrame({"age": age, "win": (d["winner"] == opp_win).astype(int)}))
    long = pd.concat(rows, ignore_index=True).dropna(subset=["age"])
    prime = long.loc[(long["age"] >= 24) & (long["age"] <= 29), "win"]
    other = long.loc[(long["age"] < 24) | (long["age"] > 29), "win"]
    t, p = stats.ttest_ind(prime, other, equal_var=False)
    return {"hypothesis": "age_prime_band_advantage", "n": int(len(long)),
            "effect": round(float(prime.mean() - other.mean()), 5), "p": float(p),
            "note": "win-rate age 24-29 %.4f (n=%d) vs other ages %.4f (n=%d)"
                    % (prime.mean(), len(prime), other.mean(), len(other))}


def fatigue_load_correlates_with_retirement(m: pd.DataFrame, sched: pd.DataFrame) -> Dict[str, Any]:
    """Does combined recent match load (matches_last_7d, both players
    averaged) run higher in matches that end in a retirement."""
    load = sched.set_index(["event_id", "player_id"])["matches_last_7d"]
    d = m.dropna(subset=["retirement", "p1_id", "p2_id"]).copy()
    l1 = pd.Series(list(zip(d["event_id"], d["p1_id"])), index=d.index).map(load)
    l2 = pd.Series(list(zip(d["event_id"], d["p2_id"])), index=d.index).map(load)
    d["combined_load"] = (l1 + l2) / 2.0
    d = d.dropna(subset=["combined_load"])
    ret, no_ret = d.loc[d["retirement"], "combined_load"], d.loc[~d["retirement"], "combined_load"]
    t, p = stats.ttest_ind(ret, no_ret, equal_var=False)
    return {"hypothesis": "fatigue_load_correlates_with_retirement", "n": int(len(d)),
            "effect": round(float(ret.mean() - no_ret.mean()), 4), "p": float(p),
            "note": "combined matches_last_7d retirement=True %.3f (n=%d) vs False %.3f (n=%d)"
                    % (ret.mean(), len(ret), no_ret.mean(), len(no_ret))}


def _first_set_won_by_match_winner(score: Any) -> int:
    """`score` is written from the MATCH WINNER's perspective in every set
    token (verified empirically: the front number wins the aggregate set
    count in 98.9% of rows, vs 51% if read as p1-p2 -- this corpus is
    winner-first, not p1-first). So "front > back" on the FIRST set token
    directly means the match winner won set 1. Returns 1/0/-1 (unparseable)."""
    if not isinstance(score, str):
        return -1
    m = _FIRST_SET_RE.match(score.strip())
    if not m:
        return -1
    g1, g2 = int(m.group(1)), int(m.group(2))
    if g1 == g2:
        return -1
    return 1 if g1 > g2 else 0


def first_set_winner_match_win_rate(m: pd.DataFrame) -> Dict[str, Any]:
    """P(the match winner also won set 1) -- equivalently, P(win the match |
    won the first set), since exactly one player wins set 1 each match.
    Expected far above 0.5 -- the classic, expected-to-CONFIRM population
    claim."""
    d = m.dropna(subset=["winner", "score"]).copy()
    d["winner_won_set1"] = d["score"].map(_first_set_won_by_match_winner)
    valid = d.loc[d["winner_won_set1"] != -1, "winner_won_set1"]
    t, p = stats.ttest_1samp(valid, 0.5)
    return {"hypothesis": "first_set_winner_match_win_rate", "n": int(len(valid)),
            "effect": round(float(valid.mean() - 0.5), 4), "p": float(p),
            "note": "match-win rate given first-set win = %.4f (n=%d)" % (valid.mean(), len(valid))}


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def run() -> List[Dict[str, Any]]:
    m = load_matches()
    players = load_players()
    sched = load_schedule_density()
    rows = [
        (ranking_gap_nonlinearity(m), 0.001),
        (lefty_advantage_on_return(m, players), 0.02),
        (age_prime_band_advantage(m, players), 0.01),
        (fatigue_load_correlates_with_retirement(m, sched), 0.05),
        (first_set_winner_match_win_rate(m), 0.1),
    ]
    out = []
    for r, min_eff in rows:
        r["verdict"] = _verdict(r["p"], r["effect"], min_eff)
        r["sport"] = "tennis"
        r["corpus"] = "atp_wta_matches_2015_2025"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
        out.append(r)
    return out


def main() -> int:
    for r in run():
        print("%-42s %-16s n=%-8d effect=%+.5f p=%.4g -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: first-set-winner parser + verdict thresholds."""
    assert _first_set_won_by_match_winner("6-3 6-1") == 1
    assert _first_set_won_by_match_winner("4-6 6-1 6-4") == 0
    assert _first_set_won_by_match_winner("7-6(5) 6-4") == 1
    assert _first_set_won_by_match_winner(None) == -1
    assert _verdict(0.001, 0.5, 0.15) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.15) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.15) == "NOT_TESTABLE"
    print("self-check OK")
