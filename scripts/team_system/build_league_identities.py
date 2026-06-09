"""LEAGUE-WIDE team identities (all 30 teams) from the full boxscore cache -- the substrate the
matchup-composition needs beyond NYK/SAS, and a layer of the always-learning pipeline.

Builds, from `data/nba/boxscore_0022500*.json` (full league) + the `season_games` spine:
  - `league_team_game.parquet`  (one row per team-game: four factors + scores + opponent stats)
  - `team_defense_league.parquet` (all 30: tov_force / ft_force / oreb_strength, opponent-adjusted,
     shrunk -- the same formulas validated on NYK/SAS, applied league-wide so the engine can run any matchup)

Every run re-reads the current boxscore cache, so as new games land (update.py) the identities sharpen.
Leak-free is the CALLER's job (walkforward_league.py rebuilds as-of); this is the full-season snapshot.

  python scripts/team_system/build_league_identities.py
"""
from __future__ import annotations
import glob, json, os
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
NBA = os.path.join(ROOT, "data", "nba")
K, K_FT = 10.0, 8.0


def _season_spine():
    spine = {}
    for fp in glob.glob(os.path.join(NBA, "season_games_*.json")):
        try:
            for r in json.load(open(fp, encoding="utf-8"))["rows"]:
                if "home_win" in r:
                    spine[r["game_id"]] = r
        except Exception:
            pass
    return spine


def build_team_game(spine):
    rows = []
    for f in glob.glob(os.path.join(NBA, "boxscore_*.json")):
        gid = os.path.basename(f)[9:-5]
        s = spine.get(gid)
        if s is None:
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if d.get("game_status") != "Final":
            continue
        ts = d.get("teams")
        if not ts or len(ts) != 2:
            continue
        a, b = ts
        for me, opp in ((a, b), (b, a)):
            poss = me["fga"] + 0.44 * me["fta"] - me["oreb"] + me["to"]
            opp_poss = opp["fga"] + 0.44 * opp["fta"] - opp["oreb"] + opp["to"]
            rows.append(dict(gid=gid, date=s["game_date"], team=me["team_abbreviation"], opp=opp["team_abbreviation"],
                             pts=me["pts"], opp_pts=opp["pts"], poss=poss, opp_poss=opp_poss,
                             tov=me["to"], opp_tov=opp["to"], fga=me["fga"], fta=me["fta"],
                             opp_fta=opp["fta"], opp_fga=opp["fga"], oreb=me["oreb"], dreb=me["dreb"],
                             opp_oreb=opp["oreb"], opp_dreb=opp["dreb"], win=int(me["pts"] > opp["pts"])))
    return pd.DataFrame(rows)


def build_defense(TG):
    base_tov = TG.opp_tov.sum() / TG.opp_poss.sum()
    league_ftr = TG.opp_fta.sum() / TG.opp_fga.sum()
    own_ftr = (TG.groupby("team").fta.sum() / TG.groupby("team").fga.sum()).to_dict()
    rows = []
    for t, g in TG.groupby("team"):
        n = len(g)
        tov_raw = (g.opp_tov.sum() / g.opp_poss.sum()) / base_tov
        oreb_raw = g.oreb.sum() / (g.oreb.sum() + g.opp_dreb.sum())
        exp_ftr = np.mean([own_ftr.get(o, league_ftr) for o in g.opp])
        ft_raw = (g.opp_fta.sum() / g.opp_fga.sum()) / exp_ftr
        w, wf = n / (n + K), n / (n + K_FT)
        rows.append(dict(team=t, n=n, tov_force=round(1 + w * (tov_raw - 1), 4), tov_force_raw=round(tov_raw, 4),
                         ft_force=round(1 + wf * (ft_raw - 1), 4), ft_force_raw=round(ft_raw, 4),
                         oreb_strength=round(oreb_raw, 4)))
    return pd.DataFrame(rows).sort_values("tov_force", ascending=False)


def main():
    spine = _season_spine()
    TG = build_team_game(spine)
    if not len(TG):
        print("no league boxscores found; skipping league-identity build"); return
    TG.to_parquet(os.path.join(TS, "league_team_game.parquet"), index=False)
    D = build_defense(TG)
    D.to_parquet(os.path.join(TS, "team_defense_league.parquet"), index=False)
    g = TG.groupby("team").apply(lambda s: pd.Series({
        "g": len(s), "ortg": 100 * s.pts.sum() / s.poss.sum(),
        "drtg": 100 * s.opp_pts.sum() / s.opp_poss.sum()}), include_groups=False)
    g["net"] = g.ortg - g.drtg
    print(f"LEAGUE IDENTITIES: {len(TG)} team-games / {TG.team.nunique()} teams / {TG.gid.nunique()} games "
          f"({TG.date.min()}->{TG.date.max()}); team_defense_league {len(D)} teams")
    print("  net leaders:", ", ".join(f"{t} {g.loc[t,'net']:+.1f}" for t in g.net.nlargest(4).index),
          "| cellar:", ", ".join(f"{t} {g.loc[t,'net']:+.1f}" for t in g.net.nsmallest(3).index))


if __name__ == "__main__":
    main()
