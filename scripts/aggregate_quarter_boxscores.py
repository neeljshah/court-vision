"""aggregate_quarter_boxscores.py — consolidate quarter caches → parquet.

Walks ``data/cache/quarter_box/<game_id>_q<period>.json`` (cycle 91a fetch
output) and writes ``data/player_quarter_stats.parquet`` with columns:

    game_id, player_id, period, min, pts, reb, ast, fg3m, stl, blk, tov,
    pf, plus_minus

Each cache file holds the v3 player frame for ONE quarter of ONE game,
so the consolidated parquet has up to 4 rows per (game_id, player_id).
Players who sat the entire quarter are skipped (their row is absent).

Safe to re-run — overwrites the parquet from scratch each time.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")
_PARQUET_PATH = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")

# Canonical column mapping. Supports both v2 (MIN/PTS/REB lowercased)
# AND v3 (minutes/points/reboundsTotal lowercased) cache payloads —
# cycle 91a switched from v3 to v2 mid-cycle when v3 was found to ignore
# the period parameter, so older v3-style caches still need to read.
_COL_MAP = {
    "min":         ("min", "minutes"),
    "pts":         ("pts", "points"),
    "reb":         ("reb", "reboundstotal", "rebounds_total", "rebounds"),
    "ast":         ("ast", "assists"),
    "fg3m":        ("fg3m", "threepointersmade", "three_pointers_made"),
    "stl":         ("stl", "steals"),
    "blk":         ("blk", "blocks"),
    "tov":         ("to", "tov", "turnovers"),
    "pf":          ("pf", "foulspersonal", "fouls_personal", "personal_fouls"),
    "plus_minus":  ("plus_minus", "plusminuspoints",
                    "plus_minus_points", "plusminus"),
}

# Filename pattern: <game_id>_q<period>.json
_FNAME_RE = re.compile(r"^(\d{10})_q([1-4])\.json$")


def _coerce_num(v) -> Optional[float]:
    """Parse v3's 'MM:SS' minute strings + numeric fields → float."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        try:
            return float(v)
        except Exception:
            return None
    s = str(v).strip()
    if not s:
        return None
    # Minutes can come back as 'MM:SS' (v3 style) or 'MM.M'. Handle both.
    if ":" in s:
        try:
            mm, ss = s.split(":", 1)
            return float(mm) + float(ss) / 60.0
        except (ValueError, TypeError):
            return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _pick(row: dict, candidates) -> Optional[float]:
    """Return the first non-null value among the candidate keys."""
    for k in candidates:
        if k in row:
            v = row[k]
            if v is not None and v != "":
                return _coerce_num(v)
    return None


def _player_id(row: dict) -> Optional[int]:
    # v2 uses player_id; v3 uses personId; cache writer lowercases both.
    for k in ("player_id", "personid", "person_id", "playerid"):
        if k in row and row[k] is not None and row[k] != "":
            try:
                return int(row[k])
            except (ValueError, TypeError):
                continue
    return None


def consolidate(cache_dir: str = _CACHE_DIR,
                parquet_path: str = _PARQUET_PATH) -> int:
    """Walk the cache and write the parquet. Returns row count."""
    import pandas as pd

    if not os.path.isdir(cache_dir):
        print(f"  [skip] no cache dir: {cache_dir}")
        return 0

    rows: List[Dict] = []
    for fname in sorted(os.listdir(cache_dir)):
        m = _FNAME_RE.match(fname)
        if not m:
            continue
        game_id = m.group(1)
        period = int(m.group(2))
        try:
            with open(os.path.join(cache_dir, fname), encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue
        players = payload.get("players") or []
        for prow in players:
            pid = _player_id(prow)
            if pid is None:
                continue
            minutes = _pick(prow, _COL_MAP["min"])
            # Skip DNPs — v3 reports MIN=None or 0 for players who sat the
            # whole quarter; they don't belong in the aggregation.
            if minutes is None or minutes <= 0:
                continue
            rows.append({
                "game_id":    game_id,
                "player_id":  pid,
                "period":     period,
                "min":        minutes,
                "pts":        _pick(prow, _COL_MAP["pts"]) or 0.0,
                "reb":        _pick(prow, _COL_MAP["reb"]) or 0.0,
                "ast":        _pick(prow, _COL_MAP["ast"]) or 0.0,
                "fg3m":       _pick(prow, _COL_MAP["fg3m"]) or 0.0,
                "stl":        _pick(prow, _COL_MAP["stl"]) or 0.0,
                "blk":        _pick(prow, _COL_MAP["blk"]) or 0.0,
                "tov":        _pick(prow, _COL_MAP["tov"]) or 0.0,
                "pf":         _pick(prow, _COL_MAP["pf"]) or 0.0,
                "plus_minus": _pick(prow, _COL_MAP["plus_minus"]) or 0.0,
            })

    if not rows:
        print("  [skip] no cached rows to consolidate")
        return 0

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(parquet_path), exist_ok=True)
    df.to_parquet(parquet_path, index=False)
    print(f"  wrote {parquet_path} ({len(df)} rows, "
          f"{df['game_id'].nunique()} games, "
          f"{df['player_id'].nunique()} players)")
    return len(df)


def main() -> int:
    n = consolidate()
    print(f"[parquet] {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
