"""NYK/SAS Team System — Stage 2 core: parse cdn.nba.com PBP into structured data.

The repo had NO code to reconstruct 5-man lineups from substitution events; this is
that piece. parse_game() walks the play-by-play once and produces:
  - JOINT STINTS keyed by (home5, away5): closed whenever either side subs. Collapsing
    a side out yields true per-team 5-man net ratings (current season — the prior gap).
  - per-team game aggregates (pts, FGA/M, 3P, FT, OREB/DREB, TOV, AST, possessions,
    per-quarter pts, clutch pts, rim/mid/3 shot mix).

CDN liveData action schema (defensive .get throughout): actionType (2pt/3pt/freethrow/
rebound/turnover/foul/substitution/period/...), subType (in/out, offensive/defensive,
shot type), personId, teamId, period, clock "PT11M34.00S", scoreHome/scoreAway (cum,
on scoring actions), shotResult, shotDistance, assistPersonId, qualifiers[].

Imported by build_team_system.py. Pure functions, no I/O beyond reading cached JSON.
"""
from __future__ import annotations

import re

_CLK = re.compile(r"PT(?:(\d+)M)?(?:([\d.]+)S)?")


def parse_clock(s) -> float:
    """ISO duration -> seconds REMAINING in the period."""
    if not s:
        return 0.0
    m = _CLK.match(s)
    if not m:
        return 0.0
    return float(m.group(1) or 0) * 60 + float(m.group(2) or 0)


def period_len(p: int) -> int:
    return 720 if p <= 4 else 300


def game_sec(period: int, rem: float) -> float:
    """Cumulative elapsed game seconds at this moment."""
    before = sum(period_len(p) for p in range(1, period))
    return before + (period_len(period) - rem)


def load_meta(box: dict) -> dict:
    g = box["game"]
    h, a = g["homeTeam"], g["awayTeam"]
    starters = {}
    for tm in (h, a):
        s = set()
        for p in tm.get("players", []):
            if str(p.get("starter", "")).strip() in ("1", "true", "True") or p.get("starter") == 1:
                s.add(int(p["personId"]))
        starters[int(tm["teamId"])] = s
    return {
        "gid": g.get("gameId"),
        "home_id": int(h["teamId"]), "away_id": int(a["teamId"]),
        "home": h["teamTricode"], "away": a["teamTricode"],
        "starters": starters,
        "home_pts_box": h.get("score"), "away_pts_box": a.get("score"),
    }


def _blank_team():
    return dict(pts=0, fga=0, fgm=0, fg3a=0, fg3m=0, fta=0, ftm=0, oreb=0, dreb=0,
               tov=0, ast=0, paint_fga=0, paint_fgm=0, mid_fga=0, mid_fgm=0,
               rim_fga=0, rim_fgm=0, q_pts={}, clutch_pts=0)


def _shot_zone(act) -> str:
    """rim / paint / mid (for 2pt), or '3' for threes."""
    if act.get("actionType") == "3pt":
        return "3"
    d = act.get("shotDistance")
    quals = act.get("qualifiers") or []
    if d is not None:
        try:
            d = float(d)
            return "rim" if d <= 4 else ("paint" if d <= 8 else "mid")
        except Exception:
            pass
    if "pointsinthepaint" in quals:
        return "paint"
    return "mid"


def parse_game(pbp: dict, box: dict) -> dict:
    meta = load_meta(box)
    hid, aid = meta["home_id"], meta["away_id"]
    actions = pbp.get("game", {}).get("actions", [])
    tg = {hid: _blank_team(), aid: _blank_team()}
    on = {hid: set(meta["starters"].get(hid, set())), aid: set(meta["starters"].get(aid, set()))}

    stints = []
    cur = {"gsec_start": 0.0, "period": 1, "h_pts": 0, "a_pts": 0,
           "ev": {hid: dict(fga=0, fta=0, oreb=0, tov=0), aid: dict(fga=0, fta=0, oreb=0, tov=0)},
           "h5": tuple(sorted(on[hid])), "a5": tuple(sorted(on[aid]))}
    sh = sa = 0  # carried cumulative score
    last_gsec = 0.0

    def close_stint(gsec):
        cur["gsec_end"] = gsec
        cur["dur"] = max(0.0, gsec - cur["gsec_start"])
        if cur["dur"] > 0 or cur["h_pts"] or cur["a_pts"]:
            stints.append(dict(cur))

    for act in actions:
        p = int(act.get("period") or cur["period"])
        rem = parse_clock(act.get("clock"))
        gsec = game_sec(p, rem) if act.get("clock") else last_gsec
        last_gsec = gsec
        cur["period"] = p
        at = act.get("actionType")
        tid = act.get("teamId") or 0
        tid = int(tid) if tid else 0

        # score deltas (robust points attribution)
        new_h = act.get("scoreHome"); new_a = act.get("scoreAway")
        if new_h not in (None, ""):
            try:
                nh, na = int(new_h), int(new_a)
                dh, da = nh - sh, na - sa
                if dh:
                    tg[hid]["pts"] += dh; cur["h_pts"] += dh
                    q = tg[hid]["q_pts"]; q[p] = q.get(p, 0) + dh
                    if p >= 4 and rem <= 300 and abs(nh - na) <= 5:
                        tg[hid]["clutch_pts"] += dh
                if da:
                    tg[aid]["pts"] += da; cur["a_pts"] += da
                    q = tg[aid]["q_pts"]; q[p] = q.get(p, 0) + da
                    if p >= 4 and rem <= 300 and abs(nh - na) <= 5:
                        tg[aid]["clutch_pts"] += da
                sh, sa = nh, na
            except Exception:
                pass

        # box-style counting for the acting team
        if tid in tg:
            T = tg[tid]
            if at in ("2pt", "3pt"):
                made = act.get("shotResult") == "Made"
                T["fga"] += 1; cur["ev"][tid]["fga"] += 1
                if at == "3pt":
                    T["fg3a"] += 1
                    if made:
                        T["fg3m"] += 1; T["fgm"] += 1
                else:
                    if made:
                        T["fgm"] += 1
                z = _shot_zone(act)
                key = {"rim": "rim", "paint": "paint", "mid": "mid", "3": None}[z]
                if key:
                    T[f"{key}_fga"] += 1
                    if made:
                        T[f"{key}_fgm"] += 1
                if made and int(act.get("assistPersonId") or 0) > 0:
                    T["ast"] += 1
            elif at == "freethrow":
                T["fta"] += 1; cur["ev"][tid]["fta"] += 1
                if act.get("shotResult") == "Made":
                    T["ftm"] += 1
            elif at == "rebound":
                st = (act.get("subType") or "").lower()
                if st == "offensive":
                    T["oreb"] += 1; cur["ev"][tid]["oreb"] += 1
                elif st == "defensive":
                    T["dreb"] += 1
            elif at == "turnover":
                T["tov"] += 1; cur["ev"][tid]["tov"] += 1

        # substitutions -> close joint stint and update on-court
        if at == "substitution":
            st = (act.get("subType") or "").lower()
            pid = int(act.get("personId") or 0)
            if pid and tid in on:
                if st == "out":
                    on[tid].discard(pid)
                elif st == "in":
                    on[tid].add(pid)
                else:
                    continue
                close_stint(gsec)
                cur = {"gsec_start": gsec, "period": p, "h_pts": 0, "a_pts": 0,
                       "ev": {hid: dict(fga=0, fta=0, oreb=0, tov=0), aid: dict(fga=0, fta=0, oreb=0, tov=0)},
                       "h5": tuple(sorted(on[hid])), "a5": tuple(sorted(on[aid]))}

    close_stint(last_gsec)

    # possessions per team (Dean Oliver) from full-game counts
    for tid in (hid, aid):
        T = tg[tid]
        T["poss"] = round(T["fga"] + 0.44 * T["fta"] - T["oreb"] + T["tov"], 1)
        T["tricode"] = meta["home"] if tid == hid else meta["away"]
        T["is_home"] = tid == hid
    meta["team_game"] = tg
    meta["stints"] = stints
    meta["home_pts"] = sh
    meta["away_pts"] = sa
    return meta


def stint_poss(ev: dict) -> float:
    return ev["fga"] + 0.44 * ev["fta"] - ev["oreb"] + ev["tov"]
