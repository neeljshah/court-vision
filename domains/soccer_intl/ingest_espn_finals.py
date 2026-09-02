"""domains.soccer_intl.ingest_espn_finals -- ESPN free-API World Cup FINAL score
ingestion (the settle-side counterpart to domains.mlb.ingest_espn_box).

WHY THIS EXISTS
----------------
The in-game paper settle arm needs each Kalshi WC ticker's realized final score,
oriented the SAME way the capture loop assigned home/away when the bet was placed
(ESPN's homeAway on the live scoreboard). The historical data/domains/soccer_intl/
results.parquet corpus (a separate all-time results dataset) is (a) stale -- it has
not been refreshed past 2026-06-27 -- and (b) sourced independently, so its
home/away convention for a neutral-site tournament match is NOT guaranteed to
match ESPN's; reusing it risks a silently swapped side. This module instead reads
ESPN's OWN scoreboard (the same provider ingame_live_state already reads for live
state) so the settle-side final score always agrees with the placement-side home/
away label.

Endpoint (free, no auth): scoreboard only -- ESPN's soccer scoreboard already
carries each competitor's final score + homeAway + a completed flag, so (unlike
MLB) no per-event summary fetch is needed.
  https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard?dates=YYYYMMDD

Network isolation: http_get is INJECTABLE; no network at import time.

KNOWLEDGE/SUBSTRATE ONLY -- NOT a model-feed signal. Realized final scores for
settlement, joined as-of by SoccerOutcomeResolver. No $/edge claim.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer_intl/test_ingest_espn_finals.py -q
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
_SCOREBOARD_URL = ("https://site.api.espn.com/apis/site/v2/sports/soccer/"
                    "{league}/scoreboard?dates={date}")
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "espn_finals.parquet"
_DEFAULT_LEAGUE = "fifa.world"


def _default_http_get(url: str) -> dict:
    """Fetch url via urllib; returns {} on any error."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        log.warning("ESPN fetch failed url=%s err=%s", url, exc)
        return {}


def _parse_event(ev: dict, date: str) -> dict:
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
    return {
        "event_id": str(ev.get("id") or ""),
        "date": date,
        "home_team": names["home"], "away_team": names["away"],
        "home_score": scores["home"], "away_score": scores["away"],
        "status_name": str(typ.get("name") or ""),
        "completed": bool(typ.get("completed")),
    }


def fetch_finals(date: str, league: str = _DEFAULT_LEAGUE,
                  http_get: Optional[Callable] = None) -> List[dict]:
    """Parsed rows for every event on *date* (YYYYMMDD) whose ESPN status is
    completed=True. An in-progress/scheduled event is skipped (never a partial
    score persisted as final)."""
    getter = http_get or _default_http_get
    payload = getter(_SCOREBOARD_URL.format(league=league, date=date))
    rows: List[dict] = []
    for ev in payload.get("events") or []:
        row = _parse_event(ev, date)
        if not row:
            continue
        if not row.get("completed"):
            log.debug("event_id=%s: not completed (status=%s) -- skipped",
                      row.get("event_id"), row.get("status_name"))
            continue
        rows.append(row)
    return rows


def ingest_range(
    dates: Sequence[str],
    league: str = _DEFAULT_LEAGUE,
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """Fetch ESPN WC final scores for *dates* (YYYYMMDD) and write/merge a parquet.

    One row per event; dedup on event_id (keep last). Descriptive/realized only --
    the label SoccerOutcomeResolver joins as-of, never an edge/ROI claim.
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    rows: List[dict] = []
    for date in dates:
        got = fetch_finals(date, league=league, http_get=getter)
        log.info("date=%s finals=%d", date, len(got))
        rows.extend(got)

    new_df = pd.DataFrame(rows) if rows else pd.DataFrame()
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
        write_parquet_atomic(new_df, out)
    log.info("Wrote %d rows to %s", len(new_df), out)
    return out


def _main() -> None:
    import argparse
    import datetime as dt
    parser = argparse.ArgumentParser(description="Ingest ESPN World Cup final scores.")
    parser.add_argument("--dates", nargs="+", default=[dt.date.today().strftime("%Y%m%d")])
    parser.add_argument("--league", default=_DEFAULT_LEAGUE)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(f"Done: {ingest_range(args.dates, league=args.league, out_path=args.out)}")


if __name__ == "__main__":
    _main()


__all__ = ["fetch_finals", "ingest_range", "_DEFAULT_OUT", "_DEFAULT_LEAGUE"]
