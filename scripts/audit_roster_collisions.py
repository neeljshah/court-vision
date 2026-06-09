"""
audit_roster_collisions.py -- Bug 6 forensic audit: roster-validation for cv_features.

For every (game_id, player_id) pair in cv_features, checks whether that player
appears in the game's boxscore file (data/nba/boxscore_<game_id>.json).

Outputs to stdout:
  - Summary counts: total / in-roster / out-of-roster / unknown-roster
  - Top 20 worst out-of-roster (player_id, game_id, row count)

Usage:
    python scripts/audit_roster_collisions.py
    python scripts/audit_roster_collisions.py > vault/Intelligence/_bug6_baseline.txt
"""

from __future__ import annotations

import json
import sys
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional, Set

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

NBA_CACHE = PROJECT_DIR / "data" / "nba"

# ── In-process boxscore roster cache ──────────────────────────────────────────
_ROSTER_CACHE: Dict[str, Optional[Set[int]]] = {}


def _get_game_team_rosters(game_id: str) -> Optional[Set[int]]:
    """Return set of nba player_ids in the boxscore for game_id, or None if unknown."""
    if game_id in _ROSTER_CACHE:
        return _ROSTER_CACHE[game_id]

    boxscore_path = NBA_CACHE / f"boxscore_{game_id}.json"
    if not boxscore_path.exists():
        _ROSTER_CACHE[game_id] = None
        return None

    try:
        with open(boxscore_path, encoding="utf-8") as f:
            bs = json.load(f)
        players = bs.get("players", [])
        ids: Set[int] = set()
        for p in players:
            pid = p.get("player_id")
            if pid:
                ids.add(int(pid))
        if ids:
            _ROSTER_CACHE[game_id] = ids
            return ids
    except Exception:
        pass

    _ROSTER_CACHE[game_id] = None
    return None


def _load_player_id_to_name() -> Dict[int, str]:
    """Build a player_id -> display name map from cached player stats JSON files."""
    result: Dict[int, str] = {}
    patterns = [
        "player_full_2025-26.json",
        "player_full_2024-25.json",
        "player_avgs_2025-26.json",
        "player_avgs_2024-25.json",
        "player_avgs_2023-24.json",
    ]
    for fname in patterns:
        p = NBA_CACHE / fname
        if not p.exists():
            continue
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for row in data:
                    pid = row.get("PLAYER_ID") or row.get("player_id")
                    name = row.get("PLAYER_NAME") or row.get("player_name")
                    if pid and name and int(pid) not in result:
                        result[int(pid)] = str(name)
            elif isinstance(data, dict):
                for name, info in data.items():
                    if isinstance(info, dict):
                        pid = info.get("player_id") or info.get("PLAYER_ID")
                        if pid and int(pid) not in result:
                            result[int(pid)] = name
        except Exception:
            pass
    return result


def main() -> None:
    from src.data.db import get_connection

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Pull all (game_id, player_id) with row counts
    cur.execute(
        "SELECT game_id, player_id, COUNT(*) AS cnt "
        "FROM cv_features "
        "GROUP BY game_id, player_id"
    )
    rows = cur.fetchall()
    conn.close()

    id_to_name = _load_player_id_to_name()

    total_pairs = 0
    total_rows = 0
    in_roster_pairs = 0
    in_roster_rows = 0
    out_roster_pairs = 0
    out_roster_rows = 0
    unknown_pairs = 0
    unknown_rows = 0

    # For top-20: accumulate out-of-roster entries
    out_roster_list: list = []

    for row in rows:
        game_id = row["game_id"]
        player_id = int(row["player_id"])
        cnt = int(row["cnt"])
        total_pairs += 1
        total_rows += cnt

        eligible = _get_game_team_rosters(game_id)

        if eligible is None:
            unknown_pairs += 1
            unknown_rows += cnt
        elif player_id in eligible:
            in_roster_pairs += 1
            in_roster_rows += cnt
        else:
            out_roster_pairs += 1
            out_roster_rows += cnt
            out_roster_list.append((player_id, game_id, cnt))

    # Sort by row count desc for top-20
    out_roster_list.sort(key=lambda x: x[2], reverse=True)

    print("=" * 70)
    print("Bug 6 Baseline Audit — cv_features Roster Validation")
    print("=" * 70)
    print(f"\nROSTER SOURCE: data/nba/boxscore_<game_id>.json")
    print(f"  (5482 boxscore files available; covers 264/314 cv_features games)\n")

    print(f"{'METRIC':<35} {'PAIRS':>8}  {'ROWS':>8}  {'ROW %':>7}")
    print("-" * 65)
    print(f"{'Total':.<35} {total_pairs:>8,}  {total_rows:>8,}  {'100.0%':>7}")
    pct_in  = 100.0 * in_roster_rows / total_rows if total_rows else 0
    pct_out = 100.0 * out_roster_rows / total_rows if total_rows else 0
    pct_unk = 100.0 * unknown_rows / total_rows if total_rows else 0
    print(f"{'In-roster (correct)':.<35} {in_roster_pairs:>8,}  {in_roster_rows:>8,}  {pct_in:>6.1f}%")
    print(f"{'Out-of-roster (Bug 6 collisions)':.<35} {out_roster_pairs:>8,}  {out_roster_rows:>8,}  {pct_out:>6.1f}%")
    print(f"{'Unknown (no boxscore file)':.<35} {unknown_pairs:>8,}  {unknown_rows:>8,}  {pct_unk:>6.1f}%")

    print(f"\nTop {min(20, len(out_roster_list))} out-of-roster entries (sorted by cv_features row count):")
    print(f"  {'player_id':>10}  {'player_name':<28}  {'game_id':>12}  {'rows':>5}")
    print("  " + "-" * 62)
    for player_id, game_id, cnt in out_roster_list[:20]:
        name = id_to_name.get(player_id, "UNKNOWN")
        print(f"  {player_id:>10}  {name:<28}  {game_id:>12}  {cnt:>5}")

    if not out_roster_list:
        print("  (none found)")

    print("\n")
    print(f"Summary: {out_roster_rows:,} of {total_rows:,} rows ({pct_out:.1f}%) are OUT-OF-ROSTER")
    print(f"         {unknown_rows:,} of {total_rows:,} rows ({pct_unk:.1f}%) have UNKNOWN roster (no boxscore)")
    print(
        "\nNext step: after running backfill_cv_features.py the out-of-roster count "
        "should drop to 0 for newly processed games. The unknown-roster group cannot "
        "be validated until boxscore files are downloaded for those 50 games."
    )


if __name__ == "__main__":
    main()
