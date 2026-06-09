"""Debug coherence MAE - understand why 18.87 pts and 115 failures."""
import pandas as pd, os, json, glob, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

oof = pd.read_parquet(os.path.join(ROOT, 'data/cache/pregame_oof_faithful.parquet'))
nba_dir = os.path.join(ROOT, 'data/nba')

# Check first boxscore for player overlap
bs_files = sorted(glob.glob(os.path.join(nba_dir, 'boxscore_*.json')))[:3]
for bf in bs_files:
    with open(bf) as f:
        bs = json.load(f)
    gid = bs.get('game_id', '')
    ht = bs.get('home_team', '')
    at = bs.get('away_team', '')
    bs_players = bs.get('players', [])
    if not bs_players:
        continue

    # find the game's date from season_games
    game_date = None
    for sg_file in glob.glob(os.path.join(nba_dir, 'season_games*.json')):
        with open(sg_file) as f:
            sg = json.load(f)
        if isinstance(sg, dict) and 'rows' in sg:
            for row in sg['rows']:
                if str(row.get('game_id','')) == str(gid):
                    game_date = row.get('game_date','')
                    break
        if game_date:
            break
    if not game_date:
        continue

    # OOF players for this date
    oof_day = oof[(oof['game_date'] == game_date) & (oof['stat'] == 'pts')]
    oof_pids = set(oof_day['player_id'].astype(int))
    bs_pids = {int(p['player_id']) for p in bs_players}
    overlap = bs_pids & oof_pids

    # Actual team pts from boxscore
    home_actual = sum(float(p.get('pts',0) or 0) for p in bs_players if p.get('team_abbreviation')==ht)
    away_actual = sum(float(p.get('pts',0) or 0) for p in bs_players if p.get('team_abbreviation')==at)

    # OOF sum for overlapping players
    home_oof_sum = oof_day[oof_day['player_id'].isin([pid for pid in overlap
                           if any(p.get('team_abbreviation')==ht for p in bs_players if int(p['player_id'])==pid)])]['oof_pred'].sum()
    away_oof_sum = oof_day[oof_day['player_id'].isin([pid for pid in overlap
                           if any(p.get('team_abbreviation')==at for p in bs_players if int(p['player_id'])==pid)])]['oof_pred'].sum()

    n_home = sum(1 for p in bs_players if p.get('team_abbreviation')==ht)
    n_away = sum(1 for p in bs_players if p.get('team_abbreviation')==at)
    n_home_oof = sum(1 for p in bs_players if p.get('team_abbreviation')==ht and int(p.get('player_id',0)) in oof_pids)
    n_away_oof = sum(1 for p in bs_players if p.get('team_abbreviation')==at and int(p.get('player_id',0)) in oof_pids)

    print(f"Game {gid} ({game_date}): {ht} vs {at}")
    print(f"  BS players: {len(bs_players)} | OOF on this date: {len(oof_day)}")
    print(f"  Home: {n_home} total, {n_home_oof} in OOF | Away: {n_away} total, {n_away_oof} in OOF")
    print(f"  Actual: home={home_actual} away={away_actual}")
    print(f"  OOF sum (overlap): home={home_oof_sum:.1f} away={away_oof_sum:.1f}")
    print(f"  Missing pts (home): {home_actual - home_oof_sum:.1f} ({n_home-n_home_oof} missing players)")
    print()
