"""
backfill_wcf_playoff.py
Backfill WCF G1-G6 into season_games_2025-26.json and recompute G7 features.
All as-of logic is PREGAME (no leakage).
G5/G6 off/def rtg are estimated from final scores + pace ~99 (FLAGGED in output).
"""
import json, shutil, math
from pathlib import Path

DATA_NBA = Path("C:/Users/neelj/nba-ai-system/data/nba")
JSON_PATH = DATA_NBA / "season_games_2025-26.json"
BAK_PATH  = DATA_NBA / "season_games_2025-26.json.bak_game7"

# 1. Verify backup exists
print("Backup exists:", BAK_PATH.exists())
if not BAK_PATH.exists():
    shutil.copy2(JSON_PATH, BAK_PATH)
    print("  --> Created backup")

# 2. Load file
with open(JSON_PATH, encoding="utf-8") as f:
    data = json.load(f)
rows = data["rows"]

# Remove existing synthetic G7 row and any pre-existing playoff rows for this series
orig_count = len(rows)
rows = [r for r in rows if r.get("game_id") not in [
    "0042500311","0042500312","0042500313","0042500314","0042500315","0042500316","0042500317"
]]
print(f"Removed existing playoff rows: {orig_count} -> {len(rows)}")

# ---- CONSTANTS: END-OF-REGULAR-SEASON BASELINES ----
# From last OKC home game (0022501196) and last OKC away game (0022501182)
# and last SAS home game (0022501197) and last SAS away game (0022501130)
OKC_REG = {
    "off_rtg": 116.46,
    "def_rtg": 104.53,
    "net_rtg": 11.93,
    "pace":    100.32,
    "efg_pct": 0.5618,
    "ts_pct":  0.6001,
    "tov_pct": 0.1231,
    "elo":     1723.9,
    "srs":     12.551,
    "win_pct": 0.7901,
    "last5_wins": 4.0,
    "off_rtg_L10": 121.12,
    "def_rtg_L10": 104.95,
    "net_rtg_L10": 16.17,
    "efg_L10": 0.5907,
    "tov_pct_L10": 0.1157,
    "oreb_pct_L10": 0.2356,
    "ft_rate_L10": 0.2514,
    "off_rtg_home_L10": 118.47,
    "off_rtg_away_L10": 116.34,
    "off_rtg_vs_top_def": 114.92,
    "top_lineup_net_rtg": 58.0,
    "pnr_ppp": 0.998,
    "def_rtg_trend": 0.42,
    "pace_variance": 2.0,
}

SAS_REG = {
    "off_rtg": 116.62,
    "def_rtg": 108.32,
    "net_rtg": 8.31,
    "pace":    101.181,
    "efg_pct": 0.5593,
    "ts_pct":  0.5955,
    "tov_pct": 0.1314,
    "elo":     1722.61,
    "srs":     11.018,
    "win_pct": 0.7654,
    "last5_wins": 4.0,
    "off_rtg_L10": 121.24,
    "def_rtg_L10": 105.91,
    "net_rtg_L10": 15.33,
    "efg_L10": 0.5786,
    "tov_pct_L10": 0.1155,
    "oreb_pct_L10": 0.2929,
    "ft_rate_L10": 0.2505,
    "off_rtg_home_L10": 122.51,
    "off_rtg_away_L10": 120.0,
    "off_rtg_vs_top_def": 112.0,
    "top_lineup_net_rtg": 35.9,
    "pnr_ppp": 0.883,
    "def_rtg_trend": -2.41,
    "pace_variance": 2.0,
}

# ---- SERIES GAME DATA ----
# G1-G4: full per-game data from wcf_team_series_agg.json (off_rtg, def_rtg, efg, tov, oreb from box score)
# G5/G6: scores only — off/def rtg estimated from pts + ~99 possessions (FLAGGED)
# Columns: game_id, date, home, away, home_pts, away_pts,
#          okc_off, okc_def, sas_off, sas_def,
#          okc_efg, sas_efg, okc_tov, sas_tov, okc_oreb, sas_oreb, pace
SERIES_GAMES = [
    ("0042500311","2026-05-18","OKC","SAS",115,122, 102.7,106.1, 106.1,102.7, 0.490,0.495, 0.134,0.200, 0.210,0.368, 93.93,  False),
    ("0042500312","2026-05-20","OKC","SAS",122,113, 124.5,116.5, 116.5,124.5, 0.548,0.583, 0.102,0.216, 0.380,0.386, 97.50,  False),
    ("0042500313","2026-05-22","SAS","OKC",108,123, 124.2,111.3, 111.3,124.2, 0.586,0.506, 0.111,0.155, 0.295,0.255, 98.00,  False),
    ("0042500314","2026-05-24","SAS","OKC", 82,103,  80.4,102.0, 102.0, 80.4, 0.363,0.439, 0.196,0.129, 0.323,0.322, 101.50, False),
    # G5/G6: estimated off/def rtg (pace ~99 assumed; est_rtg flag = True)
    # G5 OKC 127, SAS 114 @ OKC. Poss ~ (127+114)/2/0.5 ~ 99; off_rtg = pts/99*100
    ("0042500315","2026-05-26","OKC","SAS",127,114, 128.3,115.2, 115.2,128.3, None,None, None,None, None,None, 99.0,  True),
    # G6 SAS 118, OKC 91 @ SAS. Poss ~99
    ("0042500316","2026-05-28","SAS","OKC",118, 91,  91.9,119.2, 119.2, 91.9, None,None, None,None, None,None, 99.0,  True),
]


def elo_expected(elo_a, elo_b):
    return 1.0 / (1.0 + 10**((elo_b - elo_a) / 400.0))


def elo_update(elo_a, elo_b, a_won, K=20.0):
    ea = elo_expected(elo_a, elo_b)
    return round(elo_a + K * (a_won - ea), 4)


def expanding_mean(lst, key, default):
    if not lst:
        return default
    vals = [x[key] for x in lst if x.get(key) is not None]
    return sum(vals)/len(vals) if vals else default


def blend(reg_val, playoff_vals, weight_per_game=82):
    """Blend regular season value (82-game anchor) with playoff games."""
    n = len(playoff_vals)
    if n == 0:
        return reg_val
    pl_avg = sum(playoff_vals) / n
    return (reg_val * weight_per_game + pl_avg * n) / (weight_per_game + n)


def rtg_trend(results_list, key):
    vals = [x[key] for x in results_list[-3:] if x.get(key) is not None]
    if len(vals) < 2:
        return 0.0
    return (vals[-1] - vals[0]) / (len(vals)-1)


# Starting elos (end of regular season)
okc_elo = OKC_REG["elo"]   # 1723.9
sas_elo = SAS_REG["elo"]   # 1722.61

okc_results = []  # per-game history for rolling stats
sas_results = []

print("\nBuilding playoff game rows...")
playoff_rows = []

for i, (gid, date, home, away, home_pts, away_pts,
        okc_off, okc_def, sas_off, sas_def,
        okc_efg, sas_efg, okc_tov, sas_tov,
        okc_oreb, sas_oreb, pace, est_flag) in enumerate(SERIES_GAMES):

    game_num = i + 1
    home_win = 1 if home_pts > away_pts else 0

    # --- Elos BEFORE this game (pregame) ---
    pre_okc_elo = okc_elo
    pre_sas_elo = sas_elo

    # --- L10 stats (expanding mean of prior playoff games; falls back to reg-season L10) ---
    okc_off_L10 = expanding_mean(okc_results, "off_rtg", OKC_REG["off_rtg_L10"])
    okc_def_L10 = expanding_mean(okc_results, "def_rtg", OKC_REG["def_rtg_L10"])
    okc_net_L10 = okc_off_L10 - okc_def_L10
    okc_efg_L10     = expanding_mean(okc_results, "efg",    OKC_REG["efg_L10"])
    okc_tov_L10     = expanding_mean(okc_results, "tov",    OKC_REG["tov_pct_L10"])
    okc_oreb_L10    = expanding_mean(okc_results, "oreb",   OKC_REG["oreb_pct_L10"])
    okc_ft_L10      = expanding_mean(okc_results, "ft_rate",OKC_REG["ft_rate_L10"])

    sas_off_L10 = expanding_mean(sas_results, "off_rtg", SAS_REG["off_rtg_L10"])
    sas_def_L10 = expanding_mean(sas_results, "def_rtg", SAS_REG["def_rtg_L10"])
    sas_net_L10 = sas_off_L10 - sas_def_L10
    sas_efg_L10     = expanding_mean(sas_results, "efg",    SAS_REG["efg_L10"])
    sas_tov_L10     = expanding_mean(sas_results, "tov",    SAS_REG["tov_pct_L10"])
    sas_oreb_L10    = expanding_mean(sas_results, "oreb",   SAS_REG["oreb_pct_L10"])
    sas_ft_L10      = expanding_mean(sas_results, "ft_rate",SAS_REG["ft_rate_L10"])

    # --- Season-level stats (blended reg-season anchor + playoff expanding) ---
    okc_off_s  = blend(OKC_REG["off_rtg"],  [x["off_rtg"]  for x in okc_results if x.get("off_rtg")])
    okc_def_s  = blend(OKC_REG["def_rtg"],  [x["def_rtg"]  for x in okc_results if x.get("def_rtg")])
    okc_net_s  = okc_off_s - okc_def_s
    okc_pace_s = blend(OKC_REG["pace"],     [x["pace"]     for x in okc_results if x.get("pace")])
    okc_efg_s  = blend(OKC_REG["efg_pct"],  [x["efg"]      for x in okc_results if x.get("efg")])
    okc_tov_s  = blend(OKC_REG["tov_pct"],  [x["tov"]      for x in okc_results if x.get("tov")])

    sas_off_s  = blend(SAS_REG["off_rtg"],  [x["off_rtg"]  for x in sas_results if x.get("off_rtg")])
    sas_def_s  = blend(SAS_REG["def_rtg"],  [x["def_rtg"]  for x in sas_results if x.get("def_rtg")])
    sas_net_s  = sas_off_s - sas_def_s
    sas_pace_s = blend(SAS_REG["pace"],     [x["pace"]     for x in sas_results if x.get("pace")])
    sas_efg_s  = blend(SAS_REG["efg_pct"],  [x["efg"]      for x in sas_results if x.get("efg")])
    sas_tov_s  = blend(SAS_REG["tov_pct"],  [x["tov"]      for x in sas_results if x.get("tov")])

    # Fallback for G5/G6 missing detail stats
    if okc_efg is None:
        okc_efg  = expanding_mean(okc_results, "efg",  OKC_REG["efg_pct"])
    if sas_efg is None:
        sas_efg  = expanding_mean(sas_results, "efg",  SAS_REG["efg_pct"])
    if okc_tov is None:
        okc_tov  = expanding_mean(okc_results, "tov",  OKC_REG["tov_pct"])
    if sas_tov is None:
        sas_tov  = expanding_mean(sas_results, "tov",  SAS_REG["tov_pct"])
    if okc_oreb is None:
        okc_oreb = expanding_mean(okc_results, "oreb", OKC_REG["oreb_pct_L10"])
    if sas_oreb is None:
        sas_oreb = expanding_mean(sas_results, "oreb", SAS_REG["oreb_pct_L10"])

    # last5_wins = wins in series up to (not including) this game
    okc_series_wins = sum(g.get("okc_won", 0) for g in okc_results)
    sas_series_wins = sum(g.get("sas_won", 0) for g in sas_results)

    # home/away split L10
    if home == "OKC":
        home_off_home_L10 = expanding_mean([x for x in okc_results if x.get("is_home")], "off_rtg", OKC_REG["off_rtg_home_L10"])
        away_off_away_L10 = expanding_mean([x for x in sas_results if not x.get("is_home")], "off_rtg", SAS_REG["off_rtg_away_L10"])
    else:
        home_off_home_L10 = expanding_mean([x for x in sas_results if x.get("is_home")], "off_rtg", SAS_REG["off_rtg_home_L10"])
        away_off_away_L10 = expanding_mean([x for x in okc_results if not x.get("is_home")], "off_rtg", OKC_REG["off_rtg_away_L10"])

    okc_def_trend = rtg_trend(okc_results, "def_rtg")
    sas_def_trend = rtg_trend(sas_results, "def_rtg")

    # sim_win_prob from pre-game elo
    if home == "OKC":
        sim_wp = round(elo_expected(pre_okc_elo, pre_sas_elo), 4)
        h_elo, a_elo = pre_okc_elo, pre_sas_elo
        elo_diff = pre_okc_elo - pre_sas_elo
        h_off, h_def, h_net  = okc_off_s,  okc_def_s,  okc_net_s
        h_pace, h_efg, h_ts  = okc_pace_s, okc_efg_s,  OKC_REG["ts_pct"]
        h_tov                = okc_tov_s
        h_off_L10, h_def_L10 = okc_off_L10, okc_def_L10
        h_net_L10            = okc_net_L10
        h_efg_L10, h_tov_L10, h_oreb_L10, h_ft_L10 = okc_efg_L10, okc_tov_L10, okc_oreb_L10, okc_ft_L10
        h_srs, h_win_pct, h_last5 = OKC_REG["srs"], OKC_REG["win_pct"], float(okc_series_wins)
        h_top_lu, h_pnr      = OKC_REG["top_lineup_net_rtg"], OKC_REG["pnr_ppp"]
        h_def_trend          = okc_def_trend
        h_pace_var           = OKC_REG["pace_variance"]
        h_vs_top             = OKC_REG["off_rtg_vs_top_def"]
        a_off, a_def, a_net  = sas_off_s,  sas_def_s,  sas_net_s
        a_pace, a_efg, a_ts  = sas_pace_s, sas_efg_s,  SAS_REG["ts_pct"]
        a_tov                = sas_tov_s
        a_off_L10, a_def_L10 = sas_off_L10, sas_def_L10
        a_net_L10            = sas_net_L10
        a_efg_L10, a_tov_L10, a_oreb_L10, a_ft_L10 = sas_efg_L10, sas_tov_L10, sas_oreb_L10, sas_ft_L10
        a_srs, a_win_pct, a_last5 = SAS_REG["srs"], SAS_REG["win_pct"], float(sas_series_wins)
        a_top_lu, a_pnr      = SAS_REG["top_lineup_net_rtg"], SAS_REG["pnr_ppp"]
        a_def_trend          = sas_def_trend
        a_pace_var           = SAS_REG["pace_variance"]
        a_vs_top             = SAS_REG["off_rtg_vs_top_def"]
        travel_away          = 990.0
    else:  # home == "SAS"
        sim_wp = round(elo_expected(pre_sas_elo, pre_okc_elo), 4)
        h_elo, a_elo = pre_sas_elo, pre_okc_elo
        elo_diff = pre_sas_elo - pre_okc_elo
        h_off, h_def, h_net  = sas_off_s,  sas_def_s,  sas_net_s
        h_pace, h_efg, h_ts  = sas_pace_s, sas_efg_s,  SAS_REG["ts_pct"]
        h_tov                = sas_tov_s
        h_off_L10, h_def_L10 = sas_off_L10, sas_def_L10
        h_net_L10            = sas_net_L10
        h_efg_L10, h_tov_L10, h_oreb_L10, h_ft_L10 = sas_efg_L10, sas_tov_L10, sas_oreb_L10, sas_ft_L10
        h_srs, h_win_pct, h_last5 = SAS_REG["srs"], SAS_REG["win_pct"], float(sas_series_wins)
        h_top_lu, h_pnr      = SAS_REG["top_lineup_net_rtg"], SAS_REG["pnr_ppp"]
        h_def_trend          = sas_def_trend
        h_pace_var           = SAS_REG["pace_variance"]
        h_vs_top             = SAS_REG["off_rtg_vs_top_def"]
        a_off, a_def, a_net  = okc_off_s,  okc_def_s,  okc_net_s
        a_pace, a_efg, a_ts  = okc_pace_s, okc_efg_s,  OKC_REG["ts_pct"]
        a_tov                = okc_tov_s
        a_off_L10, a_def_L10 = okc_off_L10, okc_def_L10
        a_net_L10            = okc_net_L10
        a_efg_L10, a_tov_L10, a_oreb_L10, a_ft_L10 = okc_efg_L10, okc_tov_L10, okc_oreb_L10, okc_ft_L10
        a_srs, a_win_pct, a_last5 = OKC_REG["srs"], OKC_REG["win_pct"], float(okc_series_wins)
        a_top_lu, a_pnr      = OKC_REG["top_lineup_net_rtg"], OKC_REG["pnr_ppp"]
        a_def_trend          = okc_def_trend
        a_pace_var           = OKC_REG["pace_variance"]
        a_vs_top             = OKC_REG["off_rtg_vs_top_def"]
        travel_away          = 990.0

    elo_pace_interaction = round(elo_diff * pace, 4)

    row = {
        "game_id": gid,
        "season": "2025-26",
        "game_date": date,
        "home_team": home,
        "away_team": away,
        "home_win": home_win,
        "home_off_rtg":              round(h_off, 4),
        "home_def_rtg":              round(h_def, 4),
        "home_net_rtg":              round(h_net, 4),
        "home_pace":                 round(h_pace, 4),
        "home_efg_pct":              round(h_efg, 4),
        "home_ts_pct":               round(h_ts, 4),
        "home_tov_pct":              round(h_tov, 4),
        "home_rest_days":            2.0,
        "home_back_to_back":         0.0,
        "home_travel_miles":         0.0,
        "home_last5_wins":           h_last5,
        "home_season_win_pct":       h_win_pct,
        "away_off_rtg":              round(a_off, 4),
        "away_def_rtg":              round(a_def, 4),
        "away_net_rtg":              round(a_net, 4),
        "away_pace":                 round(a_pace, 4),
        "away_efg_pct":              round(a_efg, 4),
        "away_ts_pct":               round(a_ts, 4),
        "away_tov_pct":              round(a_tov, 4),
        "away_rest_days":            2.0,
        "away_back_to_back":         0.0,
        "away_travel_miles":         travel_away,
        "away_last5_wins":           a_last5,
        "away_season_win_pct":       a_win_pct,
        "net_rtg_diff":              round(h_net - a_net, 4),
        "pace_diff":                 round(h_pace - a_pace, 4),
        "home_advantage":            1.0,
        "home_off_rtg_L10":          round(h_off_L10, 4),
        "home_def_rtg_L10":          round(h_def_L10, 4),
        "home_net_rtg_L10":          round(h_net_L10, 4),
        "away_off_rtg_L10":          round(a_off_L10, 4),
        "away_def_rtg_L10":          round(a_def_L10, 4),
        "away_net_rtg_L10":          round(a_net_L10, 4),
        "home_efg_L10":              round(h_efg_L10, 4),
        "away_efg_L10":              round(a_efg_L10, 4),
        "home_tov_pct_L10":          round(h_tov_L10, 4),
        "away_tov_pct_L10":          round(a_tov_L10, 4),
        "home_oreb_pct_L10":         round(h_oreb_L10, 4),
        "away_oreb_pct_L10":         round(a_oreb_L10, 4),
        "home_ft_rate_L10":          round(h_ft_L10, 4),
        "away_ft_rate_L10":          round(a_ft_L10, 4),
        "home_off_rtg_home_L10":     round(home_off_home_L10, 4),
        "away_off_rtg_away_L10":     round(away_off_away_L10, 4),
        "home_off_rtg_vs_top_def":   h_vs_top,
        "away_off_rtg_vs_top_def":   a_vs_top,
        "home_srs":                  h_srs,
        "away_srs":                  a_srs,
        "home_elo":                  round(h_elo, 4),
        "away_elo":                  round(a_elo, 4),
        "elo_differential":          round(elo_diff, 4),
        "home_def_rtg_trend":        round(h_def_trend, 4),
        "away_def_rtg_trend":        round(a_def_trend, 4),
        "home_pace_variance":        h_pace_var,
        "away_pace_variance":        a_pace_var,
        "home_top_lineup_net_rtg":   h_top_lu,
        "away_top_lineup_net_rtg":   a_top_lu,
        "iso_matchup_edge":          0.0,
        "home_pnr_ppp":              h_pnr,
        "away_pnr_ppp":              a_pnr,
        "home_hustle_deflections_pg":0.0,
        "away_hustle_deflections_pg":0.0,
        "home_stars_available":      3,
        "away_stars_available":      3,
        "home_bench_net_rtg":        0.0,
        "away_bench_net_rtg":        0.0,
        "ref_avg_fouls":             42.0,
        "ref_home_win_pct":          0.5,
        "ref_fta_tendency":          0.0,
        "b2b_diff":                  0.0,
        "elo_pace_interaction":      elo_pace_interaction,
        "sim_win_prob":              sim_wp,
        "sim_score_diff_mean":       0.0,
        "sim_score_diff_std":        10.0,
        "sim_pace_adj":              round(pace / 100.0, 4),
    }
    if est_flag:
        row["_note"] = "G5/G6: off/def rtg estimated from score+pace=99 (no box score)"

    playoff_rows.append(row)
    flag_str = " [ESTIMATED rtg]" if est_flag else ""
    print(f"  G{game_num} {gid} {home} vs {away} {home_pts}-{away_pts}{flag_str}")
    print(f"         OKC_elo={pre_okc_elo:.1f} SAS_elo={pre_sas_elo:.1f}  "
          f"okc_off_L10={okc_off_L10:.1f} sas_off_L10={sas_off_L10:.1f}")

    # ============== UPDATE STATE FOR NEXT GAME ==============
    okc_won_this = 1 if (home == "OKC" and home_win == 1) or (home == "SAS" and home_win == 0) else 0
    sas_won_this = 1 - okc_won_this

    okc_elo = elo_update(pre_okc_elo, pre_sas_elo, okc_won_this, K=20.0)
    sas_elo = elo_update(pre_sas_elo, pre_okc_elo, sas_won_this, K=20.0)

    okc_results.append({
        "off_rtg": okc_off, "def_rtg": okc_def,
        "efg": okc_efg, "tov": okc_tov, "oreb": okc_oreb,
        "ft_rate": OKC_REG["ft_rate_L10"],  # no FTA data for G5/G6; use reg season proxy
        "pace": pace, "is_home": (home == "OKC"),
        "okc_won": okc_won_this,
    })
    sas_results.append({
        "off_rtg": sas_off, "def_rtg": sas_def,
        "efg": sas_efg, "tov": sas_tov, "oreb": sas_oreb,
        "ft_rate": SAS_REG["ft_rate_L10"],
        "pace": pace, "is_home": (home == "SAS"),
        "sas_won": sas_won_this,
    })

print(f"\nAfter G6: OKC_elo={okc_elo:.2f} SAS_elo={sas_elo:.2f}")
print(f"  OKC wins: {sum(g['okc_won'] for g in okc_results)}  "
      f"SAS wins: {sum(g['sas_won'] for g in sas_results)}")

# ============== BUILD G7 ROW ==============
pre_okc_elo_g7 = okc_elo
pre_sas_elo_g7 = sas_elo
elo_diff_g7 = pre_okc_elo_g7 - pre_sas_elo_g7

okc_off_L10_g7  = expanding_mean(okc_results, "off_rtg", OKC_REG["off_rtg_L10"])
okc_def_L10_g7  = expanding_mean(okc_results, "def_rtg", OKC_REG["def_rtg_L10"])
okc_net_L10_g7  = okc_off_L10_g7 - okc_def_L10_g7
okc_efg_L10_g7  = expanding_mean(okc_results, "efg",     OKC_REG["efg_L10"])
okc_tov_L10_g7  = expanding_mean(okc_results, "tov",     OKC_REG["tov_pct_L10"])
okc_oreb_L10_g7 = expanding_mean(okc_results, "oreb",    OKC_REG["oreb_pct_L10"])
okc_ft_L10_g7   = expanding_mean(okc_results, "ft_rate", OKC_REG["ft_rate_L10"])

sas_off_L10_g7  = expanding_mean(sas_results, "off_rtg", SAS_REG["off_rtg_L10"])
sas_def_L10_g7  = expanding_mean(sas_results, "def_rtg", SAS_REG["def_rtg_L10"])
sas_net_L10_g7  = sas_off_L10_g7 - sas_def_L10_g7
sas_efg_L10_g7  = expanding_mean(sas_results, "efg",     SAS_REG["efg_L10"])
sas_tov_L10_g7  = expanding_mean(sas_results, "tov",     SAS_REG["tov_pct_L10"])
sas_oreb_L10_g7 = expanding_mean(sas_results, "oreb",    SAS_REG["oreb_pct_L10"])
sas_ft_L10_g7   = expanding_mean(sas_results, "ft_rate", SAS_REG["ft_rate_L10"])

okc_off_s_g7  = blend(OKC_REG["off_rtg"],  [x["off_rtg"]  for x in okc_results if x.get("off_rtg")])
okc_def_s_g7  = blend(OKC_REG["def_rtg"],  [x["def_rtg"]  for x in okc_results if x.get("def_rtg")])
okc_net_s_g7  = okc_off_s_g7 - okc_def_s_g7
okc_pace_s_g7 = blend(OKC_REG["pace"],     [x["pace"]     for x in okc_results if x.get("pace")])
okc_efg_s_g7  = blend(OKC_REG["efg_pct"],  [x["efg"]      for x in okc_results if x.get("efg")])
okc_tov_s_g7  = blend(OKC_REG["tov_pct"],  [x["tov"]      for x in okc_results if x.get("tov")])

sas_off_s_g7  = blend(SAS_REG["off_rtg"],  [x["off_rtg"]  for x in sas_results if x.get("off_rtg")])
sas_def_s_g7  = blend(SAS_REG["def_rtg"],  [x["def_rtg"]  for x in sas_results if x.get("def_rtg")])
sas_net_s_g7  = sas_off_s_g7 - sas_def_s_g7
sas_pace_s_g7 = blend(SAS_REG["pace"],     [x["pace"]     for x in sas_results if x.get("pace")])
sas_efg_s_g7  = blend(SAS_REG["efg_pct"],  [x["efg"]      for x in sas_results if x.get("efg")])
sas_tov_s_g7  = blend(SAS_REG["tov_pct"],  [x["tov"]      for x in sas_results if x.get("tov")])

okc_series_wins_g7 = sum(g.get("okc_won", 0) for g in okc_results)
sas_series_wins_g7 = sum(g.get("sas_won", 0) for g in sas_results)

okc_home_off_L10_g7 = expanding_mean([x for x in okc_results if x.get("is_home")], "off_rtg", OKC_REG["off_rtg_home_L10"])
sas_away_off_L10_g7 = expanding_mean([x for x in sas_results if not x.get("is_home")], "off_rtg", SAS_REG["off_rtg_away_L10"])

okc_def_trend_g7 = rtg_trend(okc_results, "def_rtg")
sas_def_trend_g7 = rtg_trend(sas_results, "def_rtg")

pace_g7 = expanding_mean(okc_results, "pace", OKC_REG["pace"])
sim_wp_g7 = round(elo_expected(pre_okc_elo_g7, pre_sas_elo_g7), 4)
elo_pace_g7 = round(elo_diff_g7 * pace_g7, 4)

g7_row = {
    "game_id": "0042500317",
    "season": "2025-26",
    "game_date": "2026-05-30",
    "home_team": "OKC",
    "away_team": "SAS",
    "home_win": None,
    "home_off_rtg":              round(okc_off_s_g7, 4),
    "home_def_rtg":              round(okc_def_s_g7, 4),
    "home_net_rtg":              round(okc_net_s_g7, 4),
    "home_pace":                 round(okc_pace_s_g7, 4),
    "home_efg_pct":              round(okc_efg_s_g7, 4),
    "home_ts_pct":               OKC_REG["ts_pct"],
    "home_tov_pct":              round(okc_tov_s_g7, 4),
    "home_rest_days":            2.0,
    "home_back_to_back":         0.0,
    "home_travel_miles":         0.0,
    "home_last5_wins":           float(okc_series_wins_g7),
    "home_season_win_pct":       OKC_REG["win_pct"],
    "away_off_rtg":              round(sas_off_s_g7, 4),
    "away_def_rtg":              round(sas_def_s_g7, 4),
    "away_net_rtg":              round(sas_net_s_g7, 4),
    "away_pace":                 round(sas_pace_s_g7, 4),
    "away_efg_pct":              round(sas_efg_s_g7, 4),
    "away_ts_pct":               SAS_REG["ts_pct"],
    "away_tov_pct":              round(sas_tov_s_g7, 4),
    "away_rest_days":            2.0,
    "away_back_to_back":         0.0,
    "away_travel_miles":         990.0,
    "away_last5_wins":           float(sas_series_wins_g7),
    "away_season_win_pct":       SAS_REG["win_pct"],
    "net_rtg_diff":              round(okc_net_s_g7 - sas_net_s_g7, 4),
    "pace_diff":                 round(okc_pace_s_g7 - sas_pace_s_g7, 4),
    "home_advantage":            1.0,
    "home_off_rtg_L10":          round(okc_off_L10_g7, 4),
    "home_def_rtg_L10":          round(okc_def_L10_g7, 4),
    "home_net_rtg_L10":          round(okc_net_L10_g7, 4),
    "away_off_rtg_L10":          round(sas_off_L10_g7, 4),
    "away_def_rtg_L10":          round(sas_def_L10_g7, 4),
    "away_net_rtg_L10":          round(sas_net_L10_g7, 4),
    "home_efg_L10":              round(okc_efg_L10_g7, 4),
    "away_efg_L10":              round(sas_efg_L10_g7, 4),
    "home_tov_pct_L10":          round(okc_tov_L10_g7, 4),
    "away_tov_pct_L10":          round(sas_tov_L10_g7, 4),
    "home_oreb_pct_L10":         round(okc_oreb_L10_g7, 4),
    "away_oreb_pct_L10":         round(sas_oreb_L10_g7, 4),
    "home_ft_rate_L10":          round(okc_ft_L10_g7, 4),
    "away_ft_rate_L10":          round(sas_ft_L10_g7, 4),
    "home_off_rtg_home_L10":     round(okc_home_off_L10_g7, 4),
    "away_off_rtg_away_L10":     round(sas_away_off_L10_g7, 4),
    "home_off_rtg_vs_top_def":   OKC_REG["off_rtg_vs_top_def"],
    "away_off_rtg_vs_top_def":   SAS_REG["off_rtg_vs_top_def"],
    "home_srs":                  OKC_REG["srs"],
    "away_srs":                  SAS_REG["srs"],
    "home_elo":                  round(pre_okc_elo_g7, 4),
    "away_elo":                  round(pre_sas_elo_g7, 4),
    "elo_differential":          round(elo_diff_g7, 4),
    "home_def_rtg_trend":        round(okc_def_trend_g7, 4),
    "away_def_rtg_trend":        round(sas_def_trend_g7, 4),
    "home_pace_variance":        OKC_REG["pace_variance"],
    "away_pace_variance":        SAS_REG["pace_variance"],
    "home_top_lineup_net_rtg":   OKC_REG["top_lineup_net_rtg"],
    "away_top_lineup_net_rtg":   SAS_REG["top_lineup_net_rtg"],
    "iso_matchup_edge":          0.0,
    "home_pnr_ppp":              OKC_REG["pnr_ppp"],
    "away_pnr_ppp":              SAS_REG["pnr_ppp"],
    "home_hustle_deflections_pg":0.0,
    "away_hustle_deflections_pg":0.0,
    "home_stars_available":      3,
    "away_stars_available":      3,
    "home_bench_net_rtg":        0.0,
    "away_bench_net_rtg":        0.0,
    "ref_avg_fouls":             42.0,
    "ref_home_win_pct":          0.5,
    "ref_fta_tendency":          0.0,
    "b2b_diff":                  0.0,
    "elo_pace_interaction":      elo_pace_g7,
    "sim_win_prob":              sim_wp_g7,
    "sim_score_diff_mean":       0.0,
    "sim_score_diff_std":        10.0,
    "sim_pace_adj":              round(pace_g7 / 100.0, 4),
}

print(f"\nG7 pregame features:")
print(f"  OKC_elo={pre_okc_elo_g7:.2f}  SAS_elo={pre_sas_elo_g7:.2f}  elo_diff={elo_diff_g7:.2f}")
print(f"  OKC off_L10={okc_off_L10_g7:.2f}  def_L10={okc_def_L10_g7:.2f}  net_L10={okc_net_L10_g7:.2f}")
print(f"  SAS off_L10={sas_off_L10_g7:.2f}  def_L10={sas_def_L10_g7:.2f}  net_L10={sas_net_L10_g7:.2f}")
print(f"  OKC season off={okc_off_s_g7:.2f}  def={okc_def_s_g7:.2f}  net={okc_net_s_g7:.2f}")
print(f"  SAS season off={sas_off_s_g7:.2f}  def={sas_def_s_g7:.2f}  net={sas_net_s_g7:.2f}")
print(f"  okc_series_wins={okc_series_wins_g7}  sas_series_wins={sas_series_wins_g7}")
print(f"  pace_g7={pace_g7:.2f}  sim_wp={sim_wp_g7}")

# ============== WRITE FILE ==============
rows.extend(playoff_rows)
rows.append(g7_row)
data["rows"] = rows

with open(JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print(f"\nWrote {len(rows)} rows to {JSON_PATH}")
print(f"  Added {len(playoff_rows)} G1-G6 rows + 1 updated G7 row")
print(f"  Backup at: {BAK_PATH}")
