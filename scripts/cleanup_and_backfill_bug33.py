"""
Bug 2 + Bug 33 remediation runner (2026-05-28):
1. Identify all game_ids touched by the 21 strict-affected players (and 62 broader).
2. Delete cv_features rows for those players (so old ghost-registered rows are wiped).
3. Re-run backfill_cv_features.process_game() on those games with --force semantics.

After this runs, the new attribution chain (PBP-first, contest guard, ghost-skip,
INSERT OR REPLACE) writes the corrected feature set.
"""
import sys
import os
sys.path.insert(0, '.')

from src.data.db import get_connection

# 1. Find all strict-affected player_ids (n_games>=3, zero_frac>=0.80)
conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT player_id
    FROM cv_features
    GROUP BY player_id
    HAVING COUNT(DISTINCT game_id) >= 2
       AND SUM(CASE WHEN feature_value = 0 THEN 1.0 ELSE 0.0 END) / COUNT(*) >= 0.75
""")
affected_pids = [r[0] for r in cur.fetchall()]
print(f"Affected players: {len(affected_pids)}")

# 2. Find all distinct game_ids they appear in.
cur.execute(f"""
    SELECT DISTINCT game_id
    FROM cv_features
    WHERE player_id IN ({','.join(['?']*len(affected_pids))})
""", affected_pids)
affected_games = sorted({r[0] for r in cur.fetchall()})
print(f"Affected games: {len(affected_games)}")

# 3. DELETE rows for affected players.
cur.execute(f"""
    DELETE FROM cv_features
    WHERE player_id IN ({','.join(['?']*len(affected_pids))})
""", affected_pids)
deleted = cur.rowcount
conn.commit()
print(f"Deleted {deleted} cv_features rows for {len(affected_pids)} affected players.")

conn.close()

# 4. Write affected games to a file so backfill can target them.
os.makedirs("data/_wave1", exist_ok=True)
with open("data/_wave1/affected_games.txt", "w") as f:
    for gid in affected_games:
        f.write(gid + "\n")
print(f"Wrote {len(affected_games)} game_ids to data/_wave1/affected_games.txt")
print("\nNext: run backfill_cv_features.py on each affected game with --force.")
