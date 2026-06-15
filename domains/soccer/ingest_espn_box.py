"""domains.soccer.ingest_espn_box — ESPN free-API soccer team match-stats ingestion.

KNOWLEDGE/SUBSTRATE ONLY — NOT a model-feed signal.
Realized post-match stats; must be joined as-of before feeding any model.
Markets are efficient; this adds data depth, not edge.

Endpoints (free, no auth):
  scoreboard: https://site.api.espn.com/apis/site/v2/sports/soccer/<league>/scoreboard?dates=YYYYMMDD
  summary:    https://site.api.espn.com/apis/site/v2/sports/soccer/<league>/summary?event=<id>

Supported league slugs: eng.1, esp.1, ita.1, ger.1, fra.1

Summary shape (confirmed 2026-06-14 against eng.1 / event 740956):
  boxscore.teams[].statistics is a flat list [{name, displayValue, value}].
  The `value` field is always null for soccer — use `displayValue`.
  Each team block exposes 28 fields (see _STAT_FIELDS).
  Scores/status come from header.competitions[].competitors[].score.

Network isolation: http_get is INJECTABLE; no network at import time.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_TIMEOUT = 12
_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard?dates={date}"
)
_SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/summary?event={event_id}"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "soccer" / "espn_matchstats.parquet"

# All 28 stat fields confirmed in the ESPN soccer summary payload.
# Values live in displayValue (not value, which is always null for soccer).
_STAT_FIELDS: tuple = (
    "foulsCommitted",
    "yellowCards",
    "redCards",
    "offsides",
    "wonCorners",
    "saves",
    "possessionPct",
    "totalShots",
    "shotsOnTarget",
    "shotPct",
    "penaltyKickGoals",
    "penaltyKickShots",
    "accuratePasses",
    "totalPasses",
    "passPct",
    "accurateCrosses",
    "totalCrosses",
    "crossPct",
    "totalLongBalls",
    "accurateLongBalls",
    "longballPct",
    "blockedShots",
    "effectiveTackles",
    "totalTackles",
    "tacklePct",
    "interceptions",
    "effectiveClearance",
    "totalClearance",
)

SUPPORTED_LEAGUES: tuple = ("eng.1", "esp.1", "ita.1", "ger.1", "fra.1")


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
        log.warning("ESPN fetch failed url=%s err=%s", url, exc)
        return {}


# ---------------------------------------------------------------------------
# Pure parsing helpers (no I/O)
# ---------------------------------------------------------------------------

def _extract_stats(stats_list: list) -> Dict[str, Optional[float]]:
    """Convert ESPN soccer stats list [{name, displayValue, value}] -> {name: float|None}.

    Soccer stats use displayValue; value is always null. Falls back to value if
    displayValue is absent or non-numeric.
    """
    lookup: Dict[str, Optional[float]] = {}
    for item in stats_list:
        name = item.get("name")
        if name not in _STAT_FIELDS:
            continue
        # Prefer displayValue (soccer API always populates it); fall back to value
        raw = item.get("displayValue")
        if raw is None:
            raw = item.get("value")
        try:
            lookup[name] = float(str(raw).replace(",", "")) if raw is not None else None
        except (TypeError, ValueError):
            lookup[name] = None
    return {f: lookup.get(f) for f in _STAT_FIELDS}


def _parse_summary(payload: dict, event_id: str, league: str) -> dict:
    """Extract per-team match stats from an ESPN soccer summary payload.

    Returns flat dict keyed by event_id / date / league / home+away abbr / scores /
    status / venue / attendance and home_<stat> / away_<stat> for all 28 stat fields.
    Returns {} on empty/missing payload. PURE — no I/O.
    """
    if not payload:
        return {}
    teams_raw = payload.get("boxscore", {}).get("teams")
    if not isinstance(teams_raw, list) or len(teams_raw) < 2:
        return {}

    team_stats: Dict[str, Dict[str, Optional[float]]] = {}
    team_meta: Dict[str, dict] = {}
    for block in teams_raw:
        side = block.get("homeAway", "")
        if side in ("home", "away"):
            team_stats[side] = _extract_stats(block.get("statistics") or [])
            team_meta[side] = block.get("team", {})

    if "home" not in team_stats or "away" not in team_stats:
        return {}

    home_score: Optional[float] = None
    away_score: Optional[float] = None
    status_name = ""
    comps = (payload.get("header") or {}).get("competitions") or []
    if comps:
        comp = comps[0]
        for ct in comp.get("competitors") or []:
            try:
                score: Optional[float] = float(ct.get("score", ""))
            except (TypeError, ValueError):
                score = None
            if ct.get("homeAway") == "home":
                home_score = score
            elif ct.get("homeAway") == "away":
                away_score = score
        status_name = comp.get("status", {}).get("type", {}).get("name", "")

    gi = payload.get("gameInfo") or {}
    venue = (gi.get("venue") or {}).get("fullName", "")
    try:
        attendance: Optional[float] = float(gi.get("attendance") or "")
    except (TypeError, ValueError):
        attendance = None

    row: dict = {
        "event_id": str(event_id),
        "league": league,
        "home_abbr": team_meta.get("home", {}).get("abbreviation", ""),
        "away_abbr": team_meta.get("away", {}).get("abbreviation", ""),
        "home_score": home_score,
        "away_score": away_score,
        "status": status_name,
        "venue": venue,
        "attendance": attendance,
    }
    for side in ("home", "away"):
        for k, v in team_stats[side].items():
            row[f"{side}_{k}"] = v
    return row


# ---------------------------------------------------------------------------
# Fetch layer
# ---------------------------------------------------------------------------

def fetch_scoreboard(date: str, league: str, http_get: Optional[Callable] = None) -> List[dict]:
    """Return [{event_id, date, league, name}] for YYYYMMDD date string and league slug."""
    getter = http_get or _default_http_get
    payload = getter(_SCOREBOARD_URL.format(league=league, date=date))
    return [
        {"event_id": str(ev["id"]), "date": date, "league": league, "name": ev.get("name", "")}
        for ev in (payload.get("events") or [])
        if ev.get("id")
    ]


def fetch_match(event_id: str, league: str, http_get: Optional[Callable] = None) -> dict:
    """Fetch and parse match stats for a single ESPN event_id; returns {} on error."""
    getter = http_get or _default_http_get
    payload = getter(_SUMMARY_URL.format(league=league, event_id=event_id))
    return _parse_summary(payload, event_id, league)


# ---------------------------------------------------------------------------
# Ingest range — writes gitignored parquet
# ---------------------------------------------------------------------------

def ingest_range(
    dates: Sequence[str],
    leagues: Optional[Sequence[str]] = None,
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """Fetch ESPN match stats for *dates* (YYYYMMDD) across *leagues* and write/merge a parquet.

    One row per match; dedup on (event_id, league) keeping last.
    Off-season leagues return 0 events and are skipped gracefully.
    Descriptive/realized only — NOT a model input without as-of join.
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    active_leagues = list(leagues) if leagues else list(SUPPORTED_LEAGUES)
    rows: List[dict] = []

    for date in dates:
        for league in active_leagues:
            events = fetch_scoreboard(date, league, http_get=getter)
            log.info("date=%s league=%s events=%d", date, league, len(events))
            for ev in events:
                eid = ev["event_id"]
                row = fetch_match(eid, league, http_get=getter)
                if row:
                    row["date"] = date
                    rows.append(row)
                else:
                    log.debug("event_id=%s league=%s: empty parse (may be in-progress)", eid, league)

    new_df = pd.DataFrame(rows) if rows else pd.DataFrame()
    # Normalise date to datetime64 so appends merge cleanly with a datetime-typed parquet
    # (a mixed str/datetime column makes pyarrow refuse the write).
    if not new_df.empty and "date" in new_df.columns:
        new_df["date"] = pd.to_datetime(new_df["date"], format="mixed", errors="coerce")
    if out.exists() and not new_df.empty:
        try:
            existing = pd.read_parquet(out)
            if "date" in existing.columns:
                existing["date"] = pd.to_datetime(existing["date"], format="mixed", errors="coerce")
            new_df = (
                pd.concat([existing, new_df], ignore_index=True)
                .drop_duplicates(subset=["event_id", "league"], keep="last")
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not read existing parquet %s: %s — overwriting", out, exc)

    out.parent.mkdir(parents=True, exist_ok=True)
    if not new_df.empty:
        new_df.to_parquet(out, index=False)
    log.info("Wrote %d rows to %s", len(new_df), out)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ingest ESPN soccer match stats.")
    parser.add_argument("--dates", nargs="+", default=[dt.date.today().strftime("%Y%m%d")])
    parser.add_argument(
        "--leagues", nargs="+", default=list(SUPPORTED_LEAGUES),
        help="League slugs, e.g. eng.1 esp.1",
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(f"Done: {ingest_range(args.dates, leagues=args.leagues, out_path=args.out)}")


if __name__ == "__main__":
    _main()
