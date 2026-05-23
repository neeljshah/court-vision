"""expand_gamelogs_from_full.py — derive gamelog_<pid>_<season>.json files from
gamelog_full_<pid>_<season>.json wherever the short form is missing.

The per-game prop trainer (`src/prediction/prop_pergame.py::build_pergame_dataset`)
reads the short form. The full form has 2× the seasons cached locally — but a
schema mismatch (lowercase keys vs UPPERCASE) kept it from being picked up.

This converter is idempotent + read-only on existing short-form files. It
only writes a gamelog_<pid>_<season>.json when one isn't already there.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = Path(PROJECT_DIR) / "data" / "nba"

# Maps the columns build_pergame_dataset reads from the short form.
_BOX_KEYS_NEEDED = ("GAME_DATE", "MATCHUP", "PTS", "REB", "AST", "MIN",
                    "FG3M", "STL", "BLK", "TOV")


def _convert_row(full_row: dict) -> dict:
    """Lower-case gamelog_full row -> UPPER-case gamelog_<pid>_<season>.json row."""
    return {
        "GAME_DATE": full_row.get("game_date"),
        "MATCHUP":   full_row.get("matchup"),
        "PTS":       full_row.get("pts"),
        "REB":       full_row.get("reb"),
        "AST":       full_row.get("ast"),
        "MIN":       full_row.get("min"),
        "FG3M":      full_row.get("fg3m"),
        "STL":       full_row.get("stl"),
        "BLK":       full_row.get("blk"),
        "TOV":       full_row.get("tov"),
    }


def main() -> int:
    if not _NBA_CACHE.exists():
        print(f"NBA cache not found at {_NBA_CACHE}")
        return 1

    full_files = sorted(_NBA_CACHE.glob("gamelog_full_*.json"))
    written = skipped = malformed = 0

    for fpath in full_files:
        # gamelog_full_<pid>_<season>.json
        rest = fpath.name.removeprefix("gamelog_full_").removesuffix(".json")
        if "_" not in rest:
            malformed += 1
            continue
        pid, season = rest.split("_", 1)
        target = _NBA_CACHE / f"gamelog_{pid}_{season}.json"

        if target.exists():
            skipped += 1
            continue

        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  malformed: {fpath.name}: {exc}")
            malformed += 1
            continue

        if not isinstance(data, list) or not data:
            malformed += 1
            continue

        converted = [_convert_row(row) for row in data]

        # Drop rows missing the date — the trainer skips them anyway, no point persisting.
        converted = [r for r in converted if r.get("GAME_DATE")]
        if not converted:
            malformed += 1
            continue

        target.write_text(json.dumps(converted), encoding="utf-8")
        written += 1

    print(f"\nwritten: {written}  skipped: {skipped}  malformed: {malformed}")
    print(f"short-form gamelogs in cache: {len(list(_NBA_CACHE.glob('gamelog_[0-9]*.json')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
