"""etl_snapshots_to_lines.py — R9 C4 (Real-Line Join Repair).

Convert PrizePicks scraper snapshots into the canonical
`data/lines/<YYYY-MM-DD>_pp.csv` schema expected by
`src/betting/clv.find_closing_line`.

Source: `scripts/validation/real_lines_check/snapshots/prizepicks_<date>_<hhmm>.csv`
  cols: player, stat, stat_name, line, team, opp, start_time, book [, odds_type]

Target: `data/lines/<date>_pp.csv`
  cols: captured_at, book, game_id, player_id, player_name, stat, line,
        over_price, under_price, start_time

Notes
-----
- `captured_at` is derived from the snapshot filename (`YYYY-MM-DD_HHMM`).
- Combo stats (pra, pr, pa, ra) are dropped — the ledger never bets them.
- PrizePicks is no-vig pick'em; we synthesize standard 2-pick payout juice
  (-119 / -119) so `find_closing_line` can return an odds value.
- Idempotent: rewrites each output file from a full scan; dedups on
  (captured_at, player_name, stat, line).
"""
from __future__ import annotations

import csv
import glob
import os
import re
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(
    PROJECT_DIR, "scripts", "validation", "real_lines_check", "snapshots"
)
OUT_DIR = os.path.join(PROJECT_DIR, "data", "lines")

# PP stat-code -> ledger token. Combo stats dropped.
_STAT_MAP = {
    "pts":  "pts",
    "reb":  "reb",
    "ast":  "ast",
    "fg3m": "fg3m",
    "3pm":  "fg3m",
    "threes": "fg3m",
    "stl":  "stl",
    "blk":  "blk",
    "tov":  "tov",
}
_COMBO_STATS = {"pra", "pr", "pa", "ra", "sb", "fg3a"}

_OUT_COLS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]

_FNAME_RE = re.compile(r"prizepicks_(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})\.csv$")


def _captured_at_from_filename(path: str) -> str | None:
    m = _FNAME_RE.search(os.path.basename(path))
    if not m:
        return None
    date_s, hh, mm = m.group(1), m.group(2), m.group(3)
    return f"{date_s}T{hh}:{mm}:00"


def _normalize_stat(s: str) -> str | None:
    k = (s or "").lower().strip()
    if k in _COMBO_STATS:
        return None
    return _STAT_MAP.get(k)


def run(snapshot_dir: str = SNAPSHOT_DIR, out_dir: str = OUT_DIR) -> Dict[str, int]:
    os.makedirs(out_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(snapshot_dir, "prizepicks_*.csv")))
    # Group rows by output-date so we write one file per date.
    by_date: Dict[str, List[Dict]] = defaultdict(list)
    seen: Dict[str, set] = defaultdict(set)  # per-date dedup keys

    stats = {
        "files_seen": 0,
        "files_with_bad_filename": 0,
        "rows_in": 0,
        "rows_combo_dropped": 0,
        "rows_unknown_stat": 0,
        "rows_emitted": 0,
        "rows_dedup_skipped": 0,
    }

    for path in files:
        stats["files_seen"] += 1
        captured_at = _captured_at_from_filename(path)
        if captured_at is None:
            stats["files_with_bad_filename"] += 1
            continue
        out_date = captured_at[:10]

        try:
            with open(path, encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for r in reader:
                    stats["rows_in"] += 1
                    raw_stat = (r.get("stat") or "").lower().strip()
                    if raw_stat in _COMBO_STATS:
                        stats["rows_combo_dropped"] += 1
                        continue
                    norm = _normalize_stat(raw_stat)
                    if norm is None:
                        stats["rows_unknown_stat"] += 1
                        continue
                    try:
                        line_val = float(r.get("line", ""))
                    except (TypeError, ValueError):
                        continue
                    player = (r.get("player") or "").strip()
                    if not player:
                        continue
                    key = (captured_at, player.lower(), norm, line_val)
                    if key in seen[out_date]:
                        stats["rows_dedup_skipped"] += 1
                        continue
                    seen[out_date].add(key)
                    by_date[out_date].append({
                        "captured_at": captured_at,
                        "book":        "pp",
                        "game_id":     "",
                        "player_id":   "",
                        "player_name": player,
                        "stat":        norm,
                        "line":        f"{line_val:g}",
                        "over_price":  "-119",
                        "under_price": "-119",
                        "start_time":  (r.get("start_time") or "").strip(),
                    })
                    stats["rows_emitted"] += 1
        except (OSError, csv.Error) as exc:
            print(f"[etl] warn: cannot read {path}: {exc}", file=sys.stderr)
            continue

    # Write one canonical file per date (overwrite, full scan = idempotent).
    written = []
    for date_s, rows in sorted(by_date.items()):
        out_path = os.path.join(out_dir, f"{date_s}_pp.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=_OUT_COLS, extrasaction="ignore")
            w.writeheader()
            for row in rows:
                w.writerow(row)
        written.append((out_path, len(rows)))

    stats["files_written"] = len(written)
    return {"stats": stats, "written": written}


if __name__ == "__main__":
    import json
    result = run()
    print(json.dumps(result["stats"], indent=2))
    for path, n in result["written"]:
        print(f"  {path}: {n} rows")
