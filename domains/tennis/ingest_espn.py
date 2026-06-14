"""domains.tennis.ingest_espn — ESPN free-API tennis match ingestion.

KNOWLEDGE/SUBSTRATE ONLY — NOT a model-feed signal.
Realized post-match scoreline data; must be joined as-of before feeding any model.
Markets are efficient; this adds data depth, not edge.

Endpoints (free, no auth):
  ATP scoreboard: https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard?dates=YYYYMMDD
  WTA scoreboard: https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard?dates=YYYYMMDD

WHAT ESPN TENNIS RETURNS (probed 2026-06-14, live):
  - Per-tournament groupings with competitions (matches) nested under each grouping.
  - Per-match: competition_id, match date, status (STATUS_FINAL / in-progress),
    round name, discipline (Men's Singles / Women's Singles / Doubles etc.),
    tournament name, tournament id, major flag, season year, best-of format.
  - Per-player per-match: displayName, winner flag, per-set scores (linescores)
    with tiebreak counts where applicable.
  - NO serve statistics (statsSource=none across all sampled completed matches).
  - Summary endpoint (/summary?event=<comp_id>) returns HTTP 400 for all tested
    comp ids — it is NOT usable for tennis.
  - Player names absent for some inner-draw competitions in later rounds
    (athlete field missing in scoreboard payload for those comps).
  - Odds: empty (count=0) in core API for all sampled matches.

Output parquet schema (1 row per player per match, i.e. 2 rows per match):
  comp_id, date, league, tournament_id, tournament_name, major, season_year,
  best_of, discipline, round_name, status, player_name, winner,
  sets_won, s1..s5 (games per set, NaN if set not played),
  tb1..tb5 (tiebreak score for player, NaN if no tiebreak in that set).

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
_LEAGUES = ("atp", "wta")
_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/tennis/{league}/scoreboard?dates={date}"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "tennis" / "espn_matches.parquet"
_MAX_SETS = 5


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

def _parse_linescores(linescores: list) -> Dict[str, Optional[float]]:
    """Convert ESPN tennis linescores list to per-set games + tiebreak columns.

    Each linescore item may be: {value: float, winner: bool, period: int,
    tiebreak: int (optional)}.  The scoreboard endpoint omits 'period'; in that
    case the list index (1-based) is used as the set number.  Up to _MAX_SETS.

    Returns dict with keys s1..s5, tb1..tb5 (None when set not played).
    PURE — no I/O.
    """
    result: Dict[str, Optional[float]] = {}
    for s in range(1, _MAX_SETS + 1):
        result[f"s{s}"] = None
        result[f"tb{s}"] = None

    for idx, item in enumerate(linescores, start=1):
        period = item.get("period")
        # Fall back to list index when period is absent (scoreboard endpoint)
        if period is None:
            period = idx
        if not (1 <= period <= _MAX_SETS):
            continue
        val = item.get("value")
        try:
            result[f"s{period}"] = float(val) if val is not None else None
        except (TypeError, ValueError):
            result[f"s{period}"] = None
        tb = item.get("tiebreak")
        if tb is not None:
            try:
                result[f"tb{period}"] = float(tb)
            except (TypeError, ValueError):
                pass
    return result


def _sets_won(linescores: list) -> int:
    """Count sets won by this player (winner=True on linescore item)."""
    return sum(1 for item in linescores if item.get("winner") is True)


def _parse_competition(
    comp: dict,
    league: str,
    tournament_id: str,
    tournament_name: str,
    major: bool,
    season_year: Optional[int],
    discipline: str,
) -> List[dict]:
    """Parse one ESPN competition object into 0–2 player rows.

    Returns [] on missing/incomplete data. PURE — no I/O.
    """
    comp_id = str(comp.get("id", ""))
    if not comp_id:
        return []

    date_raw = comp.get("date") or comp.get("startDate") or ""
    status = comp.get("status", {}).get("type", {}).get("name", "")
    round_name = comp.get("round", {}).get("displayName", "")
    fmt = comp.get("format", {})
    best_of: Optional[int] = None
    try:
        periods = fmt.get("regulation", {}).get("periods")
        if periods is not None:
            best_of = int(periods)
    except (TypeError, ValueError):
        pass

    rows: List[dict] = []
    for comp_player in comp.get("competitors", []):
        ath = comp_player.get("athlete") or {}
        player_name = (
            ath.get("displayName") or ath.get("fullName") or ath.get("name") or ""
        )
        winner = comp_player.get("winner")
        lsc_raw = comp_player.get("linescores") or []

        set_cols = _parse_linescores(lsc_raw)
        sw = _sets_won(lsc_raw)

        row: dict = {
            "comp_id": comp_id,
            "date": date_raw,
            "league": league,
            "tournament_id": tournament_id,
            "tournament_name": tournament_name,
            "major": major,
            "season_year": season_year,
            "best_of": best_of,
            "discipline": discipline,
            "round_name": round_name,
            "status": status,
            "player_name": player_name,
            "winner": winner,
            "sets_won": sw,
        }
        row.update(set_cols)
        rows.append(row)
    return rows


def parse_scoreboard(payload: dict, league: str) -> List[dict]:
    """Parse a full scoreboard payload into a flat list of player-match rows.

    One row per player per competition (2 rows/match).  Returns [] on empty
    or malformed payload. PURE — no I/O.
    """
    if not payload:
        return []
    events = payload.get("events")
    if not isinstance(events, list):
        return []
    rows: List[dict] = []
    for event in events:
        tournament_id = str(event.get("id", ""))
        tournament_name = event.get("name", "")
        major = bool(event.get("major", False))
        season_year: Optional[int] = None
        try:
            season_year = int(event.get("season", {}).get("year", 0)) or None
        except (TypeError, ValueError):
            pass

        for grouping in event.get("groupings") or []:
            discipline = (
                (grouping.get("grouping") or {}).get("displayName") or ""
            )
            for comp in grouping.get("competitions") or []:
                rows.extend(
                    _parse_competition(
                        comp, league, tournament_id, tournament_name,
                        major, season_year, discipline,
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# Fetch layer
# ---------------------------------------------------------------------------

def fetch_scoreboard(
    date: str, league: str, http_get: Optional[Callable] = None
) -> List[dict]:
    """Fetch and parse ESPN tennis scoreboard for one date + league.

    Returns list of player-match rows (see parse_scoreboard). Empty on error.
    """
    getter = http_get or _default_http_get
    url = _SCOREBOARD_URL.format(league=league, date=date)
    payload = getter(url)
    rows = parse_scoreboard(payload, league)
    log.info("date=%s league=%s rows=%d", date, league, len(rows))
    return rows


# ---------------------------------------------------------------------------
# Ingest range — writes gitignored parquet
# ---------------------------------------------------------------------------

def ingest_range(
    dates: Sequence[str],
    leagues: Sequence[str] = _LEAGUES,
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """Fetch ESPN tennis matches for *dates* (YYYYMMDD) and write/merge a parquet.

    One row per player per competition; dedup on (comp_id, player_name) keep last.
    Descriptive/realized only — NOT a model input without as-of join.
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    rows: List[dict] = []
    for date in dates:
        for league in leagues:
            rows.extend(fetch_scoreboard(date, league, http_get=getter))

    new_df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if out.exists() and not new_df.empty:
        try:
            existing = pd.read_parquet(out)
            new_df = (
                pd.concat([existing, new_df], ignore_index=True)
                .drop_duplicates(subset=["comp_id", "player_name"], keep="last")
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Could not read existing parquet %s: %s — overwriting", out, exc
            )

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

    parser = argparse.ArgumentParser(description="Ingest ESPN tennis scoreboard.")
    parser.add_argument("--dates", nargs="+", default=[dt.date.today().strftime("%Y%m%d")])
    parser.add_argument("--leagues", nargs="+", default=list(_LEAGUES))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path = ingest_range(args.dates, leagues=args.leagues, out_path=args.out)
    print(f"Done: {path}")


if __name__ == "__main__":
    _main()
