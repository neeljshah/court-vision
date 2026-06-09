"""cv_fix_harvest_nba.py <game_id> — pull core NBA ground-truth for one game to
data/cache/cv_fix/nba_<gid>/. Safe to run in parallel across games (network only)."""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
gid = sys.argv[1]
out = f"data/cache/cv_fix/nba_{gid}"
os.makedirs(out, exist_ok=True)
from nba_api.stats.endpoints import (playbyplayv3, boxscoretraditionalv3, boxscoreadvancedv3,
    shotchartdetail, hustlestatsboxscore, boxscorematchupsv3, boxscoreplayertrackv3, gamerotation)

def save(name, fn):
    try:
        time.sleep(0.6)
        dfs = fn()
        if isinstance(dfs, list):
            for i, df in enumerate(dfs):
                df.to_json(f"{out}/{name}_{i}.json", orient="records")
            print(f"OK {name}: {[len(d) for d in dfs]}")
        else:
            dfs.to_json(f"{out}/{name}.json", orient="records")
            print(f"OK {name}: {len(dfs)}")
    except Exception as e:
        print(f"FAIL {name}: {e}")

save("pbp", lambda: playbyplayv3.PlayByPlayV3(game_id=gid).get_data_frames()[0])
save("box_traditional", lambda: boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=gid).get_data_frames()[0])
save("box_advanced", lambda: boxscoreadvancedv3.BoxScoreAdvancedV3(game_id=gid).get_data_frames()[0])
save("shotchart", lambda: shotchartdetail.ShotChartDetail(game_id_nullable=gid, team_id=0, player_id=0,
     context_measure_simple="FGA", season_type_all_star="Playoffs", season_nullable="2025-26").get_data_frames()[0])
save("hustle", lambda: hustlestatsboxscore.HustleStatsBoxScore(game_id=gid).get_data_frames()[1])
save("matchups", lambda: boxscorematchupsv3.BoxScoreMatchupsV3(game_id=gid).get_data_frames()[0])
save("playertrack", lambda: boxscoreplayertrackv3.BoxScorePlayerTrackV3(game_id=gid).get_data_frames()[0])
save("rotation", lambda: gamerotation.GameRotation(game_id=gid).get_data_frames())
print("DONE", gid)
