"""Find a game_id that matches the Cavs vs Warriors game in season data."""
import json, os

seasons = [
    "data/nba/season_games_2024-25.json",
    "data/nba/season_games_2023-24.json",
    "data/nba/season_games_2022-23.json",
]

for path in seasons:
    if not os.path.exists(path):
        continue
    data = json.load(open(path))
    # data might be list of game dicts
    if isinstance(data, list):
        games = data
    elif isinstance(data, dict):
        games = data.get("games", data.get("resultSets", [data]))
        if isinstance(games, dict):
            # nested structure
            for k, v in games.items():
                if isinstance(v, list):
                    games = v
                    break
    # find CAV / GSW / CLE / GS games
    found = []
    for g in games if isinstance(games, list) else []:
        if not isinstance(g, dict):
            continue
        vals = str(g)
        if ('CLE' in vals or 'Cavaliers' in vals or 'CAV' in vals) and \
           ('GSW' in vals or 'Warriors' in vals or 'GS' in vals or 'Golden' in vals):
            game_id = g.get('GAME_ID') or g.get('game_id') or g.get('gameId', '')
            found.append((game_id, str(g)[:120]))
    if found:
        print(f"\n{path}: {len(found)} Cavs vs Warriors games found")
        for gid, snippet in found[:3]:
            print(f"  GAME_ID={gid}: {snippet}")
    else:
        print(f"\n{path}: no Cavs vs Warriors game found")
        # Show first game for structure reference
        if isinstance(games, list) and games:
            print(f"  Sample game structure: {str(games[0])[:200]}")
