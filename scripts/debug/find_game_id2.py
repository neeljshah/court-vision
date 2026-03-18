"""Find specific Cavs vs Warriors game_id."""
import json, os

path = "data/nba/season_games_2024-25.json"
data = json.load(open(path))
rows = data.get("rows", [])

for r in rows:
    h = r.get("home_team", "")
    a = r.get("away_team", "")
    if ("CLE" in h or "CLE" in a) and ("GSW" in h or "GSW" in a):
        print(r)
