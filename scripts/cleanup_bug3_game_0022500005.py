"""
cleanup_bug3_game_0022500005.py — Bug 3 cleanup for game 0022500005.

STATUS (2026-05-28): The original artifact rows (paint_dwell_pct=0.915/0.902 for players
1642272 (Jared McCain) and 1629614 (Andrew Nembhard)) were ALREADY overwritten by the
2026-05-28 backfill (INSERT OR REPLACE behavior introduced in the Bug 2 fix).

The current cv_features DB for game 0022500005 has 3 rows for players 1629614, 1641716,
1643007 with paint_dwell_pct values of 0.013, 0.0, 0.019 — all within normal range.
Player 1642272 (McCain) no longer has any rows for this game.

THIS SCRIPT is therefore a VERIFICATION tool, not a deletion tool.
It confirms the artifact is gone and optionally deletes residual low-quality rows
(only if --force-delete is passed AND the investigation confirms they are also bad).

Run modes:
    python scripts/cleanup_bug3_game_0022500005.py          # verify only (default)
    python scripts/cleanup_bug3_game_0022500005.py --check  # check anomaly_log state
    python scripts/cleanup_bug3_game_0022500005.py --force-delete  # delete all 3 current rows

Why delete the current 3 rows (optional)?
  - Game 0022500005's tracking data only resolved to 'green#?' and 'white#?' players.
  - The 3 player IDs in the current DB (1629614, 1641716, 1643007) were assigned via PBP
    name resolution but have a high proportion of zero features (1629614 has 22/28 = 0.0).
  - With --force-delete, all rows for this game are removed so it does not pollute
    player-baseline computations for Nembhard (1629614), Jarace Walker (1641716),
    and ID:1643007.
"""

import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "nba_ai.db"
GAME_ID = "0022500005"

# Players confirmed to have had the artifact (from anomaly_log):
ARTIFACT_PLAYERS = {
    1642272: ("Jared McCain", 0.915),    # paint_dwell z=68.3 — no longer in DB
    1629614: ("Andrew Nembhard", 0.902), # paint_dwell z=67.4 — now has 0.013 (replaced)
}


def verify(conn: sqlite3.Connection) -> None:
    """Print current state of game 0022500005 in cv_features."""
    rows = conn.execute(
        "SELECT player_id, feature_name, feature_value FROM cv_features "
        "WHERE game_id = ? ORDER BY player_id, feature_name",
        (GAME_ID,),
    ).fetchall()

    print(f"\n=== Current cv_features for game {GAME_ID} ===")
    if not rows:
        print("  NO ROWS — game already cleaned.")
        return

    current_players = set(r[0] for r in rows)
    print(f"  Tracked players ({len(current_players)}): {sorted(current_players)}")
    print()

    # Check for artifact players
    for pid, (name, old_val) in ARTIFACT_PLAYERS.items():
        if pid in current_players:
            paint_row = conn.execute(
                "SELECT feature_value FROM cv_features "
                "WHERE game_id=? AND player_id=? AND feature_name='paint_dwell_pct'",
                (GAME_ID, pid),
            ).fetchone()
            current_paint = paint_row[0] if paint_row else None
            status = "ARTIFACT STILL PRESENT" if (current_paint and current_paint > 0.5) else "OK (replaced)"
            print(f"  {name} (id={pid}): paint_dwell={current_paint}  old_artifact={old_val}  [{status}]")
        else:
            print(f"  {name} (id={pid}): NOT IN DB  (artifact row was removed by backfill)")

    # Show paint_dwell for all current rows
    print()
    print("  paint_dwell_pct by player_id:")
    for pid in sorted(current_players):
        r = conn.execute(
            "SELECT feature_value FROM cv_features "
            "WHERE game_id=? AND player_id=? AND feature_name='paint_dwell_pct'",
            (GAME_ID, pid),
        ).fetchone()
        val = r[0] if r else None
        anomaly_flag = " *** ARTIFACT" if val and val > 0.5 else ""
        print(f"    player_id={pid}: {val}{anomaly_flag}")

    print()
    # Count non-zero features per player
    print("  Non-zero feature count per player:")
    for pid in sorted(current_players):
        nonzero = conn.execute(
            "SELECT COUNT(*) FROM cv_features "
            "WHERE game_id=? AND player_id=? AND feature_value != 0",
            (GAME_ID, pid),
        ).fetchone()[0]
        total = conn.execute(
            "SELECT COUNT(*) FROM cv_features WHERE game_id=? AND player_id=?",
            (GAME_ID, pid),
        ).fetchone()[0]
        print(f"    player_id={pid}: {nonzero}/{total} non-zero")


def force_delete(conn: sqlite3.Connection) -> None:
    """Delete ALL cv_features rows for game 0022500005."""
    count_before = conn.execute(
        "SELECT COUNT(*) FROM cv_features WHERE game_id=?", (GAME_ID,)
    ).fetchone()[0]

    if count_before == 0:
        print(f"Game {GAME_ID} already has 0 rows — nothing to delete.")
        return

    print(f"Deleting {count_before} rows for game {GAME_ID} ...")
    conn.execute("DELETE FROM cv_features WHERE game_id=?", (GAME_ID,))
    conn.commit()

    count_after = conn.execute(
        "SELECT COUNT(*) FROM cv_features WHERE game_id=?", (GAME_ID,)
    ).fetchone()[0]
    print(f"Deleted {count_before - count_after} rows. Remaining: {count_after}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bug 3 cleanup verifier for game 0022500005.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print anomaly_log state for this game (requires anomaly_log.parquet).",
    )
    parser.add_argument(
        "--force-delete",
        action="store_true",
        dest="force_delete",
        help="DELETE all rows for game 0022500005 from cv_features (irreversible).",
    )
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)

    print("=== Bug 3 — Game 0022500005 Paint-Cluster Artifact Cleanup ===")
    print()
    print("Investigation summary:")
    print("  OLD state (pre-2026-05-28 backfill):")
    print("    - Jared McCain (1642272): paint_dwell_pct=0.915, z=68.3 — ARTIFACT")
    print("    - Andrew Nembhard (1629614): paint_dwell_pct=0.902, z=67.4 — ARTIFACT")
    print("    - 3/3 tracked players anomalous (100%) => confirmed game-level artifact")
    print()
    print("  ROOT CAUSE: Homography/zone-classification failure. Tracking data shows")
    print("    only 'green#?' and 'white#?' player names (jersey ID resolution failed")
    print("    entirely). This corrupted court_zone assignments sent most frames to 'paint'.")
    print()
    print("  CURRENT state (post-2026-05-28 backfill):")
    print("    - INSERT OR REPLACE overwrote artifact rows during Bug 2 fix backfill.")
    print("    - McCain (1642272) was removed (ghost slot eliminated).")
    print("    - Nembhard (1629614) now shows paint_dwell=0.013 (within normal range).")

    if args.check:
        try:
            import pandas as pd
            anom_path = args.db.parent / "intelligence" / "anomaly_log.parquet"
            df_anom = pd.read_parquet(anom_path)
            g5 = df_anom[df_anom["game_id"] == GAME_ID]
            print(f"\n  anomaly_log entries for {GAME_ID}: {len(g5)}")
            print(g5[["player_id", "player_name", "max_abs_z", "n_anomalous_features"]].to_string())
        except Exception as e:
            print(f"\n  Could not load anomaly_log: {e}")

    verify(conn)

    if args.force_delete:
        print("\nWARNING: --force-delete will permanently remove all cv_features rows for this game.")
        confirm = input("Type 'yes' to proceed: ").strip().lower()
        if confirm == "yes":
            force_delete(conn)
        else:
            print("Aborted.")
    else:
        # Check if artifact rows still exist
        artifact_pids_in_db = []
        for pid in ARTIFACT_PLAYERS:
            r = conn.execute(
                "SELECT feature_value FROM cv_features "
                "WHERE game_id=? AND player_id=? AND feature_name='paint_dwell_pct'",
                (GAME_ID, pid),
            ).fetchone()
            if r and r[0] > 0.5:
                artifact_pids_in_db.append(pid)

        if artifact_pids_in_db:
            print(f"\nACTION REQUIRED: {len(artifact_pids_in_db)} artifact rows still present.")
            print("  Run with --force-delete to remove them.")
        else:
            print("\nCLEAN: No artifact rows detected. Bug 3 artifact is resolved in current DB.")
            print("  No deletion needed. The anomaly_log captures historical state only.")

    conn.close()


if __name__ == "__main__":
    main()
