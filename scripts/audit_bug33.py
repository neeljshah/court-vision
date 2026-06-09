"""Bug 33 audit: surface all nba_ids with near-zero CV signal across games."""
import sys
sys.path.insert(0, '.')
from src.data.db import get_connection

conn = get_connection()
cur = conn.cursor()

# Star check
for pid, name in [(201939, 'Curry'), (203999, 'Jokic'), (201942, 'DeRozan'), (2544, 'LeBron')]:
    cur.execute("""
        SELECT game_id, COUNT(*) as n_feats,
               SUM(CASE WHEN feature_value != 0 THEN 1 ELSE 0 END) as n_nonzero
        FROM cv_features
        WHERE player_id = ?
        GROUP BY game_id
    """, (pid,))
    rows = cur.fetchall()
    print(f"\n{name} ({pid}):")
    for r in rows:
        gid = r['game_id'] if hasattr(r, 'keys') else r[0]
        nf = r['n_feats'] if hasattr(r, 'keys') else r[1]
        nz = r['n_nonzero'] if hasattr(r, 'keys') else r[2]
        print(f"  {gid}  feats={nf} nonzero={nz}")

# Bug 33 strict audit: players with ≥3 games and >=80% zero features
print("\n\n=== BUG 33 STRICT AUDIT (n_games>=3, >=80% zero) ===")
cur.execute("""
    SELECT player_id,
           COUNT(DISTINCT game_id) as n_games,
           SUM(CASE WHEN feature_value = 0 THEN 1.0 ELSE 0.0 END) / COUNT(*) as zero_frac,
           SUM(CASE WHEN feature_value != 0 THEN 1 ELSE 0 END) as total_nonzero
    FROM cv_features
    GROUP BY player_id
    HAVING n_games >= 3 AND zero_frac >= 0.80
    ORDER BY zero_frac DESC, n_games DESC
""")
rows = cur.fetchall()
print(f"Total: {len(rows)}")
for r in rows[:30]:
    pid = r['player_id'] if hasattr(r, 'keys') else r[0]
    ng = r['n_games'] if hasattr(r, 'keys') else r[1]
    zf = r['zero_frac'] if hasattr(r, 'keys') else r[2]
    tnz = r['total_nonzero'] if hasattr(r, 'keys') else r[3]
    print(f"  pid={pid}  n_games={ng}  zero_frac={zf:.3f}  total_nonzero={tnz}")

# Broader audit
print("\n\n=== BUG 33 BROADER (n_games>=2, >=75% zero) ===")
cur.execute("""
    SELECT COUNT(*) FROM (
        SELECT player_id, COUNT(DISTINCT game_id) as n_games,
               SUM(CASE WHEN feature_value = 0 THEN 1.0 ELSE 0.0 END) / COUNT(*) as zero_frac
        FROM cv_features
        GROUP BY player_id
        HAVING n_games >= 2 AND zero_frac >= 0.75
    )
""")
print(f"Total broader-affected: {cur.fetchone()[0]}")

conn.close()
