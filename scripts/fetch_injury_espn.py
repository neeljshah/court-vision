"""fetch_injury_espn.py — ESPN injury source written in cycle-43 JSON schema.

Cycle 43's fetch_injury_report.py scrapes the official NBA injury report
PDF. From sandboxed / non-residential IPs that PDF endpoint 403s. ESPN's
public injury API (no auth, very rarely blocked) is the obvious second
source — and src/data/injury_monitor.py already wraps it.

This script wraps `injury_monitor.get_all_injuries()` and writes the
result in the SAME schema cycle 43 produces, so cycle 53's
src/data/injuries.load_unavailable_players() picks it up unchanged:

    {
        "date":       "YYYY-MM-DD",
        "source_pdf": "ESPN public injury API",
        "fetched_at": "...",
        "players":    [{"team": "...", "name": "...", "status": "...",
                        "reason": "..."}, ...]
    }

ESPN status taxonomy -> canonical (matches src/data/injuries.UNAVAILABLE_STATUSES):
  "Out" / "OUT"             -> "OUT"
  "Doubtful"                -> "DOUBTFUL"
  "Questionable"            -> "QUESTIONABLE"
  "Probable"                -> "PROBABLE"
  "Day-To-Day"              -> "QUESTIONABLE"   (no day-to-day in NBA taxonomy)
  "Suspended" / "NWT"       -> "NOT WITH TEAM"
  anything else             -> uppercased as-is (lookup_status returns None)

Run:
    python scripts/fetch_injury_espn.py                 # today
    python scripts/fetch_injury_espn.py --date 2026-05-24
    python scripts/fetch_injury_espn.py --force         # bypass cache TTL
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, date as _date

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data.injury_monitor import get_all_injuries, refresh  # noqa: E402


# ESPN status -> cycle-43 / src/data/injuries canonical status
_STATUS_MAP = {
    "out":          "OUT",
    "doubtful":     "DOUBTFUL",
    "questionable": "QUESTIONABLE",
    "probable":     "PROBABLE",
    "day-to-day":   "QUESTIONABLE",
    "dtd":          "QUESTIONABLE",
    "suspended":    "NOT WITH TEAM",
    "nwt":          "NOT WITH TEAM",
    "not with team": "NOT WITH TEAM",
    "active":       "AVAILABLE",
    "available":    "AVAILABLE",
}


def _normalize_status(raw: str) -> str:
    """Map an ESPN status string into the canonical taxonomy."""
    key = (raw or "").strip().lower()
    return _STATUS_MAP.get(key, raw.upper().strip() if raw else "")


def to_cycle43_schema(espn_rows: list, date_str: str) -> dict:
    """Convert ESPN injury rows -> cycle-43 JSON payload."""
    players = []
    for r in espn_rows:
        name = (r.get("player_name") or "").strip()
        if not name:
            continue
        # Prefer short_comment as reason; fall back to injury_type.
        reason = (r.get("short_comment") or r.get("injury_type") or "").strip()
        players.append({
            "team":   r.get("team_abbrev", ""),
            "name":   name,
            "status": _normalize_status(r.get("status", "")),
            "reason": reason,
        })
    return {
        "date":       date_str,
        "source_pdf": "ESPN public injury API",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "players":    players,
    }


def write_payload(payload: dict, out_path: str) -> int:
    """Write payload as JSON. Returns number of player entries."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return len(payload.get("players", []))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None,
                    help="Stamp the JSON with this date (default: today). "
                         "Doesn't change which players ESPN returns — that's "
                         "always 'current'.")
    ap.add_argument("--force", action="store_true",
                    help="Bypass injury_monitor's TTL cache, force a fresh fetch.")
    ap.add_argument("--out", default=None,
                    help="Output path (default: data/injuries_<date>.json — same as cycle 43)")
    args = ap.parse_args()

    if args.force:
        refresh(force=True)

    rows = get_all_injuries()
    if not rows:
        print("[fetch_injury_espn] ESPN returned 0 rows — endpoint down or cache empty.")
        return 1

    date_str = args.date or _date.today().isoformat()
    out = args.out or os.path.join(PROJECT_DIR, "data",
                                     f"injuries_{date_str}.json")
    payload = to_cycle43_schema(rows, date_str)
    n = write_payload(payload, out)

    # Quick status breakdown — what's actionable for compare_to_lines.
    by_status = {}
    for p in payload["players"]:
        s = p["status"]
        by_status[s] = by_status.get(s, 0) + 1
    print(f"[fetch_injury_espn] wrote {n} players -> {out}")
    print(f"  by status: " +
          "  ".join(f"{s}={c}" for s, c in sorted(by_status.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
