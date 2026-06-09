"""build_wcf_series_intel.py — build in-series context features for WCF G5.

Pulls traditional + advanced + matchup boxscores for the 4 played WCF games
(0042500311..14), aggregates per-player series averages, computes team-level
series aggregates (pace, off_rtg, def_rtg, eFG%, TOV%, OREB%), and writes
defensive matchup pairs if the matchups endpoint is reachable.

Outputs:
  data/nba/boxscore_<gid>.json       (traditional, if missing)
  data/nba/boxscore_adv_<gid>.json   (advanced, if missing)
  data/nba/boxscore_matchups_<gid>.json (matchups, if missing)
  data/cache/intel_2026-05-26/wcf_player_series_avg.csv
  data/cache/intel_2026-05-26/wcf_team_series_agg.json
  data/cache/intel_2026-05-26/wcf_defensive_matchups.csv
"""
from __future__ import annotations

import json
import os
import sys
import time
import csv
from collections import defaultdict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

NBA_DIR = os.path.join(PROJECT_DIR, "data", "nba")
INTEL_DIR = os.path.join(PROJECT_DIR, "data", "cache", "intel_2026-05-26")
os.makedirs(NBA_DIR, exist_ok=True)
os.makedirs(INTEL_DIR, exist_ok=True)

GAME_IDS = ["0042500311", "0042500312", "0042500313", "0042500314"]
GAME_DATES = {
    "0042500311": "2026-05-18",
    "0042500312": "2026-05-20",
    "0042500313": "2026-05-22",
    "0042500314": "2026-05-24",
}


def fetch_traditional(game_id: str) -> dict:
    out_path = os.path.join(NBA_DIR, f"boxscore_{game_id}.json")
    if os.path.exists(out_path):
        with open(out_path) as f:
            return json.load(f)
    from nba_api.stats.endpoints import boxscoretraditionalv2
    print(f"  fetching traditional {game_id} ...")
    bs = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id, timeout=30)
    frames = bs.get_data_frames()
    payload = {
        "game_id": game_id,
        "game_status": 3,
        "players": [
            {k.lower(): v for k, v in row.items()}
            for row in frames[0].to_dict("records")
        ],
        "teams": [
            {k.lower(): v for k, v in row.items()}
            for row in frames[1].to_dict("records")
        ] if len(frames) > 1 else [],
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, default=str)
    time.sleep(0.7)
    return payload


def fetch_advanced(game_id: str) -> dict:
    out_path = os.path.join(NBA_DIR, f"boxscore_adv_{game_id}.json")
    if os.path.exists(out_path):
        with open(out_path) as f:
            return json.load(f)
    try:
        from nba_api.stats.endpoints import boxscoreadvancedv3
        print(f"  fetching advanced {game_id} ...")
        bs = boxscoreadvancedv3.BoxScoreAdvancedV3(game_id=game_id, timeout=30)
        frames = bs.get_data_frames()
        # v3 returns nested team structure - both player & team frames
        player_rows = []
        team_rows = []
        # frames[0] = players (with teamTricode etc)
        try:
            player_rows = [
                {k.lower(): v for k, v in row.items()}
                for row in frames[0].to_dict("records")
            ]
        except Exception:
            pass
        try:
            team_rows = [
                {k.lower(): v for k, v in row.items()}
                for row in frames[1].to_dict("records")
            ]
        except Exception:
            pass
        payload = {"game_id": game_id, "players": player_rows, "teams": team_rows}
        with open(out_path, "w") as f:
            json.dump(payload, f, default=str)
        time.sleep(0.7)
        return payload
    except Exception as e:
        print(f"  [warn] advanced {game_id}: {e}")
        return {"game_id": game_id, "players": [], "teams": []}


def fetch_matchups(game_id: str) -> dict:
    out_path = os.path.join(NBA_DIR, f"boxscore_matchups_{game_id}.json")
    if os.path.exists(out_path):
        with open(out_path) as f:
            return json.load(f)
    try:
        from nba_api.stats.endpoints import boxscorematchupsv3
        print(f"  fetching matchups {game_id} ...")
        bs = boxscorematchupsv3.BoxScoreMatchupsV3(game_id=game_id, timeout=30)
        frames = bs.get_data_frames()
        rows = []
        for fr in frames:
            try:
                rows.extend([
                    {k.lower(): v for k, v in row.items()}
                    for row in fr.to_dict("records")
                ])
            except Exception:
                pass
        payload = {"game_id": game_id, "matchups": rows}
        with open(out_path, "w") as f:
            json.dump(payload, f, default=str)
        time.sleep(0.7)
        return payload
    except Exception as e:
        print(f"  [warn] matchups {game_id}: {e}")
        return {"game_id": game_id, "matchups": []}


def parse_min_str(min_val) -> float:
    """Box score 'min' field is sometimes 'MM:SS' string, sometimes float, sometimes None."""
    if min_val is None or min_val == "":
        return 0.0
    if isinstance(min_val, (int, float)):
        return float(min_val)
    s = str(min_val)
    if ":" in s:
        try:
            mm, ss = s.split(":")
            return float(mm) + float(ss) / 60.0
        except Exception:
            return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def num(x, default=0.0) -> float:
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def main() -> None:
    print("Fetching boxscores for WCF G1-G4 ...")
    trad = {}
    adv = {}
    matchups = {}
    for gid in GAME_IDS:
        trad[gid] = fetch_traditional(gid)
        adv[gid] = fetch_advanced(gid)
        matchups[gid] = fetch_matchups(gid)

    # ------------------------------------------------------------------
    # Per-player series averages
    # ------------------------------------------------------------------
    # key = (player_id, team_abbr) -> list of per-game stat dicts
    player_games = defaultdict(list)

    # advanced lookup: (game_id, player_id) -> adv player row
    adv_lookup: dict = {}
    for gid in GAME_IDS:
        for p in adv[gid].get("players", []):
            pid = p.get("personid") or p.get("player_id") or p.get("playerid")
            if pid is None:
                continue
            adv_lookup[(gid, int(pid))] = p

    for gid in GAME_IDS:
        for p in trad[gid].get("players", []):
            pid = p.get("player_id")
            team = p.get("team_abbreviation") or p.get("team_tricode")
            if pid is None:
                continue
            mins = parse_min_str(p.get("min"))
            fga = num(p.get("fga"))
            fgm = num(p.get("fgm"))
            fg3a = num(p.get("fg3a"))
            fg3m = num(p.get("fg3m"))
            fta = num(p.get("fta"))
            ftm = num(p.get("ftm"))
            row = {
                "game_id": gid,
                "min": mins,
                "pts": num(p.get("pts")),
                "reb": num(p.get("reb")),
                "oreb": num(p.get("oreb")),
                "dreb": num(p.get("dreb")),
                "ast": num(p.get("ast")),
                "stl": num(p.get("stl")),
                "blk": num(p.get("blk")),
                # traditionalv2 uses 'to' for turnovers
                "tov": num(p.get("tov", p.get("to"))),
                "fgm": fgm, "fga": fga,
                "fg3m": fg3m, "fg3a": fg3a,
                "ftm": ftm, "fta": fta,
                "plus_minus": num(p.get("plus_minus")),
            }
            # attach advanced if available
            adv_p = adv_lookup.get((gid, int(pid)))
            if adv_p:
                # v3 returns 0-1 scale; multiply to percent
                row["usg_pct"] = num(adv_p.get("usagepercentage", adv_p.get("usg_pct"))) * 100
                row["ts_pct_adv"] = num(adv_p.get("trueshootingpercentage", adv_p.get("ts_pct"))) * 100
                row["off_rtg"] = num(adv_p.get("offensiverating", adv_p.get("off_rating")))
                row["def_rtg"] = num(adv_p.get("defensiverating", adv_p.get("def_rating")))
                row["pie"] = num(adv_p.get("pie")) * 100
            player_games[(int(pid), team, p.get("player_name") or p.get("first_name", "") + " " + p.get("family_name", ""))].append(row)

    # Aggregate
    player_rows_out = []
    for (pid, team, name), games in player_games.items():
        gp = len(games)
        if gp == 0:
            continue
        agg = {
            "player_id": pid,
            "player_name": name.strip(),
            "team": team,
            "gp": gp,
            "min_pg": sum(g["min"] for g in games) / gp,
            "pts_pg": sum(g["pts"] for g in games) / gp,
            "reb_pg": sum(g["reb"] for g in games) / gp,
            "ast_pg": sum(g["ast"] for g in games) / gp,
            "stl_pg": sum(g["stl"] for g in games) / gp,
            "blk_pg": sum(g["blk"] for g in games) / gp,
            "tov_pg": sum(g["tov"] for g in games) / gp,
            "fg3m_pg": sum(g["fg3m"] for g in games) / gp,
            "fga_pg": sum(g["fga"] for g in games) / gp,
            "fg3a_pg": sum(g["fg3a"] for g in games) / gp,
            "fta_pg": sum(g["fta"] for g in games) / gp,
            "plus_minus_pg": sum(g["plus_minus"] for g in games) / gp,
        }
        # TS%: pts / (2 * (FGA + 0.44*FTA))
        total_pts = sum(g["pts"] for g in games)
        ts_denom = 2 * (sum(g["fga"] for g in games) + 0.44 * sum(g["fta"] for g in games))
        agg["ts_pct"] = total_pts / ts_denom if ts_denom > 0 else 0.0
        # eFG%
        total_fgm = sum(g["fgm"] for g in games)
        total_fg3m = sum(g["fg3m"] for g in games)
        total_fga = sum(g["fga"] for g in games)
        agg["efg_pct"] = (total_fgm + 0.5 * total_fg3m) / total_fga if total_fga > 0 else 0.0
        # advanced averages if present
        adv_games = [g for g in games if "usg_pct" in g]
        if adv_games:
            agg["usg_pct_pg"] = sum(g["usg_pct"] for g in adv_games) / len(adv_games)
            agg["off_rtg_pg"] = sum(g["off_rtg"] for g in adv_games) / len(adv_games)
            agg["def_rtg_pg"] = sum(g["def_rtg"] for g in adv_games) / len(adv_games)
        player_rows_out.append(agg)

    player_rows_out.sort(key=lambda r: (-r["pts_pg"], r["team"]))

    out_csv = os.path.join(INTEL_DIR, "wcf_player_series_avg.csv")
    if player_rows_out:
        fieldnames = list(player_rows_out[0].keys())
        # ensure all keys covered
        all_keys = set()
        for r in player_rows_out:
            all_keys.update(r.keys())
        # union, keeping the first row order then appending extras
        for k in all_keys:
            if k not in fieldnames:
                fieldnames.append(k)
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in player_rows_out:
                w.writerow(r)
        print(f"  wrote {len(player_rows_out)} player rows -> {out_csv}")
    else:
        print("  [warn] no player rows to write")

    # ------------------------------------------------------------------
    # Team series aggregates
    # ------------------------------------------------------------------
    # Use trad team rows + line-score points + advanced team rows
    # Pace: poss/48 ; off_rtg: pts per 100 poss ; def_rtg = opp_pts per 100 poss
    # If advanced has pace/off_rtg directly, prefer those.
    team_per_game = defaultdict(list)  # team -> list of per-game dicts
    for gid in GAME_IDS:
        trad_teams = {t.get("team_abbreviation"): t for t in trad[gid].get("teams", [])}
        adv_teams_raw = adv[gid].get("teams", [])
        adv_teams = {}
        for t in adv_teams_raw:
            abbr = t.get("teamtricode") or t.get("team_abbreviation")
            if abbr:
                adv_teams[abbr] = t
        team_pts = {}
        for abbr, t in trad_teams.items():
            team_pts[abbr] = num(t.get("pts"))
        for abbr, t in trad_teams.items():
            opp_pts = sum(v for k, v in team_pts.items() if k != abbr)
            opp_abbr = [k for k in team_pts if k != abbr][0] if len(team_pts) > 1 else None
            adv_t = adv_teams.get(abbr, {})
            row = {
                "game_id": gid,
                "date": GAME_DATES[gid],
                "opp": opp_abbr,
                "pts": team_pts[abbr],
                "opp_pts": opp_pts,
                "fgm": num(t.get("fgm")), "fga": num(t.get("fga")),
                "fg3m": num(t.get("fg3m")), "fg3a": num(t.get("fg3a")),
                "ftm": num(t.get("ftm")), "fta": num(t.get("fta")),
                "oreb": num(t.get("oreb")), "dreb": num(t.get("dreb")),
                "reb": num(t.get("reb")),
                "ast": num(t.get("ast")), "stl": num(t.get("stl")),
                "blk": num(t.get("blk")), "tov": num(t.get("tov", t.get("to"))),
                "win": 1 if team_pts[abbr] > opp_pts else 0,
            }
            # Estimate possessions: 0.5*((FGA + 0.44*FTA - 1.07*(OREB/(OREB+opp_DREB))*(FGA-FGM) + TOV) + opp_same)
            # Simplified: poss ~= FGA - OREB + TOV + 0.44*FTA
            # Use advanced pace if present
            pace_adv = num(adv_t.get("pace"))
            off_rtg_adv = num(adv_t.get("offensiverating", adv_t.get("off_rating")))
            def_rtg_adv = num(adv_t.get("defensiverating", adv_t.get("def_rating")))
            # v3 returns 0-1 (eFG/OREB%) but turnoverratio already on per-100 scale
            efg_adv = num(adv_t.get("effectivefieldgoalpercentage", adv_t.get("efg_pct")))
            tov_pct_adv = num(adv_t.get("turnoverratio", adv_t.get("estimatedteamturnoverpercentage", adv_t.get("tm_tov_pct"))))
            oreb_pct_adv = num(adv_t.get("offensivereboundpercentage", adv_t.get("oreb_pct"))) * 100
            # Fallback simple estimate
            poss_est = row["fga"] - row["oreb"] + row["tov"] + 0.44 * row["fta"]
            row["poss_est"] = poss_est
            # game length: 240 mins normally, 290 for G1 (OT)
            # OT minutes from line: G1 had 2 OTs
            game_mins = 240
            if gid == "0042500311":
                game_mins = 240 + 2 * 25  # 2 OTs * 5 mins * 5 players ... actually pace is per 48
                # for pace we want poss per 48; G1 went 58 min (2 OT)
                pace_mult = 48.0 / 58.0
            else:
                pace_mult = 1.0
            row["pace_est"] = poss_est * pace_mult if poss_est > 0 else 0.0
            row["pace"] = pace_adv if pace_adv > 0 else row["pace_est"]
            row["off_rtg"] = off_rtg_adv if off_rtg_adv > 0 else (row["pts"] / poss_est * 100 if poss_est > 0 else 0)
            row["def_rtg"] = def_rtg_adv if def_rtg_adv > 0 else (opp_pts / poss_est * 100 if poss_est > 0 else 0)
            row["efg_pct"] = efg_adv if efg_adv > 0 else (
                (row["fgm"] + 0.5 * row["fg3m"]) / row["fga"] if row["fga"] > 0 else 0
            )
            row["tov_pct"] = tov_pct_adv if tov_pct_adv > 0 else (
                100 * row["tov"] / poss_est if poss_est > 0 else 0
            )
            row["oreb_pct"] = oreb_pct_adv if oreb_pct_adv > 0 else (
                100 * row["oreb"] / (row["oreb"] + (sum(v for k, v in {a: num(tt.get('dreb')) for a, tt in trad_teams.items()}.items() if k != abbr) or 1))
            )
            team_per_game[abbr].append(row)

    team_agg = {}
    for team, games in team_per_game.items():
        n = len(games)
        wins = sum(g["win"] for g in games)
        agg = {
            "team": team,
            "games_played": n,
            "wins": wins,
            "losses": n - wins,
            "pts_pg": sum(g["pts"] for g in games) / n,
            "opp_pts_pg": sum(g["opp_pts"] for g in games) / n,
            "pace_avg": sum(g["pace"] for g in games) / n,
            "off_rtg_avg": sum(g["off_rtg"] for g in games) / n,
            "def_rtg_avg": sum(g["def_rtg"] for g in games) / n,
            "efg_pct_avg": sum(g["efg_pct"] for g in games) / n,
            "tov_pct_avg": sum(g["tov_pct"] for g in games) / n,
            "oreb_pct_avg": sum(g["oreb_pct"] for g in games) / n,
            "ast_pg": sum(g["ast"] for g in games) / n,
            "stl_pg": sum(g["stl"] for g in games) / n,
            "blk_pg": sum(g["blk"] for g in games) / n,
            "per_game": games,
        }
        team_agg[team] = agg

    # Series-state features
    series_state = {
        "series_games_played": 4,
        "series_status": "swing_2_2",
        "okc_wins": team_agg.get("OKC", {}).get("wins", 0),
        "sas_wins": team_agg.get("SAS", {}).get("wins", 0),
        "series_pace_avg": (
            (team_agg.get("OKC", {}).get("pace_avg", 0) + team_agg.get("SAS", {}).get("pace_avg", 0)) / 2
        ),
        "g4_margin_for_sas": (
            team_agg.get("SAS", {}).get("per_game", [{}])[-1].get("pts", 0)
            - team_agg.get("SAS", {}).get("per_game", [{}])[-1].get("opp_pts", 0)
        ) if team_agg.get("SAS") else 0,
        "away_team_blowout_last": 1 if team_agg.get("SAS") and (
            team_agg["SAS"]["per_game"][-1]["pts"] - team_agg["SAS"]["per_game"][-1]["opp_pts"] >= 15
        ) else 0,
    }

    out_team_json = os.path.join(INTEL_DIR, "wcf_team_series_agg.json")
    with open(out_team_json, "w") as f:
        json.dump({"teams": team_agg, "series_state": series_state}, f, indent=2, default=str)
    print(f"  wrote team aggregates -> {out_team_json}")

    # ------------------------------------------------------------------
    # Defensive matchups
    # ------------------------------------------------------------------
    matchup_pairs = defaultdict(lambda: {
        "matchup_min": 0.0,
        "partial_poss": 0.0,
        "pts_allowed": 0.0,
        "fgm_allowed": 0.0,
        "fga_allowed": 0.0,
        "fg3m_allowed": 0.0,
        "fg3a_allowed": 0.0,
        "ast_allowed": 0.0,
        "tov_forced": 0.0,
        "blocks": 0.0,
        "games": 0,
    })
    matchups_found = 0
    for gid in GAME_IDS:
        rows = matchups[gid].get("matchups", [])
        if not rows:
            continue
        matchups_found += 1
        for r in rows:
            off_id = r.get("personidoff") or r.get("personid_off") or r.get("off_player_id")
            def_id = r.get("personiddef") or r.get("personid_def") or r.get("def_player_id")
            off_name = r.get("offensiveplayername") or r.get("firstnameoff", "") + " " + r.get("familynameoff", "")
            def_name = r.get("defensiveplayername") or r.get("firstnamedef", "") + " " + r.get("familynamedef", "")
            if not off_id or not def_id:
                continue
            key = (int(off_id), int(def_id), off_name.strip(), def_name.strip())
            d = matchup_pairs[key]
            # Field names vary by endpoint
            mm = r.get("matchupminutes") or r.get("matchup_min") or r.get("matchup_minutes")
            d["matchup_min"] += parse_min_str(mm)
            d["partial_poss"] += num(r.get("partialpossessions") or r.get("partial_poss"))
            d["pts_allowed"] += num(r.get("playerpoints") or r.get("matchup_player_points") or r.get("points"))
            d["fgm_allowed"] += num(r.get("matchupfieldgoalsmade") or r.get("matchup_fgm"))
            d["fga_allowed"] += num(r.get("matchupfieldgoalsattempted") or r.get("matchup_fga"))
            d["fg3m_allowed"] += num(r.get("matchupthreepointersmade") or r.get("matchup_3pm"))
            d["fg3a_allowed"] += num(r.get("matchupthreepointersattempted") or r.get("matchup_3pa"))
            d["ast_allowed"] += num(r.get("matchupassists") or r.get("matchup_assists"))
            d["tov_forced"] += num(r.get("matchupturnovers") or r.get("matchup_turnovers"))
            d["blocks"] += num(r.get("matchupblocks") or r.get("matchup_blocks"))
            d["games"] += 1

    out_matchup_csv = os.path.join(INTEL_DIR, "wcf_defensive_matchups.csv")
    if matchup_pairs:
        # write top 60 by matchup minutes
        rows_out = []
        for (oid, did, oname, dname), d in matchup_pairs.items():
            row = {
                "off_player_id": oid,
                "off_player_name": oname,
                "def_player_id": did,
                "def_player_name": dname,
                "matchup_min": round(d["matchup_min"], 2),
                "partial_poss": round(d["partial_poss"], 2),
                "pts_allowed": round(d["pts_allowed"], 2),
                "fgm_allowed": d["fgm_allowed"],
                "fga_allowed": d["fga_allowed"],
                "fg_pct_allowed": (d["fgm_allowed"] / d["fga_allowed"]) if d["fga_allowed"] > 0 else 0.0,
                "fg3m_allowed": d["fg3m_allowed"],
                "fg3a_allowed": d["fg3a_allowed"],
                "fg3_pct_allowed": (d["fg3m_allowed"] / d["fg3a_allowed"]) if d["fg3a_allowed"] > 0 else 0.0,
                "ast_allowed": d["ast_allowed"],
                "tov_forced": d["tov_forced"],
                "blocks": d["blocks"],
                "games_matched": d["games"],
            }
            rows_out.append(row)
        rows_out.sort(key=lambda r: -r["matchup_min"])
        fieldnames = list(rows_out[0].keys())
        with open(out_matchup_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows_out:
                w.writerow(r)
        print(f"  wrote {len(rows_out)} matchup pairs -> {out_matchup_csv} (from {matchups_found}/4 games)")
    else:
        # write empty file with note
        with open(out_matchup_csv, "w", newline="", encoding="utf-8") as f:
            f.write("# matchups endpoint returned no data for any of G1-G4\n")
        print(f"  [warn] no matchups data; wrote stub -> {out_matchup_csv}")

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    print("\n=== SERIES PACE / EFFICIENCY ===")
    for team in ("OKC", "SAS"):
        a = team_agg.get(team)
        if not a:
            continue
        print(f"{team}: pace_avg={a['pace_avg']:.1f}  off_rtg={a['off_rtg_avg']:.1f}  def_rtg={a['def_rtg_avg']:.1f}  eFG%={a['efg_pct_avg']:.3f}  TOV%={a['tov_pct_avg']:.1f}  OREB%={a['oreb_pct_avg']:.1f}")
        for g in a["per_game"]:
            print(f"  G{GAME_IDS.index(g['game_id'])+1} ({g['date']}): pts={g['pts']:.0f} opp={g['opp_pts']:.0f} pace={g['pace']:.1f} off_rtg={g['off_rtg']:.1f} def_rtg={g['def_rtg']:.1f} eFG={g['efg_pct']:.3f}")

    print("\n=== KEY PLAYER SERIES AVERAGES ===")
    stars = ["Shai Gilgeous-Alexander", "Jalen Williams", "Chet Holmgren", "Isaiah Hartenstein",
             "Victor Wembanyama", "De'Aaron Fox", "Stephon Castle", "Devin Vassell"]
    for r in player_rows_out:
        nm = r["player_name"]
        for star in stars:
            if star.lower() in nm.lower() or nm.lower() in star.lower():
                line = f"{nm} ({r['team']}): MIN={r['min_pg']:.1f} PTS={r['pts_pg']:.1f} REB={r['reb_pg']:.1f} AST={r['ast_pg']:.1f} STL={r['stl_pg']:.1f} BLK={r['blk_pg']:.1f} TOV={r['tov_pg']:.1f} FG3M={r['fg3m_pg']:.1f} TS%={r['ts_pct']:.3f}"
                if "usg_pct_pg" in r:
                    line += f" USG%={r['usg_pct_pg']:.1f} off_rtg={r['off_rtg_pg']:.1f} def_rtg={r['def_rtg_pg']:.1f}"
                print("  " + line)
                break


if __name__ == "__main__":
    main()
