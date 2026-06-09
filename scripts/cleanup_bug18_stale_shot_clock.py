"""
Bug 18 stale-row cleanup (2026-05-28).

Bug 18 fix added a NaN guard so new backfills don't write avg_shot_clock_at_shot=0.0
when n_shots>0. But old rows from before the fix persist. This script DELETES
those stale rows (the cv_features cell, not the whole player-game row).
"""
import sys
sys.path.insert(0, '.')

from src.data.db import get_connection

conn = get_connection()
cur = conn.cursor()

# Find (game_id, player_id) pairs where shot_clock=0 AND n_shots>0
cur.execute("""
    SELECT t1.game_id, t1.player_id
    FROM cv_features t1
    JOIN cv_features t2
        ON t1.game_id = t2.game_id AND t1.player_id = t2.player_id
    WHERE t1.feature_name = 'avg_shot_clock_at_shot' AND t1.feature_value = 0.0
      AND t2.feature_name = 'n_shots_tracked'        AND t2.feature_value > 0
""")
pairs = cur.fetchall()
print(f"Stale shot_clock=0 pairs (n_shots>0): {len(pairs)}")

if not pairs:
    print("No stale rows to delete.")
else:
    for r in pairs[:5]:
        gid = r['game_id'] if hasattr(r, 'keys') else r[0]
        pid = r['player_id'] if hasattr(r, 'keys') else r[1]
        print(f"  game={gid} pid={pid}")

    deleted = 0
    for r in pairs:
        gid = r['game_id'] if hasattr(r, 'keys') else r[0]
        pid = r['player_id'] if hasattr(r, 'keys') else r[1]
        cur.execute("""
            DELETE FROM cv_features
            WHERE game_id=? AND player_id=? AND feature_name='avg_shot_clock_at_shot'
        """, (gid, pid))
        deleted += cur.rowcount
    conn.commit()
    print(f"\nDeleted {deleted} stale avg_shot_clock_at_shot rows.")

cur.execute("SELECT COUNT(*) FROM cv_features")
print(f"Remaining cv_features rows: {cur.fetchone()[0]}")

conn.close()
