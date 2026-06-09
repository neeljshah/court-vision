"""NYK/SAS Team System — Stage 3: aggregate parsed PBP into the team system.

Reads every cached NYK/SAS game, parses it (pbp_parse.parse_game), and writes:
  data/cache/team_system/team_game.parquet  — per (game, team) four-factor row
  data/cache/team_system/lineups.parquet     — per (team, 5-man) REAL 2025-26 net ratings
  data/cache/team_system/player_min.parquet  — per (team, player) minutes/games (rotation)
  data/cache/team_system/summary.json        — rich per-team profile + NYK-vs-SAS H2H

Everything is current-season (the cache is 2025-26 reg+playoff), so "up to date" = rerun
fetch then this. Consumed by fold_team_system.py.

  python scripts/team_system/build_team_system.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbp_parse import parse_game, stint_poss  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
PBP_DIR, BOX_DIR = os.path.join(TS, "pbp"), os.path.join(TS, "box")
NYK, SAS = 1610612752, 1610612759
TEAM_IDS = {NYK: "NYK", SAS: "SAS"}
MIN_LINEUP_MIN = 12.0   # report a 5-man only above this season floor


def _name_map(box) -> dict:
    out = {}
    g = box["game"]
    for tm in (g["homeTeam"], g["awayTeam"]):
        for p in tm.get("players", []):
            out[int(p["personId"])] = p.get("name") or p.get("nameI") or str(p["personId"])
    return out


def main():
    games = json.load(open(os.path.join(TS, "nyk_sas_games.json")))
    rows, names = [], {}
    # stint accumulators per team: lineup5 -> dict, player -> minutes
    lu = {NYK: defaultdict(lambda: dict(pf=0.0, pa=0.0, op=0.0, dp=0.0, mn=0.0)),
          SAS: defaultdict(lambda: dict(pf=0.0, pa=0.0, op=0.0, dp=0.0, mn=0.0))}
    pmin = {NYK: defaultdict(lambda: [0.0, 0]), SAS: defaultdict(lambda: [0.0, 0])}

    for gmeta in games:
        gid = gmeta["gid"]
        pf, bf = os.path.join(PBP_DIR, f"{gid}.json"), os.path.join(BOX_DIR, f"{gid}.json")
        if not (os.path.exists(pf) and os.path.exists(bf)):
            continue
        try:
            box = json.load(open(bf)); g = parse_game(json.load(open(pf)), box)
        except Exception as e:
            print(f"  parse fail {gid}: {e}"); continue
        names.update(_name_map(box))
        hid, aid = g["home_id"], g["away_id"]
        for tid in (hid, aid):
            if tid not in TEAM_IDS:
                continue
            oid = aid if tid == hid else hid
            T, O = g["team_game"][tid], g["team_game"][oid]
            rows.append({
                "gid": gid, "date": gmeta["date"], "kind": gmeta["kind"], "team": TEAM_IDS[tid],
                "opp": g["away"] if tid == hid else g["home"], "is_home": tid == hid,
                "win": int((g["home_pts"] if tid == hid else g["away_pts"]) >
                           (g["away_pts"] if tid == hid else g["home_pts"])),
                "pts": T["pts"], "poss": T["poss"], "opp_pts": O["pts"], "opp_poss": O["poss"],
                "fga": T["fga"], "fgm": T["fgm"], "fg3a": T["fg3a"], "fg3m": T["fg3m"],
                "fta": T["fta"], "ftm": T["ftm"], "oreb": T["oreb"], "dreb": T["dreb"],
                "tov": T["tov"], "ast": T["ast"], "opp_dreb": O["dreb"], "opp_tov": O["tov"],
                "rim_fga": T["rim_fga"], "rim_fgm": T["rim_fgm"], "mid_fga": T["mid_fga"],
                "paint_fga": T["paint_fga"], "clutch_pts": T["clutch_pts"], "clutch_opp": O["clutch_pts"],
                "q1": T["q_pts"].get(1, 0), "q2": T["q_pts"].get(2, 0),
                "q3": T["q_pts"].get(3, 0), "q4": T["q_pts"].get(4, 0),
            })
            # stints for this team's lineups + player minutes
            for s in g["stints"]:
                five = s["h5"] if tid == hid else s["a5"]
                mins = s["dur"] / 60.0
                for pid in five:
                    pmin[tid][pid][0] += mins
                if len(five) != 5:
                    continue
                d = lu[tid][five]
                d["pf"] += (s["h_pts"] if tid == hid else s["a_pts"])
                d["pa"] += (s["a_pts"] if tid == hid else s["h_pts"])
                d["op"] += stint_poss(s["ev"][tid]); d["dp"] += stint_poss(s["ev"][oid])
                d["mn"] += mins
            for pid in set(p for s in g["stints"] for p in (s["h5"] if tid == hid else s["a5"])):
                pmin[tid][pid][1] += 1

    tg = pd.DataFrame(rows)
    tg.to_parquet(os.path.join(TS, "team_game.parquet"), index=False)

    # lineups parquet
    lrows = []
    for tid, d in lu.items():
        for five, v in d.items():
            if v["mn"] < MIN_LINEUP_MIN or v["op"] < 1 or v["dp"] < 1:
                continue
            ortg, drtg = 100 * v["pf"] / v["op"], 100 * v["pa"] / v["dp"]
            lrows.append({"team": TEAM_IDS[tid], "lineup": " | ".join(names.get(p, str(p)) for p in five),
                          "ids": ",".join(map(str, five)), "min": round(v["mn"], 1),
                          "off_rtg": round(ortg, 1), "def_rtg": round(drtg, 1),
                          "net": round(ortg - drtg, 1), "poss": round(v["op"] + v["dp"], 0)})
    lin = pd.DataFrame(lrows).sort_values(["team", "min"], ascending=[True, False])
    lin.to_parquet(os.path.join(TS, "lineups.parquet"), index=False)

    # player minutes
    prows = [{"team": TEAM_IDS[tid], "player": names.get(pid, str(pid)), "pid": pid,
              "min": round(v[0], 1), "g": v[1], "mpg": round(v[0] / v[1], 1) if v[1] else 0}
             for tid, d in pmin.items() for pid, v in d.items() if v[1] >= 1]
    pm = pd.DataFrame(prows).sort_values(["team", "min"], ascending=[True, False])
    pm.to_parquet(os.path.join(TS, "player_min.parquet"), index=False)

    summary = {"as_of": tg["date"].max(), "teams": {}, "h2h": _h2h(tg, lin, pm, names)}
    for t in ("NYK", "SAS"):
        summary["teams"][t] = _team_summary(tg[tg.team == t], lin[lin.team == t], pm[pm.team == t])
    json.dump(summary, open(os.path.join(TS, "summary.json"), "w"), indent=1, default=str)

    print(f"DONE: {len(tg)} team-game rows | {len(lin)} lineup rows | {len(pm)} player rows")
    for t in ("NYK", "SAS"):
        s = summary["teams"][t]
        print(f"  {t}: {s['record']} | net {s['net_rtg']:+.1f} (off {s['off_rtg']} / def {s['def_rtg']}) "
              f"pace {s['pace']} | last10 {s['last10_record']} net {s['last10_net']:+.1f}")
    h = summary["h2h"]
    print(f"  H2H NYK-SAS: {h['n_games']} games, series-so-far {h['nyk_wins']}-{h['sas_wins']} (NYK-SAS)")


def _ff(df):
    s = df.sum(numeric_only=True)
    poss, op = max(s["poss"], 1), max(s["opp_poss"], 1)
    return {
        "off_rtg": round(100 * s["pts"] / poss, 1), "def_rtg": round(100 * s["opp_pts"] / op, 1),
        "pace": round((s["poss"] + s["opp_poss"]) / (2 * len(df)), 1) if len(df) else 0,
        "efg": round((s["fgm"] + 0.5 * s["fg3m"]) / max(s["fga"], 1), 3),
        "tov_pct": round(s["tov"] / poss, 3), "oreb_pct": round(s["oreb"] / max(s["oreb"] + s["opp_dreb"], 1), 3),
        "ftr": round(s["fta"] / max(s["fga"], 1), 3), "fg3a_rate": round(s["fg3a"] / max(s["fga"], 1), 3),
        "tov_forced_pct": round(s["opp_tov"] / op, 3),
    }


def _team_summary(df, lin, pm):
    df = df.sort_values("date")
    ff = _ff(df)
    l10 = df.tail(10)
    out = {"n_games": len(df), "record": f"{int(df.win.sum())}-{int((1 - df.win).sum())}",
           "net_rtg": round(ff["off_rtg"] - ff["def_rtg"], 1), **ff,
           "last10_record": f"{int(l10.win.sum())}-{int((1 - l10.win).sum())}",
           "last10_net": round(_ff(l10)["off_rtg"] - _ff(l10)["def_rtg"], 1),
           "q_for": [round(df[f"q{i}"].mean(), 1) for i in range(1, 5)],
           "clutch": f"{int(df[df.clutch_pts!=0].pipe(lambda x: (x.clutch_pts>x.clutch_opp).sum()))} clutch-game scoring edges of {int((df.clutch_pts!=0).sum())}",
           "top_lineups": lin.head(6).to_dict("records"),
           "rotation": pm.head(10)[["player", "mpg", "g"]].to_dict("records")}
    po = df[df.kind == "playoff"]
    if len(po):
        pff = _ff(po)
        out["playoff"] = {"record": f"{int(po.win.sum())}-{int((1 - po.win).sum())}",
                          "net_rtg": round(pff["off_rtg"] - pff["def_rtg"], 1), **pff}
    return out


def _h2h(tg, lin, pm, names):
    h = tg[((tg.team == "NYK") & (tg.opp == "SAS")) | ((tg.team == "SAS") & (tg.opp == "NYK"))]
    nyk = h[h.team == "NYK"].sort_values("date")
    games = [{"date": r.date, "kind": r.kind, "site": "vs" if r.is_home else "@",
              "nyk": int(r.pts), "sas": int(r.opp_pts), "nyk_win": int(r.win)} for r in nyk.itertuples()]
    fin = [gm for gm in games if gm["kind"] == "playoff"]
    return {"n_games": len(games), "nyk_wins": int(nyk.win.sum()), "sas_wins": int((1 - nyk.win).sum()),
            "finals_games": fin, "finals_series": f"{sum(g['nyk_win'] for g in fin)}-{sum(1-g['nyk_win'] for g in fin)}",
            "games": games,
            "nyk_ff_vs_sas": _ff(h[h.team == "NYK"]), "sas_ff_vs_nyk": _ff(h[h.team == "SAS"])}


if __name__ == "__main__":
    main()
