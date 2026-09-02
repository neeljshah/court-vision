"""domains.basketball_wnba.ingest_espn -- ESPN free-API WNBA scoreboard ingestion.

WHY THIS EXISTS
----------------
NBA-brand hosts (stats.nba.com / cdn.nba.com) are blocked on this box; ESPN's
site.api is the sanctioned keyless route (see domains/soccer_intl/ingest_espn_finals.py
and domains/tennis/ingest_espn.py for the same pattern on other sports). This module
is the WNBA settle-side final-score ingest: one row per completed game, oriented by
ESPN's own homeAway label so home/away is never guessed or silently swapped.

Endpoints (free, no auth):
  scoreboard (single day):  https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates=YYYYMMDD
  scoreboard (season index): https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates=YYYY
    -- returns leagues[0].calendar: a list of ISO date-times, one per date with a
    game (regular season + playoffs). Probed live 2026-07-03: 2024 -> 109 dates
    (2024-05-03..2024-10-20), 2025 -> 126 dates (2025-05-02..2025-10-10), 2026 ->
    121 dates (2026-04-25..2026-09-24, in progress). Using this index instead of a
    blind day-by-day walk cuts request count by >2x and is the polite-pacing route.

Schema confirmed 2026-07-02 against a live 2026 scoreboard payload: competitions[0]
.competitors[] carries homeAway ("home"/"away"), score (str), team.displayName;
competitions[0].status.type carries name + completed (bool); competitions[0]
.neutralSite (bool, present on some events).

Network isolation: http_get is INJECTABLE; no network at import time.

KNOWLEDGE/SUBSTRATE ONLY -- NOT a model-feed signal by itself; the adapter's Elo
replay consumes the home_win label built here. No $/edge claim.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingest_espn.py -q
"""
from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_TIMEOUT = 12
_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates={date}"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "wnba" / "espn_scoreboard.parquet"

GAMES_COLS: tuple = (
    "event_id", "date", "season", "home_team", "away_team",
    "home_score", "away_score", "home_win", "neutral_site", "status_name",
)


def _default_http_get(url: str) -> dict:
    """Fetch url via urllib; returns {} on any error (never raises)."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        log.warning("ESPN fetch failed url=%s err=%s", url, exc)
        return {}


def season_calendar(year: str, http_get: Optional[Callable] = None) -> List[str]:
    """Every YYYYMMDD date the *year* season index reports a game on, or [].

    Reads leagues[0].calendar from the yearly scoreboard query (a season-date
    index, not a fixture list). Pure date extraction -- malformed/absent calendar
    entries are silently skipped, never raise.
    """
    getter = http_get or _default_http_get
    payload = getter(_SCOREBOARD_URL.format(date=year))
    leagues = payload.get("leagues") or []
    if not leagues:
        return []
    calendar = leagues[0].get("calendar") or []
    out: List[str] = []
    for entry in calendar:
        try:
            out.append(str(entry)[:10].replace("-", ""))
        except (TypeError, ValueError):
            continue
    return out


def _parse_event(ev: dict, date: str, season: str) -> dict:
    """One ESPN scoreboard event -> a flat final-score row, or {} if unusable.

    PURE -- no I/O. Only a competitor pair with BOTH homeAway sides present and a
    numeric score on each side is kept; a partial/malformed event is skipped
    (never a fabricated 0-0).
    """
    comps = ev.get("competitions") or []
    if not comps:
        return {}
    comp = comps[0]
    status = comp.get("status") or {}
    typ = status.get("type") or {}
    scores: Dict[str, Optional[float]] = {}
    names: Dict[str, str] = {}
    for c in comp.get("competitors") or []:
        side = c.get("homeAway")
        if side not in ("home", "away"):
            continue
        try:
            scores[side] = float(c.get("score"))
        except (TypeError, ValueError):
            scores[side] = None
        names[side] = ((c.get("team") or {}).get("displayName") or "").strip()
    if "home" not in scores or "away" not in scores:
        return {}
    if scores["home"] is None or scores["away"] is None:
        return {}
    if not names.get("home") or not names.get("away"):
        return {}
    home_score, away_score = scores["home"], scores["away"]
    return {
        "event_id": str(ev.get("id") or ""),
        "date": date,
        "season": season,
        "home_team": names["home"], "away_team": names["away"],
        "home_score": home_score, "away_score": away_score,
        "home_win": 1.0 if home_score > away_score else (
            0.0 if home_score < away_score else float("nan")),
        "neutral_site": bool(comp.get("neutralSite", False)),
        "status_name": str(typ.get("name") or ""),
        "completed": bool(typ.get("completed")),
    }


def fetch_day(date: str, season: str, http_get: Optional[Callable] = None) -> List[dict]:
    """Parsed rows for every COMPLETED event on *date* (YYYYMMDD).

    An in-progress/scheduled event is skipped (never a partial score persisted as
    final). *season* is the caller's label (e.g. "2024"), stamped verbatim.
    """
    getter = http_get or _default_http_get
    payload = getter(_SCOREBOARD_URL.format(date=date))
    rows: List[dict] = []
    for ev in payload.get("events") or []:
        row = _parse_event(ev, date, season)
        if not row:
            continue
        if not row.pop("completed"):
            log.debug("event_id=%s: not completed (status=%s) -- skipped",
                      row.get("event_id"), row.get("status_name"))
            continue
        rows.append(row)
    return rows


def ingest_season(
    year: str,
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
    dates_override: Optional[Sequence[str]] = None,
) -> Path:
    """Backfill one WNBA *year* season (regular + playoffs) via the calendar index,
    then per-date scoreboard fetch, merged/deduped into the parquet at out_path.

    *dates_override* lets a test/caller skip the two-call (calendar + per-date)
    chain and inject dates directly. One row per event_id; dedup keeps the latest
    (a re-run with corrected/updated scores overwrites the stale row).
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    dates = list(dates_override) if dates_override is not None else season_calendar(year, http_get=getter)
    rows: List[dict] = []
    for date in dates:
        got = fetch_day(date, year, http_get=getter)
        log.info("season=%s date=%s finals=%d", year, date, len(got))
        rows.extend(got)

    new_df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=list(GAMES_COLS))
    if not new_df.empty and "date" in new_df.columns:
        new_df["date"] = pd.to_datetime(new_df["date"], format="mixed", errors="coerce")
    if out.exists() and not new_df.empty:
        try:
            existing = pd.read_parquet(out)
            if "date" in existing.columns:
                existing["date"] = pd.to_datetime(existing["date"], format="mixed", errors="coerce")
            new_df = (pd.concat([existing, new_df], ignore_index=True)
                      .drop_duplicates(subset=["event_id"], keep="last"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("S95: unreadable existing parquet %s" % out) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    if not new_df.empty:
        new_df = new_df.sort_values(["date", "event_id"], kind="mergesort").reset_index(drop=True)
        write_parquet_atomic(new_df, out)
    log.info("Wrote %d rows to %s", len(new_df), out)
    return out


def ingest_seasons(
    years: Sequence[str],
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """Backfill multiple seasons in sequence into the SAME parquet (dedup on event_id
    across the whole call). Convenience wrapper around repeated ingest_season calls."""
    out = Path(out_path) if out_path else _DEFAULT_OUT
    for year in years:
        ingest_season(year, http_get=http_get, out_path=out)
    return out


def _main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Ingest ESPN WNBA scoreboard finals.")
    parser.add_argument("--years", nargs="+", default=["2024", "2025", "2026"])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    dest = ingest_seasons(args.years, out_path=args.out)
    df = pd.read_parquet(dest)
    print(f"Done: {dest} -- {len(df)} total rows across seasons {sorted(df['season'].unique().tolist())}")
    for s in sorted(df["season"].unique().tolist()):
        n = int((df["season"] == s).sum())
        print(f"  season={s}: {n} games")


if __name__ == "__main__":
    _main()


__all__ = ["fetch_day", "season_calendar", "ingest_season", "ingest_seasons",
           "_DEFAULT_OUT", "GAMES_COLS"]
