"""
Bug 6 cleanup runner (2026-05-28):
After Wave 2 backfill with roster guard, OLD out-of-roster rows persist in cv_features
because INSERT OR REPLACE only touches keys the new run re-registered. Rejected rows
were never written by the new code, so they survive from before.

This script:
1. Re-runs the roster audit (uses src.data.db + boxscore JSONs)
2. DELETES all (game_id, player_id) pairs that are out-of-roster per boxscore
3. Preserves UNKNOWN-roster rows (no boxscore available) and IN-roster rows

Run once on RunPod after Wave 2 backfill completes.
"""
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, '.')

from src.data.db import get_connection

ROOT = Path('.').resolve()
BOXSCORE_DIR = ROOT / 'data' / 'nba'


def get_boxscore_pids(game_id: str) -> set:
    p = BOXSCORE_DIR / f'boxscore_{game_id}.json'
    if not p.exists():
        return set()
    try:
        with open(p, encoding='utf-8') as f:
            j = json.load(f)
        pids = set()
        # Format 1: top-level players list
        for k in ('players', 'player_stats', 'box_score_players'):
            if k in j and isinstance(j[k], list):
                for pl in j[k]:
                    pid = pl.get('player_id') or pl.get('personId')
                    if pid:
                        pids.add(int(pid))
        # Format 2: nested per-team
        for k in ('home', 'away', 'home_team', 'away_team'):
            tm = j.get(k, {})
            if isinstance(tm, dict):
                for pl in (tm.get('players', []) or tm.get('player_stats', []) or []):
                    pid = pl.get('player_id') or pl.get('personId')
                    if pid:
                        pids.add(int(pid))
        return pids
    except Exception:
        return set()


conn = get_connection()
cur = conn.cursor()

# Get all (game_id, player_id) pairs
cur.execute("SELECT DISTINCT game_id, player_id FROM cv_features")
pairs = cur.fetchall()
print(f"Total (game, player) pairs: {len(pairs)}")

stale_pairs = []
unknown_games = 0
known_games_seen = set()
for r in pairs:
    gid = r[0] if hasattr(r, '__getitem__') else r['game_id']
    pid = r[1] if hasattr(r, '__getitem__') else r['player_id']
    roster = get_boxscore_pids(gid)
    if not roster:
        unknown_games += 1
        continue
    known_games_seen.add(gid)
    if int(pid) not in roster:
        stale_pairs.append((gid, int(pid)))

print(f"Known-roster pairs: {len(pairs) - unknown_games}")
print(f"Stale (out-of-roster): {len(stale_pairs)}")
print(f"Games with known rosters: {len(known_games_seen)}")

if not stale_pairs:
    print("\nNo stale pairs to delete.")
else:
    print(f"\nFirst 10 stale pairs:")
    for gid, pid in stale_pairs[:10]:
        print(f"  game={gid} pid={pid}")

    # DELETE them
    deleted = 0
    for gid, pid in stale_pairs:
        cur.execute(
            "DELETE FROM cv_features WHERE game_id=? AND player_id=?",
            (gid, pid),
        )
        deleted += cur.rowcount
    conn.commit()
    print(f"\nDeleted {deleted} cv_features rows ({len(stale_pairs)} player-game pairs).")

cur.execute("SELECT COUNT(*) FROM cv_features")
print(f"Remaining cv_features rows: {cur.fetchone()[0]}")

conn.close()
