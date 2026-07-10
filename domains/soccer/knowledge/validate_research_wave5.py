"""domains.soccer.knowledge.validate_research_wave5 -- the 1 soccer
literature-sourced UNTESTED row seeded 2026-07-10 by the round-5 research-
wave commit (29628281, mechanisms.md row #42): goalkeeper distribution style
vs downstream buildup xG, distinct from CONFIRMED #20 (retention-only).

PREMISE CHECK (this session, fresh): `data/cache/statsbomb/events/*.json`
(4,235 cached match files) confirmed every event carries a `possession`
integer field and every Shot event carries `shot.statsbomb_xg` -- a goal-
kick's `possession` id links directly to any shot(s) sharing that id within
the same match (StatsBomb possession ids are per-match, not global, so this
join never crosses a match boundary -- no leak risk).

Leak audit: buildup_xg is computed from events strictly WITHIN the same
already-played match as the goal kick -- a contemporaneous descriptive
check, same leak posture as #20's own retention test.

Run: python -m domains.soccer.knowledge.validate_research_wave5
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
from scipy import stats

from domains.soccer.knowledge._data import LEDGER_PATH, iter_all_event_files
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_ABS_GAP = 0.01  # xG
MIN_N = 30
SHORT_HEIGHTS = {"Ground Pass", "Low Pass"}


def _match_goal_kick_buildup_xg(events: List[Dict[str, Any]]) -> List[Tuple[str, float]]:
    """Per goal-kick Pass event in this match: (height, buildup_xg) where
    buildup_xg = max statsbomb_xg among Shot events sharing its possession id
    (0.0 if that possession produced no shot)."""
    shot_xg_by_poss: Dict[Any, float] = {}
    for e in events:
        if e["type"]["name"] == "Shot":
            poss = e.get("possession")
            xg = (e.get("shot") or {}).get("statsbomb_xg")
            if poss is not None and xg is not None:
                shot_xg_by_poss[poss] = max(shot_xg_by_poss.get(poss, 0.0), float(xg))
    out = []
    for e in events:
        if e["type"]["name"] != "Pass":
            continue
        p = e.get("pass") or {}
        if (p.get("type") or {}).get("name") != "Goal Kick":
            continue
        height = (p.get("height") or {}).get("name")
        out.append((height, shot_xg_by_poss.get(e.get("possession"), 0.0)))
    return out


def gk_distribution_vs_buildup_xg(goal_kicks: List[Tuple[str, float]]) -> Dict[str, Any]:
    short_xg = np.array([x for h, x in goal_kicks if h in SHORT_HEIGHTS])
    long_xg = np.array([x for h, x in goal_kicks if h == "High Pass"])
    if len(short_xg) < MIN_N or len(long_xg) < MIN_N:
        return {"hypothesis": "gk_distribution_vs_buildup_xg", "n": int(len(short_xg) + len(long_xg)),
                "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than %d goal kicks in one of the two height buckets" % MIN_N}
    stat, p = stats.mannwhitneyu(short_xg, long_xg, alternative="two-sided")
    mean_gap = float(short_xg.mean() - long_xg.mean())
    median_gap = float(np.median(short_xg) - np.median(long_xg))
    verdict = "CONFIRMED_LOCAL" if (p < ALPHA and (abs(mean_gap) >= MIN_ABS_GAP or abs(median_gap) >= MIN_ABS_GAP)) \
        else "NULL_LOCAL"
    return {"hypothesis": "gk_distribution_vs_buildup_xg", "n": int(len(short_xg) + len(long_xg)),
            "effect": round(mean_gap, 4), "p": float(p), "verdict": verdict,
            "note": "Mann-Whitney U, buildup xG in short/ground goal-kick possessions (mean=%.4f, median=%.4f, "
                    "n=%d) vs long/high (mean=%.4f, median=%.4f, n=%d); mean_gap=%+.4f median_gap=%+.4f"
                    % (short_xg.mean(), np.median(short_xg), len(short_xg), long_xg.mean(), np.median(long_xg),
                       len(long_xg), mean_gap, median_gap)}


def run() -> List[Dict[str, Any]]:
    goal_kicks: List[Tuple[str, float]] = []
    for _, events in iter_all_event_files():
        goal_kicks.extend(_match_goal_kick_buildup_xg(events))
    rows = [gk_distribution_vs_buildup_xg(goal_kicks)]
    for r in rows:
        r["sport"] = "soccer"
        r["corpus"] = "statsbomb_events_full_cache"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-32s %-16s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    events = [
        {"type": {"name": "Shot"}, "possession": 1, "shot": {"statsbomb_xg": 0.3}},
        {"type": {"name": "Pass"}, "possession": 1, "pass": {"type": {"name": "Goal Kick"},
                                                               "height": {"name": "Ground Pass"}}},
        {"type": {"name": "Pass"}, "possession": 2, "pass": {"type": {"name": "Goal Kick"},
                                                               "height": {"name": "High Pass"}}},
    ]
    gk = _match_goal_kick_buildup_xg(events)
    assert gk == [("Ground Pass", 0.3), ("High Pass", 0.0)]

    short = [("Ground Pass", 0.05)] * 40
    long = [("High Pass", 0.0)] * 40
    r = gk_distribution_vs_buildup_xg(short + long)
    assert r["verdict"] == "CONFIRMED_LOCAL"
    print("self-check OK")
