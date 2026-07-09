"""domains.soccer.knowledge.validate_pressing_defense -- 3 UNTESTED team-style
mechanisms (mechanisms.md #18 set-piece xG share vs possession share, #19
pressing-intensity (PPDA proxy) vs opponent-turnover rate, #26 defensive
block-height proxy vs opponent shot xG) against the full local StatsBomb
event cache (~3,400 matches, no match_meta join needed -- team-match grain,
one pass per match). Leak audit: every measure is derived from the SAME
match's own events for both teams -- a cross-sectional descriptive
comparison across team-match units, not a forecast feature.

Run: python -m domains.soccer.knowledge.validate_pressing_defense
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
from scipy import stats

from domains.soccer.knowledge._data import LEDGER_PATH, iter_all_event_files
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
SETPIECE_TYPES = {"Corner", "Free Kick", "Penalty"}
DEF_ACTION_TYPES = {"Pressure", "Duel", "Interception"}
BLOCK_ACTION_TYPES = {"Pressure", "Interception", "Duel", "Clearance"}


def _verdict(p, min_abs_effect: float, effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _per_match_team_stats(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """One pass -> per-team-in-this-match dict of the raw counts/sums every
    function below needs (pass count, defensive-action count, set-piece/
    open-play xG, def-action mean x, shot mean x, own-shot xG mean)."""
    teams: Dict[str, Dict[str, Any]] = {}

    def _t(name: str) -> Dict[str, Any]:
        return teams.setdefault(name, {
            "passes": 0, "def_actions": 0, "recoveries": 0, "interceptions": 0, "setpiece_xg": 0.0,
            "openplay_xg": 0.0, "def_x_sum": 0.0, "def_x_n": 0, "shot_x_sum": 0.0, "shot_x_n": 0,
        })

    for e in events:
        team = (e.get("team") or {}).get("name")
        if not team:
            continue
        etype = e["type"]["name"]
        d = _t(team)
        if etype == "Pass":
            d["passes"] += 1
        elif etype in DEF_ACTION_TYPES:
            d["def_actions"] += 1
            if etype == "Interception":
                d["interceptions"] += 1
        elif etype == "Ball Recovery":
            d["recoveries"] += 1
        if etype in BLOCK_ACTION_TYPES:
            loc = e.get("location")
            if loc:
                d["def_x_sum"] += loc[0]
                d["def_x_n"] += 1
        if etype == "Shot":
            shot = e.get("shot") or {}
            xg = shot.get("statsbomb_xg")
            loc = e.get("location")
            if xg is not None:
                stype = (shot.get("type") or {}).get("name")
                if stype in SETPIECE_TYPES:
                    d["setpiece_xg"] += xg
                else:
                    d["openplay_xg"] += xg
            if loc:
                d["shot_x_sum"] += loc[0]
                d["shot_x_n"] += 1
    return teams


def setpiece_xg_share_vs_possession(rows: List[Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    xs, ys = [], []
    for teams in rows:
        names = list(teams.keys())
        if len(names) != 2:
            continue
        total_passes = sum(teams[n]["passes"] for n in names)
        if total_passes == 0:
            continue
        for n in names:
            total_xg = teams[n]["setpiece_xg"] + teams[n]["openplay_xg"]
            if total_xg <= 0:
                continue
            xs.append(teams[n]["passes"] / total_passes)  # possession-share proxy
            ys.append(teams[n]["setpiece_xg"] / total_xg)  # set-piece xG share
    r, p = stats.pearsonr(xs, ys)
    return {"hypothesis": "setpiece_xg_share_vs_possession", "n": len(xs), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.05, r),
            "note": "pearson r, team-match pass-share (possession proxy) vs set-piece-xG/total-xG share, "
                    "n=%d team-match units" % len(xs)}


def pressing_ppda_vs_turnover_rate(rows: List[Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    ppda, turnover = [], []
    for teams in rows:
        names = list(teams.keys())
        if len(names) != 2:
            continue
        for n in names:
            opp = [o for o in names if o != n][0]
            opp_passes = teams[opp]["passes"]
            def_actions = teams[n]["def_actions"]
            if opp_passes < 20 or def_actions == 0:
                continue
            ppda.append(opp_passes / def_actions)
            turnover.append((teams[n]["interceptions"] + teams[n]["recoveries"]) / opp_passes)
    r, p = stats.pearsonr(ppda, turnover)
    return {"hypothesis": "pressing_ppda_vs_turnover_rate", "n": len(ppda), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.05, r),
            "note": "pearson r, team-match PPDA-proxy (opp passes / own Pressure+Duel+Interception count) "
                    "vs (interceptions+recoveries)-per-opp-pass, n=%d team-match units (expect negative: "
                    "lower PPDA [more pressing] -> higher turnover rate)" % len(ppda)}


def defensive_block_height_vs_opponent_xg(rows: List[Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    block_proxy, opp_xg = [], []
    for teams in rows:
        names = list(teams.keys())
        if len(names) != 2:
            continue
        for n in names:
            opp = [o for o in names if o != n][0]
            d = teams[n]
            if d["def_x_n"] == 0 or d["shot_x_n"] == 0:
                continue
            own_def_x = d["def_x_sum"] / d["def_x_n"]
            own_shot_x = d["shot_x_sum"] / d["shot_x_n"]
            # direction-agnostic proxy: distance between where a team defends and where it
            # attacks -- a deep/direct block sits far from its own attacking territory, a
            # compact high press sits close to it. Does not require knowing absolute pitch
            # orientation (which StatsBomb does not label per period).
            block_proxy.append(abs(own_def_x - own_shot_x))
            opp_d = teams[opp]
            if opp_d["shot_x_n"] == 0:
                continue
            opp_xg.append((opp_d["setpiece_xg"] + opp_d["openplay_xg"]) /
                          max(1, opp_d["shot_x_n"]))
    n = min(len(block_proxy), len(opp_xg))
    block_proxy, opp_xg = block_proxy[:n], opp_xg[:n]
    r, p = stats.pearsonr(block_proxy, opp_xg)
    return {"hypothesis": "defensive_block_height_vs_opponent_xg", "n": n, "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.05, r),
            "note": "pearson r, |own defensive-action mean x - own shot mean x| (direction-agnostic block-"
                    "height/compactness proxy) vs opponent mean xG-per-shot, n=%d team-match units" % n}


def run() -> List[Dict[str, Any]]:
    rows = [_per_match_team_stats(events) for _, events in iter_all_event_files()]
    out = [setpiece_xg_share_vs_possession(rows), pressing_ppda_vs_turnover_rate(rows),
           defensive_block_height_vs_opponent_xg(rows)]
    for r in out:
        r["sport"] = "soccer"
        r["corpus"] = "statsbomb_events_full_cache"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return out


def main() -> int:
    for r in run():
        print("%-36s %-16s n=%-8d effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.02, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.02, 0.1) == "NULL_LOCAL"
    print("self-check OK")
