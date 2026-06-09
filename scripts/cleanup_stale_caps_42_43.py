"""
Bug 31 / 42 / 43 stale row cleanup (2026-05-29).

Code fixes for Bug 31 (preshot_velocity_peak cap) and Bug 37/38 (shot_distance,
defender_distance, spacing caps) are now in tracking_feature_extractor.py — they
prevent NEW bad values. But OLD cv_features rows from prior backfills still carry:
- preshot_velocity_peak == 40.0 (cap sentinel; should be NaN/missing)
- avg_shot_distance > 32 ft (Bug 42; impossible NBA shot distance)
- avg_defender_distance > 50 ft (Bug 43; homography failure leaked pixel units)
- avg_spacing > 60 ft (Bug 37; rescale missed)

DELETE these specific feature cells (not the whole row), preserving the player-game
row but removing the contaminated values.
"""
import sys
sys.path.insert(0, '.')

from src.data.db import get_connection

conn = get_connection()
cur = conn.cursor()

# Define impossible thresholds per feature
CAPS = [
    ('preshot_velocity_peak', '== 40.0'),         # Bug 31 cap sentinel
    ('avg_shot_distance', '> 32.0'),              # Bug 42 court geometry violation
    ('avg_defender_distance', '> 50.0'),          # Bug 43 homography-fail pixel residue
    ('avg_spacing', '> 60.0'),                    # Bug 37 court width + slack
]

total_deleted = 0
for feature_name, condition in CAPS:
    cur.execute(f"""
        SELECT COUNT(*) FROM cv_features
        WHERE feature_name = ? AND feature_value {condition}
    """, (feature_name,))
    n_stale = cur.fetchone()[0]
    print(f"{feature_name} {condition}: {n_stale} stale rows")

    if n_stale:
        cur.execute(f"""
            DELETE FROM cv_features
            WHERE feature_name = ? AND feature_value {condition}
        """, (feature_name,))
        total_deleted += cur.rowcount

conn.commit()
print(f"\nTotal stale feature-cells deleted: {total_deleted}")

cur.execute("SELECT COUNT(*) FROM cv_features")
print(f"Remaining cv_features rows: {cur.fetchone()[0]}")

conn.close()
