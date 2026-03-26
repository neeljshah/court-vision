"""
seed_postgres.py — Bulk-load existing shot_log.csv and tracking_data.csv files into
PostgreSQL.

Reads all data/tracking/<game_id>/ directories and inserts rows into the `shots` and
`tracking_frames` tables.  Skips rows that already exist (ON CONFLICT DO NOTHING).

Requires DATABASE_URL to be set (e.g. via .env or environment):
    export DATABASE_URL="postgresql://localhost/nba_ai"

Usage:
    python scripts/seed_postgres.py [--game GAME_ID ...] [--shots-only] [--tracking-only]
"""

import argparse
import csv
import os
import sys
from typing import List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load .env from project root if present (before importing db)
_ROOT = os.path.join(os.path.dirname(__file__), "..")
_ENV_FILE = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

DATA_DIR = os.path.join(_ROOT, "data", "tracking")

sys.path.insert(0, _ROOT)
from src.data.db import get_connection, execute_batch, is_postgres  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    try:
        v = float(val)
        return None if (v != v) else v   # NaN → None
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> Optional[int]:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _safe_bool(val) -> Optional[bool]:
    if val in (None, "", "None", "nan"):
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("1", "true", "yes"):
        return True
    if s in ("0", "false", "no"):
        return False
    return None


# ── shot_log seeding ──────────────────────────────────────────────────────────

_SHOT_INSERT = """
    INSERT INTO shots
        (game_id, tracker_player_id, shot_x, shot_y, court_zone,
         defender_distance, team_spacing, made, period)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT DO NOTHING
"""


def _seed_shots(conn, game_id: str, shot_csv: str) -> int:
    if not os.path.exists(shot_csv):
        return 0
    rows: List[tuple] = []
    with open(shot_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dd = _safe_float(r.get("defender_distance"))
            if dd == 200.0:          # skip sentinel rows not yet backfilled
                dd = None
            rows.append((
                game_id,
                _safe_int(r.get("player_id")),
                _safe_float(r.get("x_position")),
                _safe_float(r.get("y_position")),
                r.get("court_zone") or None,
                dd,
                _safe_float(r.get("team_spacing")),
                _safe_bool(r.get("made")),
                _safe_int(r.get("period")),
            ))
    if not rows:
        return 0
    with conn.cursor() as cur:
        execute_batch(cur, _SHOT_INSERT, rows)
    conn.commit()
    return len(rows)


# ── tracking_frames seeding ───────────────────────────────────────────────────

_TRACKING_INSERT = """
    INSERT INTO tracking_frames
        (game_id, frame_number, timestamp_sec, tracker_player_id,
         x_pos, y_pos, speed, acceleration, ball_possession,
         event, confidence, team_spacing, paint_count_own, paint_count_opp)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT DO NOTHING
"""


def _seed_tracking(conn, game_id: str, tracking_csv: str, max_rows: int = 0) -> int:
    """Seed tracking_data.csv rows.  max_rows=0 means no limit (loads all)."""
    if not os.path.exists(tracking_csv):
        return 0
    rows: List[tuple] = []
    with open(tracking_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((
                game_id,
                _safe_int(r.get("frame")),
                _safe_float(r.get("timestamp")),
                _safe_int(r.get("player_id")),
                _safe_float(r.get("x_position")),
                _safe_float(r.get("y_position")),
                _safe_float(r.get("velocity")),
                _safe_float(r.get("acceleration")),
                _safe_bool(r.get("ball_possession")),
                r.get("event") or None,
                _safe_float(r.get("confidence")),
                _safe_float(r.get("team_spacing")),
                _safe_int(r.get("paint_count_own")),
                _safe_int(r.get("paint_count_opp")),
            ))
            if max_rows and len(rows) >= max_rows:
                break
    if not rows:
        return 0
    # Insert in batches of 2000 to avoid huge transactions
    batch_size = 2000
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        with conn.cursor() as cur:
            execute_batch(cur, _TRACKING_INSERT, batch)
        conn.commit()
        total += len(batch)
    return total


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Seed PostgreSQL from existing CSV files")
    ap.add_argument("--game", dest="games", nargs="*",
                    help="Game IDs (default: all dirs under data/tracking/)")
    ap.add_argument("--shots-only",    action="store_true")
    ap.add_argument("--tracking-only", action="store_true")
    ap.add_argument("--max-tracking-rows", type=int, default=0,
                    help="Limit tracking rows per game (0 = no limit)")
    args = ap.parse_args()

    conn = get_connection()
    backend = "PostgreSQL" if is_postgres(conn) else "SQLite"
    if not is_postgres(conn):
        print(f"WARNING: DATABASE_URL not set — seeding into SQLite ({backend})")
        print("Set DATABASE_URL=postgresql://localhost/nba_ai to target PostgreSQL.\n")

    if args.games:
        game_dirs = [os.path.join(DATA_DIR, g) for g in args.games]
    else:
        game_dirs = sorted(
            os.path.join(DATA_DIR, d)
            for d in os.listdir(DATA_DIR)
            if os.path.isdir(os.path.join(DATA_DIR, d))
        )

    if not game_dirs:
        print("No game directories found under", DATA_DIR)
        return

    print(f"Seeding {len(game_dirs)} game(s) → {backend}\n")

    total_shots = 0
    total_tracking = 0
    for d in game_dirs:
        game_id = os.path.basename(d)
        shot_csv     = os.path.join(d, "shot_log.csv")
        tracking_csv = os.path.join(d, "tracking_data.csv")

        s_count = 0
        t_count = 0

        if not args.tracking_only:
            try:
                s_count = _seed_shots(conn, game_id, shot_csv)
            except Exception as e:
                print(f"  {game_id} shots ERROR: {e}")

        if not args.shots_only:
            try:
                t_count = _seed_tracking(conn, game_id, tracking_csv,
                                         max_rows=args.max_tracking_rows)
            except Exception as e:
                print(f"  {game_id} tracking ERROR: {e}")

        if s_count or t_count:
            print(f"  {game_id}: {s_count} shots, {t_count} tracking rows")

    conn.close()
    print(f"\nTotal seeded: {total_shots} shots, {total_tracking} tracking rows")


if __name__ == "__main__":
    main()
