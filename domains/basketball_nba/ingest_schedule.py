"""domains.basketball_nba.ingest_schedule — schedule JSONs → games.parquet.

Reads 120 per-team schedule JSON files (data/nba/schedule/schedule_{TEAM}_{SEASON}_v2.json).
Each file contains one team's perspective of its 73-82 games.  Each game appears TWICE —
once from the home team's file and once from the away team's file.

build_games(out_path=None) -> Path
  Deduplicates to ONE row per game_id and writes the parquet.

Output columns (exact, in order):
  game_id, date, season, home_team, away_team, home_win,
  rest_days_home, rest_days_away, home_b2b, away_b2b,
  travel_home, travel_away

home_win: float (1.0 = home team won, 0.0 = away team won, NaN = not yet played).
rest_days capped at REST_CAP (99-sentinel clipped to sane max).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEDULE_DIR = _REPO_ROOT / "data" / "nba" / "schedule"
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_FILENAME_RE = re.compile(r"schedule_([A-Z0-9]+)_(\d{4}-\d{2})_v2\.json$")
REST_CAP = 10  # clip season-start sentinel (99) to this value

GAMES_COLS: Tuple[str, ...] = (
    "game_id", "date", "season", "home_team", "away_team", "home_win",
    "rest_days_home", "rest_days_away", "home_b2b", "away_b2b",
    "travel_home", "travel_away",
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_files(schedule_dir: Path) -> List[dict]:
    """Read all schedule_*_v2.json files; tag each row with team/season."""
    rows: List[dict] = []
    for fpath in sorted(schedule_dir.glob("schedule_*_v2.json")):
        m = _FILENAME_RE.match(fpath.name)
        if not m:
            continue
        team, season = m.group(1), m.group(2)
        try:
            records = json.loads(fpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(records, list):
            continue
        for rec in records:
            rec = dict(rec)
            rec["_team"] = team
            rec["_season"] = season
            rows.append(rec)
    return rows


def _dedup(rows: List[dict]) -> List[dict]:
    """Merge two per-team perspectives into one row per game_id.

    Strategy:
    - Collect home-perspective and away-perspective rows keyed by game_id.
    - For each game_id, join the two (or use whichever exists if only one).
    - home_win: read from the home-perspective row's wl field ("W" → 1.0, else 0.0,
      None/missing → NaN).
    """
    # Bucket rows: home_rows[game_id] and away_rows[game_id]
    home_rows: Dict[str, dict] = {}
    away_rows: Dict[str, dict] = {}

    for r in rows:
        gid = str(r.get("game_id", ""))
        if not gid:
            continue
        if r.get("home") is True:
            # This team is the home team
            home_rows.setdefault(gid, r)
        else:
            away_rows.setdefault(gid, r)

    all_ids = set(home_rows) | set(away_rows)
    out: List[dict] = []

    for gid in all_ids:
        hr = home_rows.get(gid)
        ar = away_rows.get(gid)

        # date and season: prefer home row
        primary = hr if hr is not None else ar
        date_str = str(primary.get("date", ""))
        season = primary.get("_season", "")

        # team identities
        if hr is not None and ar is not None:
            home_team = hr["_team"]
            away_team = ar["_team"]
        elif hr is not None:
            home_team = hr["_team"]
            away_team = str(hr.get("opponent", ""))
        else:
            away_team = ar["_team"]  # type: ignore[union-attr]
            home_team = str(ar.get("opponent", ""))  # type: ignore[union-attr]

        # home_win from the home-team perspective
        if hr is not None:
            wl = hr.get("wl")
            if wl == "W":
                home_win: float = 1.0
            elif wl == "L":
                home_win = 0.0
            else:
                home_win = float("nan")
        else:
            # Only away perspective available: invert their wl
            wl_a = ar.get("wl")  # type: ignore[union-attr]
            if wl_a == "W":
                home_win = 0.0
            elif wl_a == "L":
                home_win = 1.0
            else:
                home_win = float("nan")

        def _rest(row: Optional[dict]) -> float:
            if row is None:
                return float("nan")
            v = row.get("rest_days")
            try:
                return float(min(int(v), REST_CAP))
            except (TypeError, ValueError):
                return float("nan")

        def _b2b(row: Optional[dict]) -> object:
            if row is None:
                return None
            return bool(row.get("back_to_back", False))

        def _travel(row: Optional[dict]) -> float:
            if row is None:
                return float("nan")
            v = row.get("travel_miles")
            try:
                return float(v)
            except (TypeError, ValueError):
                return float("nan")

        out.append({
            "game_id": gid,
            "date": pd.Timestamp(date_str) if date_str else pd.NaT,
            "season": season,
            "home_team": home_team,
            "away_team": away_team,
            "home_win": home_win,
            "rest_days_home": _rest(hr),
            "rest_days_away": _rest(ar),
            "home_b2b": _b2b(hr),
            "away_b2b": _b2b(ar),
            "travel_home": _travel(hr),
            "travel_away": _travel(ar),
        })

    return out


def build_games(out_path: Optional[str] = None) -> Path:
    """Read schedule JSONs → deduplicate → write games.parquet.

    Returns the Path where the parquet was written.
    """
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT
    dest.parent.mkdir(parents=True, exist_ok=True)

    raw_rows = _parse_files(_SCHEDULE_DIR)
    game_rows = _dedup(raw_rows)

    if not game_rows:
        df = pd.DataFrame(columns=list(GAMES_COLS))
    else:
        df = pd.DataFrame(game_rows)
        df = df[list(GAMES_COLS)]
        df["home_win"] = df["home_win"].astype("float32")
        df["rest_days_home"] = df["rest_days_home"].astype("float32")
        df["rest_days_away"] = df["rest_days_away"].astype("float32")
        df["travel_home"] = df["travel_home"].astype("float32")
        df["travel_away"] = df["travel_away"].astype("float32")
        df = (
            df.sort_values(["date", "game_id"], kind="mergesort")
              .reset_index(drop=True)
        )

    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, str(dest))
    return dest


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="NBA schedule ingest → games.parquet")
    ap.add_argument("--out", default=None, help="Output parquet path (optional)")
    args = ap.parse_args()

    dest = build_games(out_path=args.out)
    df = pd.read_parquet(str(dest))
    n_games = len(df)
    hw_mean = float(df["home_win"].mean()) if n_games else float("nan")
    print(f"Wrote {n_games} games to {dest}")
    print(f"home_win mean: {hw_mean:.4f}")
    print(f"Schema: {list(df.columns)}")
    print(df.head(3).to_string())
