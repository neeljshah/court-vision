"""scripts.platformkit.omni.close_lookup -- historical pregame devigged close.

``pregame_close(sport, game_date, home, away)`` -> ``{"prob_home_devig": float,
"source": "kalshi"|"polymarket", "ts": int}`` or ``None``.

Reads the settled-market tick corpus already on disk
(``data/cache/inplay_odds/<sport>_price_series.parquet``, Kalshi + Polymarket
venues in one file) -- no new corpus, no new fetch. Missing = ``None``, never
fabricated (matches ``grade_paper_close.close_from_store``'s own contract).

CLOSE DEFINITION -- last tick strictly BEFORE a per-event start-time proxy:

1. Kalshi tickers for MLB embed an HHMM scheduled time
   (``KXMLBGAME-<YY><MON><DD><HHMM><AWAY><HOME>``, e.g. ...1835SEABAL,
   ...1310BOSTB -- verified live 2026-07-13 against this store's own MLB
   tickers: the HHMM values are plausible ET first-pitch times). Parsed as ET
   (fixed UTC-4 / EDT -- this store's Apr-Jul window is always in EDT, a
   documented simplification) and converted to UTC; used directly.
2. Otherwise (NBA Kalshi tickers carry no HHMM; Polymarket slugs carry only a
   date) -- conservative fallback: 00:00:00 UTC of the ticker/slug's OWN
   embedded date, NOT the store's ``game_date`` column. The column is a
   capture-bucket date and can roll past midnight (the documented UTC/ET
   trap): ``KXNBAGAME-26APR26BOSPHI`` embeds Apr 26 while its own
   ``game_date`` rows say ``2026-04-27`` -- verified live on this exact event.
   00:00 UTC of the ET game date is always hours before any real tip-off
   (even the earliest afternoon games), so this never admits a mid-game tick
   -- it trades freshness for safety and is documented as such, never
   claimed as the true closing number.

Team resolution reuses ``scripts.platformkit.odds_provider.team_resolver
.canonical`` (existing 30-team alias tables) -- no new mapping invented.

Devig: proportional normalize (``ih / (ih + ia)``) when both home- and
away-side ticks exist before cutoff (Kalshi captures both legs). Polymarket
rows in this store carry only the home side, so its close is that single
quoted probability, undevigged -- documented, matches
``kx_close_fallback``'s existing single-leg convention for Kalshi binaries.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; never
raises; never claims an edge (calibration reference only).
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from scripts.platformkit.odds_provider.team_resolver import canonical

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STORE_DIR = _REPO_ROOT / "data" / "cache" / "inplay_odds"
_CACHE: Dict[str, pd.DataFrame] = {}

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL",
     "AUG", "SEP", "OCT", "NOV", "DEC"])}
_TICKER_DATE_RE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(\d{4})?")
_SLUG_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})$")


def _load(sport: str) -> Optional[pd.DataFrame]:
    """Cached, moneyline-only frame for a sport's price-series store, or None."""
    if sport in _CACHE:
        return _CACHE[sport]
    path = _STORE_DIR / f"{sport}_price_series.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df = df[df["market_type"] == "moneyline"].copy()
    _CACHE[sport] = df
    return df


def _ticker_anchor(ticker: str) -> Optional[tuple]:
    """(embedded_local_date, utc_start_proxy) parsed from a Kalshi ticker, or
    None. embedded_local_date is the ticker's OWN date component (ET calendar
    date), used for the query-date match so a UTC-rollover shift in the HHMM
    conversion never causes a false date mismatch."""
    m = _TICKER_DATE_RE.search(ticker)
    if not m:
        return None
    yy, mon, dd, hhmm = m.groups()
    mon_n = _MONTHS.get(mon)
    if mon_n is None:
        return None
    try:
        local_date = dt.date(2000 + int(yy), mon_n, int(dd))
        if hhmm:
            hh, mm = int(hhmm[:2]), int(hhmm[2:])
            if not (0 <= hh < 24 and 0 <= mm < 60):
                raise ValueError("bad HHMM")
            local = dt.datetime(local_date.year, local_date.month, local_date.day, hh, mm)
            utc_proxy = local + dt.timedelta(hours=4)  # ET -> UTC, EDT fixed offset
        else:
            utc_proxy = dt.datetime(local_date.year, local_date.month, local_date.day)
        return (local_date, utc_proxy)
    except ValueError:
        return None


def _slug_anchor(slug: str) -> Optional[tuple]:
    """(embedded_date, 00:00-UTC start-proxy) from a Polymarket slug's own
    trailing ISO date, or None."""
    m = _SLUG_DATE_RE.search(slug)
    if not m:
        return None
    try:
        d = dt.datetime.strptime(m.group(1), "%Y-%m-%d")
        return (d.date(), d)
    except ValueError:
        return None


def _devig(home_p: Optional[float], away_p: Optional[float]) -> Optional[float]:
    if home_p is None or not (0.0 < home_p < 1.0):
        return None
    if away_p is None or not (0.0 < away_p < 1.0):
        return home_p  # single-sided quote (Polymarket store) -- undevigged
    tot = home_p + away_p
    return (home_p / tot) if tot > 0 else None


def _last_before(rows: pd.DataFrame, cutoff_ts: int) -> Optional[pd.Series]:
    before = rows[rows["ts"] < cutoff_ts]
    if before.empty:
        return None
    return before.loc[before["ts"].idxmax()]


def _kalshi_close(grp: pd.DataFrame, home_key: str, away_key: str,
                   sport: str, cutoff_ts: int) -> Optional[Dict[str, Any]]:
    sides = grp["side"].unique()
    home_side = next((s for s in sides if canonical(sport, s) == home_key), None)
    if home_side is None:
        return None
    hrow = _last_before(grp[grp["side"] == home_side], cutoff_ts)
    if hrow is None:
        return None
    away_side = next((s for s in sides if canonical(sport, s) == away_key), None)
    away_p = None
    if away_side is not None:
        arow = _last_before(grp[grp["side"] == away_side], cutoff_ts)
        if arow is not None:
            away_p = float(arow["prob"])
    p = _devig(float(hrow["prob"]), away_p)
    if p is None:
        return None
    return {"prob_home_devig": p, "source": "kalshi", "ts": int(hrow["ts"])}


def _polymarket_close(grp: pd.DataFrame, slug: str, home_key: str, away_key: str,
                       sport: str, cutoff_ts: int) -> Optional[Dict[str, Any]]:
    parts = slug.split("-")
    if len(parts) < 4:
        return None
    away_tok, home_tok = parts[1], parts[2]
    if canonical(sport, home_tok) != home_key or canonical(sport, away_tok) != away_key:
        return None
    hrow = _last_before(grp, cutoff_ts)
    if hrow is None:
        return None
    # ORIENTATION (P1-D review fix, verified 2026-07-13): the store's PM
    # `prob` column tracks the slug's FIRST team -- the corpus AWAY team.
    # Settlement check across every matched settled game: NBA 1281/1281 and
    # MLB 664/666 (2 doubleheader collisions) show prob -> ~1.0 iff the
    # slug-first (away) team won. The store's side='home' label refers to
    # slug position, not the corpus home team. Corpus HOME prob = complement.
    p = _devig(1.0 - float(hrow["prob"]), None)
    if p is None:
        return None
    return {"prob_home_devig": p, "source": "polymarket", "ts": int(hrow["ts"])}


def _venue_close(day_df: pd.DataFrame, venue: str, d: str, home_key: str,
                  away_key: str, sport: str) -> Optional[Dict[str, Any]]:
    v = day_df[day_df["venue"] == venue]
    if v.empty:
        return None
    query_date = dt.datetime.strptime(d, "%Y-%m-%d").date()
    # Kalshi's event_key is per-game (its ticker_or_slug is per-SIDE within it);
    # Polymarket's event_key is a shared per-DAY bucket ("nba-dailies-<date>"),
    # so the per-game unit there is ticker_or_slug itself -- group on the
    # column that is actually per-game for each venue (verified live: PM
    # event_key == "nba-dailies-2023-04-09" for all 15 games that date).
    group_col = "event_key" if venue == "kalshi" else "ticker_or_slug"
    for event_key, grp in v.groupby(group_col):
        ek = str(event_key)
        anchor = _ticker_anchor(ek) if venue == "kalshi" else _slug_anchor(ek)
        if anchor is None:
            continue
        embedded_date, utc_proxy = anchor
        if embedded_date != query_date:
            continue
        cutoff_ts = int(utc_proxy.replace(tzinfo=dt.timezone.utc).timestamp())
        if venue == "kalshi":
            res = _kalshi_close(grp, home_key, away_key, sport, cutoff_ts)
        else:
            res = _polymarket_close(grp, ek, home_key, away_key, sport, cutoff_ts)
        if res is not None:
            return res
    return None


def pregame_close(sport: str, game_date: str, home: str, away: str) -> Optional[Dict[str, Any]]:
    """Last-before-start devigged home win prob for (sport, date, home, away).

    Missing = None (unmapped team, no captured line for that date/matchup, or
    any lookup failure) -- never fabricated. Prefers Kalshi, falls back to
    Polymarket. Never raises.
    """
    try:
        sport = str(sport).strip().lower()
        df = _load(sport)
        if df is None or df.empty:
            return None
        home_key, away_key = canonical(sport, home), canonical(sport, away)
        d = str(game_date)[:10]
        lo = (pd.to_datetime(d) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        hi = (pd.to_datetime(d) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        day_df = df[df["game_date"].between(lo, hi)]
        if day_df.empty:
            return None
        for venue in ("kalshi", "polymarket"):
            res = _venue_close(day_df, venue, d, home_key, away_key, sport)
            if res is not None:
                return res
        return None
    except Exception:  # noqa: BLE001 -- an honest miss, never a crash
        return None


__all__ = ["pregame_close"]
