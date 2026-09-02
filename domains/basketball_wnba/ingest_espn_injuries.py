"""domains.basketball_wnba.ingest_espn_injuries -- ESPN free-API WNBA injury-report
snapshot ingest (scrape_targets rank 2, lane espn-injuries, 2026-07-04).

PROBE RESULT (live, 2026-07-04): CONFIRMED. GET
  https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/injuries
returned HTTP 200, top-level keys {timestamp, status, season, injuries}, 15
team blocks / 41 injury entries. Schema is byte-for-byte the same shape as
domains/mlb/ingest_injuries.py's MLB endpoint (injuries[].{id,displayName,
injuries[]}, each entry carrying status/date/shortComment/longComment/athlete/
details). This module mirrors that ingest 1:1, swapping only the WNBA URL and
the WNBA player-id link pattern (site.espn.com/wnba/player/_/id/<n>/...).

KNOWLEDGE/SUBSTRATE ONLY -- NOT a model-feed signal by itself. Ingest only;
no feature derivation, no wiring into predictions. The injury_absence_flag
gate is a separate, later, pre-registered item (per task instructions).

LEAK CONTRACT: captured_at is WHEN WE OBSERVED the row (ISO UTC, set at fetch
time) -- NOT when the injury happened. injury_date is ESPN's own 'date' field
on the injury entry and can lag/lead capture. As-of joins MUST key on
snapshot_date (the day WE captured this row), never on injury_date alone.

PROVENANCE (m31 as-of pattern, baked in at write time, not retrofit): every
row carries as_of (== snapshot_date) and corpus_id columns written at
creation, matching domains/basketball_wnba/atlas_extract_*.py convention.
Write is atomic (tmp file + os.replace via Path.replace), matching
atlas_extract_player.py's run_extract_player_atlas pattern.

Network isolation: http_get is INJECTABLE; no network call happens at import.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingest_espn_injuries.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional

import pandas as pd
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_TIMEOUT = 12
_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/injuries"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "wnba" / "injuries.parquet"

CORPUS_ID = "wnba_espn_injuries_v1"

_SNAPSHOT_COLUMNS = [
    "snapshot_date", "captured_at", "team", "athlete_id", "athlete_name",
    "position", "status", "injury_date", "injury_type", "detail", "side",
    "return_date", "short_comment", "long_comment", "as_of", "corpus_id",
]

_PLAYER_ID_RE = re.compile(r"/wnba/player/(?:[a-z]+/)?_/id/(\d+)")


# ---------------------------------------------------------------------------
# Network layer
# ---------------------------------------------------------------------------

def _default_http_get(url: str) -> dict:
    """Fetch url via urllib; returns {} on any error (never raises)."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        log.warning("ESPN fetch failed url=%s err=%s", url, exc)
        return {}


# ---------------------------------------------------------------------------
# Pure parsing helpers (no I/O)
# ---------------------------------------------------------------------------

def _athlete_id(athlete: dict) -> Optional[int]:
    """Pull the numeric ESPN athlete id out of a playercard/overview link href.

    The injury payload never carries athlete.id directly -- only link hrefs
    like '.../wnba/player/_/id/4433386/jaylyn-sherrod'. Returns None if no
    link parses (handled gracefully downstream -- nullable Int64 column).
    """
    for link in athlete.get("links") or []:
        href = link.get("href", "")
        m = _PLAYER_ID_RE.search(href)
        if m:
            return int(m.group(1))
    return None


def _parse_injury_row(team_name: str, entry: dict, snapshot_date: str, captured_at: str) -> Optional[dict]:
    """Parse one injuries[].injuries[] entry into a flat snapshot row.

    Returns None only if there is no usable athlete name at all. Every other
    field is optional and defaults to None/''. PURE -- no I/O.
    """
    athlete = entry.get("athlete") or {}
    name = athlete.get("displayName") or athlete.get("shortName")
    if not name:
        return None

    details = entry.get("details") or {}
    position = (athlete.get("position") or {}).get("abbreviation")

    return {
        "snapshot_date": snapshot_date,
        "captured_at": captured_at,
        "team": team_name,
        "athlete_id": _athlete_id(athlete),
        "athlete_name": name,
        "position": position,
        "status": entry.get("status"),
        "injury_date": entry.get("date"),
        "injury_type": details.get("type"),
        "detail": details.get("detail"),
        "side": details.get("side"),
        "return_date": details.get("returnDate"),
        "short_comment": entry.get("shortComment") or "",
        "long_comment": entry.get("longComment") or "",
        "as_of": snapshot_date,
        "corpus_id": CORPUS_ID,
    }


def parse_injuries_payload(payload: dict, snapshot_date: str, captured_at: str) -> List[dict]:
    """Flatten an ESPN injuries payload into a list of snapshot rows. PURE -- no I/O."""
    rows: List[dict] = []
    for team_block in payload.get("injuries") or []:
        team_name = team_block.get("displayName", "")
        for entry in team_block.get("injuries") or []:
            row = _parse_injury_row(team_name, entry, snapshot_date, captured_at)
            if row is not None:
                rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Fetch + snapshot-append layer
# ---------------------------------------------------------------------------

def fetch_injuries(http_get: Optional[Callable] = None) -> dict:
    """Fetch the raw ESPN injuries payload; returns {} on error."""
    getter = http_get or _default_http_get
    return getter(_INJURIES_URL)


def _now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ingest_snapshot(
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
    snapshot_date: Optional[str] = None,
    captured_at: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch one injuries snapshot and merge it into the append-only parquet.

    Dedup key is (snapshot_date, athlete_id) keep-last -- a same-day re-run is
    idempotent (row count does not grow), but prior snapshot_dates are NEVER
    dropped, so history across days is preserved for as-of joins. Rows with a
    null athlete_id fall back to (snapshot_date, team, athlete_name) for dedup
    since Int64 NaN cannot be a reliable subset key. Write is atomic
    (tmp file + Path.replace).
    Returns the full (existing + new) DataFrame that was written.
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    snap_date = snapshot_date or dt.date.today().strftime("%Y-%m-%d")
    cap_at = captured_at or _now_utc_iso()

    payload = fetch_injuries(http_get=http_get)
    rows = parse_injuries_payload(payload, snap_date, cap_at)
    new_df = pd.DataFrame(rows, columns=_SNAPSHOT_COLUMNS)
    if not new_df.empty:
        new_df["athlete_id"] = new_df["athlete_id"].astype("Int64")

    if out.exists():
        try:
            existing = pd.read_parquet(out)
            new_df = pd.concat([existing, new_df], ignore_index=True)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("S95: unreadable existing parquet %s" % out) from exc

    if not new_df.empty:
        has_id = new_df["athlete_id"].notna()
        keyed = new_df[has_id].drop_duplicates(subset=["snapshot_date", "athlete_id"], keep="last")
        unkeyed = new_df[~has_id].drop_duplicates(
            subset=["snapshot_date", "team", "athlete_name"], keep="last"
        )
        new_df = pd.concat([keyed, unkeyed], ignore_index=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    if not new_df.empty:
        write_parquet_atomic(new_df, out)
    log.info("wnba injuries snapshot: %d rows -> %s", len(new_df), out)
    return new_df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    snap_df = ingest_snapshot()
    teams = snap_df["team"].nunique() if not snap_df.empty else 0
    print(f"snapshot rows: {len(snap_df)}")
    print(f"teams: {teams}")
    print(f"out: {_DEFAULT_OUT}")


if __name__ == "__main__":
    _main()


__all__ = ["fetch_injuries", "parse_injuries_payload", "ingest_snapshot", "CORPUS_ID", "_DEFAULT_OUT"]
