"""domains.mlb.ingest_probables -- MLB Stats API daily probables/weather/umpire ingest.

KNOWLEDGE/SUBSTRATE ONLY -- NOT a model-feed signal.
Snapshot of probable pitchers, game weather, and the home-plate umpire as
reported by statsapi.mlb.com at fetch time. Markets are efficient; this adds
data depth, not edge.

Endpoint (free, keyless, browser User-Agent required):
  https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,weather,officials

Notes on the live shape (verified by hand): probablePitcher / weather /
officials may be ABSENT or EMPTY on games far from first pitch -- officials
in particular are usually only populated near/after game time; such gaps
are stored as None, not skipped. probablePitcher does not reliably carry a
pitchHand sub-object; home_sp_hand / away_sp_hand are None when absent.

LEAK CONTRACT: captured_at records when WE knew it (fetch wall-clock, UTC).
Downstream as-of joins MUST key on snapshot_date/captured_at, never on
game_date alone -- a probable pitcher or umpire scraped on game day is not
known information at any earlier as-of point, and a snapshot taken well
before first pitch can still change before game time.

Network isolation: http_get is INJECTABLE; no network at import time.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import pandas as pd
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_TIMEOUT = 12
_SCHEDULE_URL = (
    "https://statsapi.mlb.com/api/v1/schedule"
    "?sportId=1&date={date}&hydrate=probablePitcher,weather,officials"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "probables.parquet"

_DEDUP_KEYS = ["game_pk", "snapshot_date"]

_COLUMNS = [
    "game_pk", "game_date", "snapshot_date", "captured_at",
    "home_team", "away_team", "day_night", "venue",
    "home_sp_id", "home_sp_name", "home_sp_hand",
    "away_sp_id", "away_sp_name", "away_sp_hand",
    "weather_condition", "temp_f", "wind",
    "hp_umpire_id", "hp_umpire_name",
]

_NULLABLE_INT_COLS = ["home_sp_id", "away_sp_id", "hp_umpire_id"]
_FLOAT_COLS = ["temp_f"]


# ---------------------------------------------------------------------------
# Network layer
# ---------------------------------------------------------------------------

def _default_http_get(url: str) -> dict:
    """Fetch url via urllib; returns {} on any error."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        log.warning("MLB schedule fetch failed url=%s err=%s", url, exc)
        return {}


# ---------------------------------------------------------------------------
# Pure parsing helpers (no I/O)
# ---------------------------------------------------------------------------

def _side_pitcher(side_block: dict) -> dict:
    """Extract {id, name, hand} for one team's probablePitcher, all-None if absent."""
    pp = side_block.get("probablePitcher") or {}
    if not pp:
        return {"id": None, "name": None, "hand": None}
    hand_obj = pp.get("pitchHand")
    hand = hand_obj.get("code") if isinstance(hand_obj, dict) else None
    return {"id": pp.get("id"), "name": pp.get("fullName"), "hand": hand}


def _home_plate_umpire(officials: list) -> dict:
    """Return {id, name} for the Home Plate official, all-None if not found."""
    for off in officials or []:
        if off.get("officialType") == "Home Plate":
            person = off.get("official") or {}
            return {"id": person.get("id"), "name": person.get("fullName")}
    return {"id": None, "name": None}


def _parse_weather(weather: dict) -> dict:
    """Extract {condition, temp_f, wind} from a weather block; None fields if absent."""
    weather = weather or {}
    temp_raw = weather.get("temp")
    temp_f: Optional[float] = None
    if temp_raw not in (None, ""):
        try:
            temp_f = float(temp_raw)
        except (TypeError, ValueError):
            pass
    return {
        "condition": weather.get("condition") or None,
        "temp_f": temp_f,
        "wind": weather.get("wind") or None,
    }


def parse_game(game: dict, snapshot_date: str, captured_at: str) -> Optional[dict]:
    """Parse one MLB Stats API schedule game entry into one flat row.

    Returns None if the game entry is missing required team/gamePk data.
    PURE -- no I/O.
    """
    if not game:
        return None
    game_pk = game.get("gamePk")
    teams = game.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    home_team_obj = home.get("team") or {}
    away_team_obj = away.get("team") or {}
    if game_pk is None or not home_team_obj.get("name") or not away_team_obj.get("name"):
        return None

    home_sp = _side_pitcher(home)
    away_sp = _side_pitcher(away)
    weather = _parse_weather(game.get("weather") or {})
    hp_ump = _home_plate_umpire(game.get("officials") or [])
    venue = (game.get("venue") or {}).get("name")

    return {
        "game_pk": int(game_pk),
        "game_date": game.get("officialDate"),
        "snapshot_date": snapshot_date,
        "captured_at": captured_at,
        "home_team": home_team_obj.get("name"),
        "away_team": away_team_obj.get("name"),
        "day_night": game.get("dayNight"),
        "venue": venue,
        "home_sp_id": home_sp["id"],
        "home_sp_name": home_sp["name"],
        "home_sp_hand": home_sp["hand"],
        "away_sp_id": away_sp["id"],
        "away_sp_name": away_sp["name"],
        "away_sp_hand": away_sp["hand"],
        "weather_condition": weather["condition"],
        "temp_f": weather["temp_f"],
        "wind": weather["wind"],
        "hp_umpire_id": hp_ump["id"],
        "hp_umpire_name": hp_ump["name"],
    }


def parse_schedule(payload: dict, snapshot_date: str, captured_at: str) -> List[dict]:
    """Parse a full schedule payload into a list of per-game rows. PURE -- no I/O."""
    if not payload:
        return []
    rows: List[dict] = []
    for date_block in payload.get("dates") or []:
        for game in date_block.get("games") or []:
            row = parse_game(game, snapshot_date, captured_at)
            if row is not None:
                rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Fetch layer
# ---------------------------------------------------------------------------

def fetch_date(date: str, http_get: Optional[Callable] = None) -> List[dict]:
    """Fetch + parse probables/weather/umpires for one YYYY-MM-DD date.

    snapshot_date/captured_at are stamped at call time (local date / UTC iso).
    """
    getter = http_get or _default_http_get
    payload = getter(_SCHEDULE_URL.format(date=date))
    snapshot_date = dt.date.today().isoformat()
    captured_at = dt.datetime.utcnow().isoformat() + "Z"
    return parse_schedule(payload, snapshot_date, captured_at)


# ---------------------------------------------------------------------------
# Frame assembly + parquet merge
# ---------------------------------------------------------------------------

def _coerce_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    for col in _NULLABLE_INT_COLS:
        if col in df.columns:
            df[col] = df[col].astype("Int64")
    for col in _FLOAT_COLS:
        if col in df.columns:
            df[col] = df[col].astype("float64")
    return df


def _rows_to_frame(rows: Sequence[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=_COLUMNS)
    df = pd.DataFrame(rows)
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[_COLUMNS]
    return _coerce_dtypes(df)


def ingest_range(
    dates: Sequence[str],
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
    sleep_s: float = 0.4,
) -> Path:
    """Fetch probables/weather/umpires for *dates* (YYYY-MM-DD) and merge into a parquet.

    One row per (game_pk, snapshot_date); dedup keep-last on that pair so
    re-running the same date is idempotent.
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    rows: List[dict] = []
    for i, date in enumerate(dates):
        rows.extend(fetch_date(date, http_get=getter))
        if (i + 1) % 20 == 0:
            print(f"progress: {i + 1}/{len(dates)} dates fetched")
        if sleep_s and i < len(dates) - 1:
            time.sleep(sleep_s)

    new_df = _rows_to_frame(rows)
    if not new_df.empty:
        new_df = new_df.drop_duplicates(subset=_DEDUP_KEYS, keep="last")

    if out.exists():
        try:
            existing = pd.read_parquet(out)
            existing = _coerce_dtypes(existing)
            combined = pd.concat([existing, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=_DEDUP_KEYS, keep="last")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("S95: unreadable existing parquet %s" % out) from exc
    else:
        combined = new_df

    out.parent.mkdir(parents=True, exist_ok=True)
    if not combined.empty:
        write_parquet_atomic(combined, out)
    log.info("Wrote %d rows to %s", len(combined), out)
    return out


def _date_range(start: str, end: str) -> List[str]:
    d0 = dt.date.fromisoformat(start)
    d1 = dt.date.fromisoformat(end)
    out: List[str] = []
    d = d0
    while d <= d1:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest MLB probable pitchers + weather + umpires (keyless)."
    )
    parser.add_argument("--date", default=None, help="Single date YYYY-MM-DD (default: today).")
    parser.add_argument("--start", default=None, help="Range start YYYY-MM-DD.")
    parser.add_argument("--end", default=None, help="Range end YYYY-MM-DD.")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.start and args.end:
        dates = _date_range(args.start, args.end)
    else:
        dates = [args.date or dt.date.today().isoformat()]

    out_path = Path(args.out) if args.out else None
    result = ingest_range(dates, out_path=out_path)
    print(f"Done: {result}")


if __name__ == "__main__":
    _main()
