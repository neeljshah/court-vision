"""domains.soccer.ingest_espn_players -- ESPN free-API per-PLAYER soccer match stats.

KNOWLEDGE/SUBSTRATE ONLY. Realized POST-MATCH player stats (one row per player per
match) feeding World Cup player-prop rate priors + prop-bet settlement. LEAK-FREE
means these rows MUST be joined AS-OF (strictly BEFORE kickoff) before feeding any
model; a player's own post-match row is never a feature for that same match. Markets
are efficient -- this adds per-player data depth, not edge. Companion to (and does
NOT touch) the team-level ingest_espn_box.py.

Summary shape (confirmed 2026-06-16 against fifa.world / event 760432):
  summary["rosters"] = 2 team blocks. block["roster"][] players: athlete{id,
  displayName}, position{abbreviation}, starter, subbedIn, subbedOut, jersey,
  stats[]. stats are [{name,value,displayValue}] -- value IS numeric per-player; GK
  rows expose saves/shotsFaced. summary["keyEvents"] substitution events
  (type.text=="Substitution"): clock.displayValue is the minute ("75'");
  participants[] carry only {athlete:{id}} and do NOT label in vs out -- we
  disambiguate via the roster subbedIn/subbedOut flags. That minute is the off-minute
  for the out-player, on-minute for the in.

Network isolation: http_get is INJECTABLE; no network at import time.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_TIMEOUT = 12
_SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/summary?event={event_id}"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "soccer" / "espn_player_stats.parquet"

# Per-player numeric stat columns emitted (ESPN stat name == output column name).
_STAT_FIELDS: tuple = (
    "totalShots", "shotsOnTarget", "foulsCommitted", "foulsSuffered", "yellowCards",
    "redCards", "goalAssists", "offsides", "totalGoals", "saves",
)

_FULL_MATCH = 90.0
_SUB_IN_FALLBACK = 20.0  # used only when an on-minute can't be found in keyEvents


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

def _stat_value(item: dict) -> Optional[float]:
    """Numeric value from a stat dict; prefer value, fall back to displayValue."""
    raw = item.get("value")
    if raw is None:
        raw = item.get("displayValue")
    try:
        return float(str(raw).replace(",", "")) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _extract_stats(stats_list: list) -> Dict[str, Optional[float]]:
    """ESPN per-player stats list -> {field: float|None} for the emitted fields."""
    lookup: Dict[str, Optional[float]] = {}
    for item in stats_list or []:
        name = item.get("name")
        if name in _STAT_FIELDS:
            lookup[name] = _stat_value(item)
    return {f: lookup.get(f) for f in _STAT_FIELDS}


def _parse_minute(display: Optional[str]) -> Optional[int]:
    """'75'' or "75'" or '90+3' -> 75 (the leading integer); None if unparseable."""
    if not display:
        return None
    m = re.search(r"\d+", str(display))
    return int(m.group()) if m else None


def _sub_minutes(payload: dict) -> Dict[str, int]:
    """Map athlete_id (str) -> substitution minute from keyEvents. Both participants
    of a sub share the event minute; the caller decides on- vs off- via roster flags.
    """
    out: Dict[str, int] = {}
    for ev in payload.get("keyEvents") or []:
        text = (ev.get("type") or {}).get("text") or ""
        if "sub" not in text.lower():
            continue
        minute = _parse_minute((ev.get("clock") or {}).get("displayValue"))
        if minute is None:
            continue
        for pt in ev.get("participants") or []:
            aid = (pt.get("athlete") or {}).get("id")
            if aid is not None:
                out[str(aid)] = minute
    return out


def _derive_minutes(
    starter: bool, subbed_in: bool, subbed_out: bool, sub_minute: Optional[int]
) -> tuple:
    """Best-effort minutes played -> (minutes, estimated_flag).

    starter & not off -> 90; starter & off -> off-minute; sub on & not off ->
    90 - on-minute; sub on & off -> single-sub estimate; never played -> 0.
    Missing sub minute -> conservative fallback + estimated_flag=True.
    """
    if not starter and not subbed_in:
        return 0.0, False
    if starter and not subbed_out:
        return _FULL_MATCH, False
    if starter and subbed_out:
        if sub_minute is None:
            return _FULL_MATCH, True
        return float(sub_minute), False
    if subbed_in and not subbed_out:
        if sub_minute is None:
            return _SUB_IN_FALLBACK, True
        return float(max(0, _FULL_MATCH - sub_minute)), False
    # subbed_in and subbed_out: only one minute available for this athlete -> estimate.
    if sub_minute is None:
        return _SUB_IN_FALLBACK, True
    return float(max(0.0, _FULL_MATCH - sub_minute)), True


def _parse_player_summary(payload: dict, event_id: str, league: str) -> List[dict]:
    """Per-player rows from an ESPN soccer summary payload. PURE -- no I/O. One row
    per rostered player; unused subs are KEPT (minutes 0.0, stats None -- a real
    0-minute fact). Returns [] on empty/missing payload.
    """
    if not payload:
        return []
    rosters = payload.get("rosters")
    if not isinstance(rosters, list) or not rosters:
        return []

    sub_minutes = _sub_minutes(payload)
    rows: List[dict] = []
    for block in rosters:
        side = block.get("homeAway", "")
        team_abbr = (block.get("team") or {}).get("abbreviation", "")
        for p in block.get("roster") or []:
            athlete = p.get("athlete") or {}
            pid = athlete.get("id")
            if pid is None:
                continue
            starter = bool(p.get("starter"))
            subbed_in = bool(p.get("subbedIn"))
            subbed_out = bool(p.get("subbedOut"))
            minutes, estimated = _derive_minutes(
                starter, subbed_in, subbed_out, sub_minutes.get(str(pid))
            )
            row: dict = {
                "event_id": str(event_id),
                "league": league,
                "team_abbr": team_abbr,
                "home_away": side,
                "player_id": str(pid),
                "player": athlete.get("displayName", ""),
                "position": (p.get("position") or {}).get("abbreviation", ""),
                "starter": starter,
                "subbed_in": subbed_in,
                "subbed_out": subbed_out,
                "minutes": minutes,
                "minutes_estimated": estimated,
            }
            row.update(_extract_stats(p.get("stats") or []))
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Fetch layer
# ---------------------------------------------------------------------------

def fetch_player_match(
    event_id: str, league: str = "fifa.world", http_get: Optional[Callable] = None
) -> List[dict]:
    """Fetch + parse per-player stats for one ESPN event_id; [] on error."""
    getter = http_get or _default_http_get
    payload = getter(_SUMMARY_URL.format(league=league, event_id=event_id))
    return _parse_player_summary(payload, event_id, league)


def fetch_scoreboard(
    date: str, league: str = "fifa.world", http_get: Optional[Callable] = None
) -> List[dict]:
    """Return [{event_id, date, league, name}] for a YYYYMMDD date + league slug.

    Mirrors ingest_espn_box.fetch_scoreboard; replicated to keep this module
    self-contained without importing from the team-level module.
    """
    getter = http_get or _default_http_get
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/soccer/"
        f"{league}/scoreboard?dates={date}"
    )
    payload = getter(url)
    return [
        {"event_id": str(ev["id"]), "date": date, "league": league, "name": ev.get("name", "")}
        for ev in (payload.get("events") or [])
        if ev.get("id")
    ]


# ---------------------------------------------------------------------------
# Ingest range -- writes gitignored parquet
# ---------------------------------------------------------------------------

def ingest_range(
    dates: Sequence[str],
    leagues: Sequence[str] = ("fifa.world",),
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """Fetch per-player stats for *dates* (YYYYMMDD) x *leagues*; write/merge parquet.

    One row per player per match; dedup on (event_id, player_id) keeping last.
    Off-day leagues return 0 events and are skipped gracefully.
    Realized/post-match only -- NOT a model input without an as-of join.
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    rows: List[dict] = []

    for date in dates:
        for league in leagues:
            events = fetch_scoreboard(date, league, http_get=getter)
            log.info("date=%s league=%s events=%d", date, league, len(events))
            for ev in events:
                eid = ev["event_id"]
                player_rows = fetch_player_match(eid, league, http_get=getter)
                for r in player_rows:
                    r["date"] = date
                    rows.append(r)
                if not player_rows:
                    log.debug("event_id=%s league=%s: no player rows", eid, league)

    new_df = pd.DataFrame(rows) if rows else pd.DataFrame()
    # Normalise date to datetime64 so appends merge cleanly with a datetime parquet.
    if not new_df.empty and "date" in new_df.columns:
        new_df["date"] = pd.to_datetime(new_df["date"], format="mixed", errors="coerce")
    if out.exists() and not new_df.empty:
        try:
            existing = pd.read_parquet(out)
            if "date" in existing.columns:
                existing["date"] = pd.to_datetime(existing["date"], format="mixed", errors="coerce")
            new_df = (
                pd.concat([existing, new_df], ignore_index=True)
                .drop_duplicates(subset=["event_id", "player_id"], keep="last")
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("S95: unreadable existing parquet %s" % out) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    if not new_df.empty:
        write_parquet_atomic(new_df, out)
    log.info("Wrote %d player rows to %s", len(new_df), out)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ingest ESPN per-player soccer stats.")
    parser.add_argument("--dates", nargs="+", default=[dt.date.today().strftime("%Y%m%d")])
    parser.add_argument("--leagues", nargs="+", default=["fifa.world"])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(f"Done: {ingest_range(args.dates, leagues=args.leagues, out_path=args.out)}")


if __name__ == "__main__":
    _main()
