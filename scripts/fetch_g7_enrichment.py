"""fetch_g7_enrichment.py — deep NBA-API tracking/hustle/clutch/defense pull
for WCF Game 7 (SAS @ OKC, 2026-05-30, game_id 0042500317).

Pulls 2025-26 playoff (and clutch reg-season) tracking data for both teams +
key players, MINES it for betting signals, and writes
data/cache/intel_game7/nba_enrich_g7.json.

Endpoints used (all verified working from RunPod datacenter IP):
  - leaguedashptstats   (Drives, Defense, CatchShoot, PullUpShot, Possessions)
  - playerdashptshots   (catch-shoot vs pull-up, defended-distance, rim)
  - leaguehustlestatsplayer (deflections, contested, screen-asts, box-outs)
  - leaguedashplayerclutch  (clutch scoring last-5-min <=5pts)
  - leaguedashptdefend  (Overall = defended rim FG%, 3 Pointers)
  - leaguedashlineups   (5-man on/off, Advanced)

Read-only. Writes ONLY the two allowed new files (+ optional raw cache).
"""
from __future__ import annotations

import json
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

SEASON = "2025-26"
OKC, SAS = 1610612760, 1610612759
OUT_DIR = os.path.join(PROJECT_DIR, "data", "cache", "intel_game7")
RAW_DIR = os.path.join(PROJECT_DIR, "data", "nba")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

KEY = {
    "Wemby": 1641705, "SGA": 1628983, "Holmgren": 1631096, "Castle": 1642264,
    "Fox": 1628368, "McCain": 1642272, "Harper": 1642844, "Caruso": 1627936,
    "Hartenstein": 1628392, "Dort": 1629652, "Wallace": 1641717,
}
PID2NAME = {v: k for k, v in KEY.items()}
OKC_PIDS = {1628983, 1631096, 1627936, 1628392, 1629652, 1641717}
SAS_PIDS = {1641705, 1642264, 1628368, 1642272, 1642844}

blockers = []


def safe(name, fn):
    t = time.time()
    try:
        out = fn()
        print(f"  OK {name} ({time.time()-t:.1f}s)")
        return out
    except Exception as e:
        msg = f"{name}: {str(e)[:160]}"
        print(f"  BLOCKER {msg}")
        blockers.append(msg)
        return None


def pctile(series, val):
    """percentile rank of val within series (0-100), higher=better."""
    s = series.dropna()
    if len(s) == 0 or val is None:
        return None
    return round(100.0 * (s < val).mean(), 1)


def num(x):
    try:
        return round(float(x), 3)
    except Exception:
        return None


def main():
    from nba_api.stats.endpoints import (
        leaguedashptstats, playerdashptshots, leaguehustlestatsplayer,
        leaguedashplayerclutch, leaguedashptdefend, leaguedashlineups,
    )

    enrich = {
        "meta": {
            "game_id": "0042500317", "game": "SAS @ OKC WCF G7",
            "date": "2026-05-30", "season": SEASON, "series": "3-3",
            "okc_out": ["Jalen Williams", "Ajay Mitchell", "Sorber"],
        },
        "endpoints_ok": [], "blockers": [],
        "tracking": {}, "shots": {}, "hustle": {}, "clutch": {},
        "defense": {}, "lineups": {}, "signals": [],
    }

    # ---------- 1. leaguedashptstats: Drives + Defense + Possessions ----------
    print("[1] leaguedashptstats (playoffs)")
    measures = {}
    for m in ["Drives", "Defense", "Possessions", "CatchShoot", "PullUpShot"]:
        df = safe(f"ptstats-{m}", lambda m=m: leaguedashptstats.LeagueDashPtStats(
            season=SEASON, season_type_all_star="Playoffs", pt_measure_type=m,
            player_or_team="Player", per_mode_simple="PerGame",
        ).get_data_frames()[0])
        if df is not None:
            measures[m] = df
            enrich["endpoints_ok"].append(f"leaguedashptstats/{m}")
        time.sleep(0.4)

    # Drives signal
    if "Drives" in measures:
        d = measures["Drives"]
        for pid, nm in PID2NAME.items():
            r = d[d.PLAYER_ID == pid]
            if len(r):
                r = r.iloc[0]
                enrich["tracking"].setdefault(nm, {})["drives"] = {
                    "drives_pg": num(r.DRIVES), "drive_fg_pct": num(r.DRIVE_FG_PCT),
                    "drive_pts_pg": num(r.DRIVE_PTS), "drive_pf_pg": num(r.DRIVE_PF),
                    "drive_pct_pctile": pctile(d.DRIVES, r.DRIVES),
                }

    # Defense (rim protection: DEF_RIM_FG_PCT, BLK)
    if "Defense" in measures:
        d = measures["Defense"]
        cols = list(d.columns)
        rim_col = next((c for c in cols if "RIM" in c and "PCT" in c), None)
        for pid, nm in PID2NAME.items():
            r = d[d.PLAYER_ID == pid]
            if len(r):
                r = r.iloc[0]
                rec = {"def_blk_pg": num(r.get("BLK"))}
                if rim_col:
                    rec["def_rim_fg_pct_allowed"] = num(r.get(rim_col))
                    rec["def_rim_pctile_lower_better"] = pctile(d[rim_col], r.get(rim_col))
                enrich["tracking"].setdefault(nm, {})["defense"] = rec

    # ---------- 2. playerdashptshots: shot quality by type/defense/dribble ----
    print("[2] playerdashptshots (per key scorer, playoffs)")
    scorers = {"Wemby": (SAS, 1641705), "SGA": (OKC, 1628983),
               "Castle": (SAS, 1642264), "Fox": (SAS, 1628368),
               "Holmgren": (OKC, 1631096), "McCain": (SAS, 1642272)}
    for nm, (tid, pid) in scorers.items():
        dfs = safe(f"ptshots-{nm}", lambda tid=tid, pid=pid:
                   playerdashptshots.PlayerDashPtShots(
                       team_id=tid, player_id=pid, season=SEASON,
                       season_type_all_star="Playoffs").get_data_frames())
        if dfs is None:
            continue
        if "playerdashptshots" not in enrich["endpoints_ok"]:
            enrich["endpoints_ok"].append("playerdashptshots")
        rec = {}
        # frame 1 = general shooting (Catch&Shoot / PullUps / <10ft)
        gs = dfs[1]
        for _, row in gs.iterrows():
            st = str(row.SHOT_TYPE).lower().replace(" ", "_").replace("&", "and")
            rec[st] = {"fga_pg": num(row.FGA), "fg_pct": num(row.FG_PCT),
                       "efg_pct": num(row.EFG_PCT), "freq": num(row.FGA_FREQUENCY)}
        # frame 4 = closest defender distance ranges
        cd = dfs[4]
        rec["by_def_distance"] = {}
        for _, row in cd.iterrows():
            rng = str(row.CLOSE_DEF_DIST_RANGE)
            rec["by_def_distance"][rng] = {
                "fga_pg": num(row.FGA), "fg_pct": num(row.FG_PCT),
                "freq": num(row.FGA_FREQUENCY)}
        enrich["shots"][nm] = rec

    # ---------- 3. hustle ----------
    print("[3] leaguehustlestatsplayer (playoffs)")
    h = safe("hustle", lambda: leaguehustlestatsplayer.LeagueHustleStatsPlayer(
        season=SEASON, season_type_all_star="Playoffs",
        per_mode_time="PerGame").get_data_frames()[0])
    if h is not None:
        enrich["endpoints_ok"].append("leaguehustlestatsplayer")
        for pid, nm in PID2NAME.items():
            r = h[h.PLAYER_ID == pid]
            if len(r):
                r = r.iloc[0]
                enrich["hustle"][nm] = {
                    "deflections_pg": num(r.DEFLECTIONS),
                    "deflections_pctile": pctile(h.DEFLECTIONS, r.DEFLECTIONS),
                    "contested_shots_pg": num(r.CONTESTED_SHOTS),
                    "contested_3pt_pg": num(r.CONTESTED_SHOTS_3PT),
                    "screen_assists_pg": num(r.SCREEN_ASSISTS),
                    "screen_ast_pts_pg": num(r.SCREEN_AST_PTS),
                    "box_outs_pg": num(r.BOX_OUTS),
                    "charges_drawn_pg": num(r.CHARGES_DRAWN),
                    "loose_balls_pg": num(r.LOOSE_BALLS_RECOVERED),
                }

    # ---------- 4. clutch (reg season, robust sample) ----------
    print("[4] leaguedashplayerclutch (Last 5 Minutes, <=5 pts, reg season)")
    c = safe("clutch", lambda: leaguedashplayerclutch.LeagueDashPlayerClutch(
        season=SEASON, season_type_all_star="Regular Season",
        clutch_time="Last 5 Minutes", point_diff=5,
        per_mode_detailed="PerGame").get_data_frames()[0])
    if c is not None:
        enrich["endpoints_ok"].append("leaguedashplayerclutch")
        for pid, nm in PID2NAME.items():
            r = c[c.PLAYER_ID == pid]
            if len(r):
                r = r.iloc[0]
                enrich["clutch"][nm] = {
                    "gp": int(r.GP), "min_pg": num(r.MIN), "pts_pg": num(r.PTS),
                    "fg_pct": num(r.FG_PCT), "fg3_pct": num(r.FG3_PCT),
                    "ft_pct": num(r.FT_PCT), "plus_minus": num(r.PLUS_MINUS),
                    "usg_pct": num(r.get("USG_PCT")),
                }

    # ---------- 5. defended FG% (matchup defense) ----------
    print("[5] leaguedashptdefend (Overall=rim, 3 Pointers)")
    for cat, key in [("Overall", "rim_overall"), ("3 Pointers", "threes")]:
        df = safe(f"ptdefend-{key}", lambda cat=cat: leaguedashptdefend.LeagueDashPtDefend(
            season=SEASON, season_type_all_star="Playoffs",
            defense_category=cat, per_mode_simple="PerGame").get_data_frames()[0])
        if df is None:
            continue
        enrich["endpoints_ok"].append(f"leaguedashptdefend/{cat}")
        # Overall uses D_FGA/D_FG_PCT/NORMAL_FG_PCT/PCT_PLUSMINUS;
        # 3 Pointers uses FG3A/FG3_PCT/NS_FG3_PCT/PLUSMINUS.
        fga_c = "D_FGA" if "D_FGA" in df.columns else "FG3A"
        pct_c = "D_FG_PCT" if "D_FG_PCT" in df.columns else "FG3_PCT"
        norm_c = "NORMAL_FG_PCT" if "NORMAL_FG_PCT" in df.columns else "NS_FG3_PCT"
        pm_c = "PCT_PLUSMINUS" if "PCT_PLUSMINUS" in df.columns else "PLUSMINUS"
        for pid, nm in PID2NAME.items():
            r = df[df.CLOSE_DEF_PERSON_ID == pid]
            if len(r):
                r = r.iloc[0]
                enrich["defense"].setdefault(nm, {})[key] = {
                    "d_fga_pg": num(r[fga_c]), "d_fg_pct": num(r[pct_c]),
                    "normal_fg_pct": num(r[norm_c]),
                    "pct_plusminus": num(r[pm_c]),
                }

    # ---------- 6. lineups (5-man Advanced) ----------
    print("[6] leaguedashlineups (5-man Advanced, both teams)")
    for tid, tag in [(OKC, "OKC"), (SAS, "SAS")]:
        df = safe(f"lineups-{tag}", lambda tid=tid: leaguedashlineups.LeagueDashLineups(
            season=SEASON, season_type_all_star="Playoffs", team_id_nullable=tid,
            group_quantity=5, per_mode_detailed="PerGame",
            measure_type_detailed_defense="Advanced").get_data_frames()[0])
        if df is None:
            continue
        if "leaguedashlineups" not in enrich["endpoints_ok"]:
            enrich["endpoints_ok"].append("leaguedashlineups")
        df = df.sort_values("MIN", ascending=False).head(8)
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "lineup": r.GROUP_NAME, "min_pg": num(r.MIN), "gp": int(r.GP),
                "net_rating": num(r.NET_RATING), "off_rating": num(r.OFF_RATING),
                "def_rating": num(r.DEF_RATING), "pace": num(r.get("PACE")),
            })
        enrich["lineups"][tag] = rows

    # ================= MINE SIGNALS =================
    sigs = enrich["signals"]

    def get(path, *keys, default=None):
        cur = path
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    # SGA drives vs SAS rim/foul
    sga_dr = get(enrich["tracking"], "SGA", "drives")
    if sga_dr:
        sigs.append({
            "signal": "SGA drive volume + drive FT generation",
            "number": f"{sga_dr['drives_pg']} drives/g, {sga_dr['drive_fg_pct']} FG, "
                      f"{sga_dr['drive_pts_pg']} drive-pts/g (PO)",
            "read": "Confirms SGA PTS-over / FTA-over; G7 close => more drawn fouls late.",
        })

    # Wemby shot profile + defended distance
    wemby = enrich["shots"].get("Wemby", {})
    if wemby:
        cns = wemby.get("catch_and_shoot", {})
        pu = wemby.get("pull_ups", {})
        rim = wemby.get("less_than_10_ft", {})
        sigs.append({
            "signal": "Wemby shot mix: rim-reliant, cold jumper (PO)",
            "number": f"<10ft {rim.get('fg_pct')} FG on {rim.get('fga_pg')} FGA/g; "
                      f"C&S {cns.get('fg_pct')} / PullUp {pu.get('fg_pct')}",
            "read": "Wemby value is at rim; if OKC walls paint his jumper bails them out "
                    "-> lean Wemby PTS UNDER vs inflated lines, but rim attempts are sticky.",
        })

    # Wemby as rim defender (defense rec)
    wd = get(enrich["tracking"], "Wemby", "defense")
    if wd and wd.get("def_rim_fg_pct_allowed") is not None:
        sigs.append({
            "signal": "Wemby rim deterrence",
            "number": f"opp rim FG% allowed {wd['def_rim_fg_pct_allowed']} "
                      f"(pctile {wd.get('def_rim_pctile_lower_better')}), {wd.get('def_blk_pg')} BLK/g",
            "read": "Corroborates SAS rim-wall; pressures OKC non-SGA rim finishers "
                    "-> OKC role-player scoring UNDERs / fewer easy Holmgren rim looks.",
        })

    # Hartenstein leak vs Wemby (screen + defended distance)
    hart_h = enrich["hustle"].get("Hartenstein", {})
    if hart_h:
        sigs.append({
            "signal": "Hartenstein screen-assist hub (OKC half-court)",
            "number": f"{hart_h.get('screen_assists_pg')} screen-ast/g, "
                      f"{hart_h.get('screen_ast_pts_pg')} screen-ast-pts/g, "
                      f"{hart_h.get('box_outs_pg')} box-outs/g",
            "read": "Hartenstein generates OKC half-court offense via screens; "
                    "if Wemby drops he frees SGA pull-ups -> SGA 3PA/midrange volume.",
        })

    # Caruso / Dort deflections (defensive disruption)
    for d_nm in ("Caruso", "Dort", "Wallace"):
        dh = enrich["hustle"].get(d_nm, {})
        if dh and dh.get("deflections_pg") is not None:
            sigs.append({
                "signal": f"{d_nm} ball-pressure",
                "number": f"{dh['deflections_pg']} deflections/g "
                          f"(pctile {dh.get('deflections_pctile')}), "
                          f"{dh.get('contested_3pt_pg')} contested-3/g",
                "read": f"{d_nm} disrupts SAS guards -> SAS TOV-over / Castle-Fox-McCain "
                        "assist+scoring variance up.",
            })

    # Clutch profiles
    for nm in ("SGA", "Fox", "Castle", "Wemby", "McCain"):
        cl = enrich["clutch"].get(nm)
        if cl and cl["gp"] >= 5:
            sigs.append({
                "signal": f"{nm} clutch profile (reg-season last-5 <=5pts)",
                "number": f"{cl['pts_pg']} pts/g over {cl['gp']}g, FG {cl['fg_pct']}, "
                          f"3P {cl['fg3_pct']}, +/- {cl['plus_minus']}",
                "read": "G7 stays close -> clutch-min usage matters for last-5 prop spikes.",
            })

    # Defended FG% matchup edges
    for nm, rec in enrich["defense"].items():
        ov = rec.get("rim_overall")
        if ov and ov.get("pct_plusminus") is not None:
            sigs.append({
                "signal": f"{nm} as primary defender (defended FG%)",
                "number": f"opp shoots {ov['d_fg_pct']} vs {nm} (normal {ov['normal_fg_pct']}), "
                          f"PCT+/- {ov['pct_plusminus']} on {ov['d_fga_pg']} FGA/g",
                "read": "Negative PCT+/- = lockdown; positive = attackable matchup "
                        "-> target opposing scorer's prop accordingly.",
            })

    # Best/worst lineups
    for tag, rows in enrich["lineups"].items():
        if rows:
            top = max(rows, key=lambda r: r["net_rating"] if r["net_rating"] is not None else -999)
            sigs.append({
                "signal": f"{tag} top 5-man lineup (PO, by net rating)",
                "number": f"{top['lineup']}: net {top['net_rating']} "
                          f"(off {top['off_rating']}/def {top['def_rating']}) over {top['min_pg']} min/g",
                "read": "If this five is the likely G7 close lineup, its net rating biases "
                        "team total / spread / live in-game direction.",
            })

    enrich["blockers"] = blockers
    out_path = os.path.join(OUT_DIR, "nba_enrich_g7.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(enrich, f, indent=2)
    print(f"\nWROTE {out_path}")
    print(f"endpoints_ok={len(enrich['endpoints_ok'])} signals={len(sigs)} blockers={len(blockers)}")
    return out_path


if __name__ == "__main__":
    main()
