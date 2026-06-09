"""
Bug 36 cleanup (2026-05-28).

Find (game_id, player_id) pairs where ALL features are 0.0 (or near-all-zero) —
these are the broader-than-Bug-33 ghost rows. Delete them.

Threshold: a player-game row is "sparse-ghost" if it has <3 non-zero features
(excluding cv_archetype, which is assigned post-registration).
"""
import sys
sys.path.insert(0, '.')

from src.data.db import get_connection
from collections import defaultdict

conn = get_connection()
cur = conn.cursor()

# Build feature counts per (game_id, player_id)
cur.execute("""
    SELECT game_id, player_id, feature_name, feature_value
    FROM cv_features
    WHERE feature_name != 'cv_archetype'
""")
groups = defaultdict(list)
for r in cur.fetchall():
    gid = r['game_id'] if hasattr(r, 'keys') else r[0]
    pid = r['player_id'] if hasattr(r, 'keys') else r[1]
    fname = r['feature_name'] if hasattr(r, 'keys') else r[2]
    fval = r['feature_value'] if hasattr(r, 'keys') else r[3]
    groups[(gid, pid)].append((fname, fval))

print(f"Total (game, player) pairs: {len(groups)}")

# Find sparse-ghost pairs (<3 non-zero features)
sparse_pairs = []
for (gid, pid), feats in groups.items():
    nonzero = sum(1 for _, v in feats if v not in (None, 0, 0.0))
    if nonzero < 3:
        sparse_pairs.append((gid, pid, len(feats), nonzero))

print(f"Sparse-ghost pairs (<3 nonzero features): {len(sparse_pairs)}")

if not sparse_pairs:
    print("No sparse-ghost rows to delete.")
else:
    print("\nFirst 10:")
    for gid, pid, n, nz in sparse_pairs[:10]:
        print(f"  game={gid} pid={pid} features={n} nonzero={nz}")

    # DELETE
    deleted = 0
    for gid, pid, _, _ in sparse_pairs:
        cur.execute(
            "DELETE FROM cv_features WHERE game_id=? AND player_id=?",
            (gid, pid),
        )
        deleted += cur.rowcount
    conn.commit()
    print(f"\nDeleted {deleted} cv_features rows ({len(sparse_pairs)} player-game pairs).")

cur.execute("SELECT COUNT(*) FROM cv_features")
print(f"Remaining cv_features rows: {cur.fetchone()[0]}")

conn.close()
