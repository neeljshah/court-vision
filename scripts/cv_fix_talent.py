"""cv_fix_talent.py — fetch per-player true-talent shooting (season eFG%) so the simulator
separates SHOT-MAKING TALENT from luck. Writes data/cache/cv_fix/talent.json {pid: mult}."""
import json, os, sys
from nba_api.stats.endpoints import leaguedashplayerstats
season = sys.argv[1] if len(sys.argv) > 1 else "2025-26"
stype = sys.argv[2] if len(sys.argv) > 2 else "Regular Season"
df = leaguedashplayerstats.LeagueDashPlayerStats(season=season, season_type_all_star=stype,
        per_mode_detailed="Totals").get_data_frames()[0]
# eFG = (FGM + 0.5*FG3M)/FGA ; talent mult vs league, clamped, min-volume guarded
fga = df["FGA"].clip(lower=1)
efg = (df["FGM"] + 0.5 * df["FG3M"]) / fga
lg = float(((df["FGM"].sum() + 0.5 * df["FG3M"].sum()) / max(1, df["FGA"].sum())))
talent = {}
for pid, e, n in zip(df["PLAYER_ID"], efg, df["FGA"]):
    if n < 50:
        m = 1.0  # too few attempts -> neutral
    else:
        m = max(0.85, min(1.18, float(e) / lg))
    talent[str(int(pid))] = round(m, 3)
os.makedirs("data/cache/cv_fix", exist_ok=True)
json.dump({"league_efg": round(lg, 3), "season": season, "type": stype, "mult": talent},
          open("data/cache/cv_fix/talent.json", "w"), indent=2)
print(f"talent.json: {len(talent)} players, league eFG {lg:.3f}")
