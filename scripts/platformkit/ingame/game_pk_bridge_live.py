"""scripts.platformkit.ingame.game_pk_bridge_live -- LIVE 3-way MLB id bridge
(statsapi gamePk <-> ESPN event id <-> Kalshi KXMLBGAME ticker) for TODAY's slate.

NOT the historical corpus bridge (domains/mlb/game_pk_bridge.py, which maps
game_pk -> games_current.event_id for the 2022+ backtest parquet corpus via a
date+team-pair key). This module is the LIVE-SLATE twin: it hits the three real
feeds for a given date and emits one row per statsapi game with whichever of
{espn_id, kalshi_ticker_stem} it can UNAMBIGUOUSLY resolve.

JOIN KEY: (date, sorted canonical team-pair) via domains.mlb.team_name_resolver
(the existing ESPN-name -> canonical-key resolver -- REUSED, not duplicated).
statsapi gives full team names (e.g. "Chicago White Sox"); ESPN's scoreboard
gives BOTH a displayName ("Chicago White Sox") and its own abbreviation
("CHW", which is NOT in team_name_resolver's alias table -- verified live
2026-07-03) -- so this bridge always resolves via displayName, never the raw
ESPN abbreviation. Kalshi tickers encode their OWN abbreviation dialect
(KALSHI_ABBR in ingame_id_resolver_mlb, e.g. "CWS" not "CHW", "AZ" not "ARI")
-- REUSED from that module rather than re-derived.

Espn-matching approach mirrors espn_wp_backfill_measure.resolve_event_id (one
scoreboard GET per date, then match by competitor identity) but matches on the
canonical team-pair key instead of a dialect-specific abbrev-concat string, so
it works regardless of which of the three dialects supplied the ticker.

AMBIGUITY GUARDS (binding, never guessed):
  * A statsapi game whose two team names cannot BOTH resolve to a canonical
    key -> both ids left None (cannot safely key it).
  * >1 ESPN event or >1 Kalshi ticker sharing the same (date, team-pair) key
    (e.g. a live doubleheader) -> that id left None for every game sharing the
    key (never guess which half).
  * Kalshi tickers are matched by their OWN encoded date (from the ticker
    string), not the caller's *date* arg, so a ticker for tomorrow's slate
    (already open pregame) never mismatches into today's row.

Cache: data/domains/mlb/game_pk_bridge/<date>.json (one row list); best-effort,
never required for the live probe.

INVARIANTS: scripts/platformkit/ingame/ only; <=300 LOC; ASCII only; no
src/kernel/api imports; stdlib + repo-internal only; no $ / edge claim
(id-join coverage only).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/ingame/test_game_pk_bridge_live.py -q
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.ingame.ingame_id_resolver_mlb import (
    KALSHI_ABBR, parse_kalshi_mlb_ticker,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CACHE_DIR = _REPO_ROOT / "data" / "domains" / "mlb" / "game_pk_bridge"

_UA = "curl/8.0"  # plain UA: ESPN 403s non-tool UAs from datacenter IPs (2026-08-31)
_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}"
_ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates={yyyymmdd}"
)
_KALSHI_MARKETS_URL = (
    "https://api.elections.kalshi.com/trade-api/v2/markets"
    "?series_ticker=KXMLBGAME&status=open&limit=200"
)

HttpGet = Callable[[str], Any]


def _http_get_json(url: str, timeout: float = 10.0) -> Optional[Any]:
    """GET url, return parsed JSON or None on any failure. Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            ValueError, OSError) as exc:
        logger.debug("game_pk_bridge_live GET failed url=%s: %s", url, exc)
        return None


def _canon(name: Any) -> Optional[str]:
    """team_name_resolver.resolve, degraded to None on any import/lookup issue."""
    try:
        from domains.mlb.team_name_resolver import resolve
        return resolve(str(name or ""))
    except Exception as exc:  # noqa: BLE001 -- an unresolved name is an honest miss
        logger.debug("game_pk_bridge_live team resolve failed for %r: %s", name, exc)
        return None


def _pair_key(away: Any, home: Any) -> Optional[str]:
    a, h = _canon(away), _canon(home)
    if not a or not h:
        return None
    return "|".join(sorted((a, h)))


@dataclass(frozen=True)
class BridgeRow:
    """One statsapi game's resolved ids for the date. None fields are honest misses."""

    game_pk: int
    date: str
    away: str
    home: str
    espn_id: Optional[str]
    kalshi_ticker_stem: Optional[str]


def _fetch_statsapi_games(date_str: str, http: HttpGet) -> List[Dict[str, Any]]:
    """[{game_pk, away, home}] for every scheduled game on *date_str* (any status).
    Never raises; [] on any feed failure."""
    data = http(_SCHEDULE_URL.format(date=date_str))
    if not isinstance(data, dict):
        return []
    out: List[Dict[str, Any]] = []
    for d in data.get("dates", []) or []:
        for g in d.get("games", []) or []:
            teams = g.get("teams", {}) or {}
            away = (teams.get("away", {}).get("team", {}) or {}).get("name")
            home = (teams.get("home", {}).get("team", {}) or {}).get("name")
            if g.get("gamePk") is None or not away or not home:
                continue
            out.append({"game_pk": g["gamePk"], "away": away, "home": home})
    return out


def _fetch_espn_events(date_str: str, http: HttpGet) -> Dict[str, List[str]]:
    """pair_key -> [espn_event_id, ...] for *date_str* (YYYY-MM-DD). A key with
    >1 event id is an ambiguous (doubleheader) key -- caller must never guess
    which one. Never raises; {} on any feed failure."""
    yyyymmdd = date_str.replace("-", "")
    data = http(_ESPN_SCOREBOARD_URL.format(yyyymmdd=yyyymmdd))
    if not isinstance(data, dict):
        return {}
    out: Dict[str, List[str]] = {}
    for e in data.get("events", []) or []:
        comps = (e.get("competitions") or [{}])[0].get("competitors", [])
        names = {c.get("homeAway"): (c.get("team", {}) or {}).get("displayName")
                 for c in comps if isinstance(c, dict)}
        key = _pair_key(names.get("away"), names.get("home"))
        eid = e.get("id")
        if key is None or eid is None:
            continue
        out.setdefault(key, []).append(str(eid))
    return out


def _fetch_kalshi_tickers(http: HttpGet) -> List[str]:
    """All currently-open KXMLBGAME tickers. Never raises; [] on any feed failure."""
    data = http(_KALSHI_MARKETS_URL)
    if not isinstance(data, dict):
        return []
    tickers = set()
    for m in data.get("markets", []) or []:
        if isinstance(m, dict) and m.get("ticker"):
            # ticker stem is the event_ticker (drop any trailing -T<n>/-side suffix);
            # event_ticker itself is already the KXMLBGAME-<...> stem when present.
            stem = m.get("event_ticker") or str(m["ticker"]).rsplit("-", 1)[0]
            tickers.add(str(stem))
    return sorted(tickers)


def _kalshi_pair_key(ticker_stem: str) -> Optional[Tuple[str, Optional[str]]]:
    """(pair_key, ticker_date_yyyymmdd) for a KXMLBGAME ticker stem, or None if
    unparseable / either team is outside KALSHI_ABBR's reverse map."""
    parsed = parse_kalshi_mlb_ticker(ticker_stem)
    if parsed is None:
        return None
    blob = parsed["blob"]
    # KALSHI_ABBR maps full-name(lower) -> abbrev; invert once per call (small table).
    abbr_to_name = {v: k for k, v in KALSHI_ABBR.items()}
    # Kalshi abbrevs are 2-3 chars; try longest-first split so e.g. "AZTB" splits AZ+TB
    # and "CWSCLE" splits CWS+CLE unambiguously against the known abbrev set.
    abbrevs = sorted(KALSHI_ABBR.values(), key=len, reverse=True)
    for a_len_first in abbrevs:
        if blob.startswith(a_len_first):
            rest = blob[len(a_len_first):]
            if rest in KALSHI_ABBR.values():
                away_name = abbr_to_name[a_len_first]
                home_name = abbr_to_name[rest]
                key = _pair_key(away_name, home_name)
                if key is not None:
                    month = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
                              "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
                              "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"
                              }.get(parsed["mon"], None)
                    tdate = f"20{parsed['yy']}{month}{parsed['dd']}" if month else None
                    return key, tdate
    return None


def build_bridge(date_str: Optional[str] = None, *,
                 http: HttpGet = _http_get_json) -> List[BridgeRow]:
    """Build the unambiguous 3-way bridge rows for *date_str* (default: today UTC).

    Emits one BridgeRow per statsapi-scheduled game. Each of espn_id /
    kalshi_ticker_stem is None whenever the (date, team-pair) key is unresolved,
    unmatched, or AMBIGUOUS (shared by >1 candidate) -- never guessed.
    """
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    games = _fetch_statsapi_games(date_str, http)
    espn_by_key = _fetch_espn_events(date_str, http)

    kalshi_by_key: Dict[str, List[str]] = {}
    for stem in _fetch_kalshi_tickers(http):
        parsed = _kalshi_pair_key(stem)
        if parsed is None:
            continue
        key, tdate = parsed
        if tdate is not None and tdate != date_str.replace("-", ""):
            continue  # ticker belongs to a different date's slate -- never mismatch in
        kalshi_by_key.setdefault(key, []).append(stem)

    rows: List[BridgeRow] = []
    for g in games:
        key = _pair_key(g["away"], g["home"])
        espn_id = None
        kalshi_stem = None
        if key is not None:
            eids = espn_by_key.get(key)
            if eids and len(eids) == 1:
                espn_id = eids[0]
            ktix = kalshi_by_key.get(key)
            if ktix and len(ktix) == 1:
                kalshi_stem = ktix[0]
        rows.append(BridgeRow(
            game_pk=int(g["game_pk"]), date=date_str, away=g["away"], home=g["home"],
            espn_id=espn_id, kalshi_ticker_stem=kalshi_stem,
        ))
    return rows


def write_cache(rows: List[BridgeRow], date_str: str) -> None:
    """Best-effort cache write to data/domains/mlb/game_pk_bridge/<date>.json.
    Never raises (a cache-write failure never blocks the live report)."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _CACHE_DIR / f"{date_str}.json"
        out_path.write_text(
            json.dumps([asdict(r) for r in rows], indent=1), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.debug("game_pk_bridge_live cache write failed: %s", exc)


def summarize(rows: List[BridgeRow]) -> Dict[str, Any]:
    n = len(rows)
    n_all_three = sum(1 for r in rows if r.espn_id and r.kalshi_ticker_stem)
    n_espn = sum(1 for r in rows if r.espn_id)
    n_kalshi = sum(1 for r in rows if r.kalshi_ticker_stem)
    return {"n_games": n, "n_bridged_all_three": n_all_three,
            "n_espn_resolved": n_espn, "n_kalshi_resolved": n_kalshi}


def _main() -> int:  # pragma: no cover -- CLI smoke, not exercised by tests
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today UTC)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = build_bridge(date_str)
    if not args.no_cache:
        write_cache(rows, date_str)
    print(json.dumps({"date": date_str, "summary": summarize(rows),
                      "rows": [asdict(r) for r in rows]}, indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = [
    "BridgeRow", "build_bridge", "write_cache", "summarize",
]
