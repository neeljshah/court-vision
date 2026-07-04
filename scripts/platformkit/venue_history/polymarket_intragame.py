"""scripts.platformkit.venue_history.polymarket_intragame -- Polymarket gamma-api
per-game intra-game price-path backfill (LANE 1).

RECIPE (scout-verified, see memory reference_ingame_data_sources_2026_07_04):
  1. Search (GET /public-search?q=<sport> dailies&events_status=closed) is FUZZY
     (relevance-ranked, not literal date match) -- used only to discover the slug
     FAMILY (<sport>-dailies-YYYY-MM-DD); actual enumeration walks day-by-day and
     confirms each day via EXACT-slug GET /events?slug=<sport>-dailies-<date>.
  2. clobTokenIds/outcomes/outcomePrices are JSON-ENCODED STRINGS -- json.loads,
     not literal lists.
  3. GET clob.polymarket.com/prices-history?market=<token>&startTs=&endTs=&
     fidelity=1 -- EXPLICIT ts only; interval= shorthand silently returns [] on
     old markets. One side's token suffices (other side = 1-p).
  4. Outcome: a CLOSED market's outcomePrices settle to exactly ["1","0"] or
     ["0","1"]; anything else (unresolved / draw-shaped 0.5/0.5 / not closed) is
     ambiguous -> outcome=None, never guessed.

REAL AVAILABILITY (verified live 2026-07 by direct day-by-day slug probing):
  Polymarket's per-game "dailies" markets are NOT a continuous multi-season
  series -- MLB exists only as a short 2023 pilot (dense ~2023-03-30..05-24,
  off-days missing); NBA clusters similarly around 2023, not 2024/2025. No
  evidence of MLB-2024 dailies on this venue -- the brief's "MLB 2024" premise
  does not hold against the live API. This runs the REAL confirmed MLB 2023
  window instead (reported honestly); date/sport-parameterized so a later
  Polymarket resumption needs no code change.

PROVENANCE (binding): VALIDATION corpus, physically separate from Lane 2
(Kalshi) and the forward pre-registered tail gates. Never pooled forward.

Politeness: 1 req/s (sleep injected, tests instant); resumable JSON progress
sidecar so an interrupted run continues from its last confirmed date.

Output: data/venue_history/polymarket/<sport>/<date>_<eventslug>.jsonl, one
JSON doc per GAME market: {date, event_slug, market_slug, sport, home, away,
outcome_home_win: 0|1|None, closed, token_home, prices: [{ts, prob_home}]}.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; stdlib only; no $-edge claims;
no data/registry writes; no flag flips.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_polymarket_intragame.py -q
"""
from __future__ import annotations

import json
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.odds_provider.http_cache import http_get_json
from scripts.platformkit.venue_history.progress_sidecar import load_progress, save_progress

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "venue_history" / "polymarket"
DEFAULT_PROGRESS = DEFAULT_OUT_DIR / "_progress.json"

HttpGet = Callable[[str], Any]

# Confirmed-live real windows (see module docstring) -- used as the default
# range for run_backfill when the caller does not pass explicit dates.
DEFAULT_MLB_START = "2023-03-30"
DEFAULT_MLB_END = "2023-05-24"


def _get(http: HttpGet, url: str) -> Optional[Any]:
    try:
        return http(url)
    except Exception:  # noqa: BLE001 -- a failed call must not kill the whole run
        return None


def _as_list(value: Any) -> List[Any]:
    """clobTokenIds / outcomes / outcomePrices are JSON-ENCODED STRINGS on gamma."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def fetch_dailies_event(sport: str, date: str, *, http: HttpGet = http_get_json) -> Optional[Dict[str, Any]]:
    """Exact-slug lookup for <sport>-dailies-<date>; None if that day has no event.
    Exact slug lookup is authoritative (unlike the fuzzy public-search)."""
    slug = "%s-dailies-%s" % (sport.lower(), date)
    url = "%s/events?slug=%s" % (GAMMA_BASE, urllib.parse.quote(slug))
    body = _get(http, url)
    if not isinstance(body, list) or not body:
        return None
    return body[0]


def _resolve_outcome(market: Dict[str, Any]) -> Optional[int]:
    """A CLOSED market's outcomePrices settle to exactly ["1","0"]/["0","1"].
    Anything else (open, a draw-shaped 0.5/0.5, unparseable) -> None, never guessed."""
    if not market.get("closed"):
        return None
    prices = _as_list(market.get("outcomePrices"))
    if len(prices) != 2:
        return None
    try:
        p0, p1 = float(prices[0]), float(prices[1])
    except (TypeError, ValueError):
        return None
    if p0 == 1.0 and p1 == 0.0:
        return 1
    if p0 == 0.0 and p1 == 1.0:
        return 0
    return None


def fetch_price_history(token: str, start_ts: int, end_ts: int, *,
                        fidelity: int = 1, http: HttpGet = http_get_json) -> List[Dict[str, Any]]:
    """1-min price path for one clob token over [start_ts, end_ts] (EXPLICIT ts)."""
    params = urllib.parse.urlencode({
        "market": token, "startTs": int(start_ts), "endTs": int(end_ts),
        "fidelity": int(fidelity),
    })
    url = "%s/prices-history?%s" % (CLOB_BASE, params)
    body = _get(http, url)
    if not isinstance(body, dict):
        return []
    hist = body.get("history")
    if not isinstance(hist, list):
        return []
    out: List[Dict[str, Any]] = []
    for pt in hist:
        if not isinstance(pt, dict):
            continue
        t, p = pt.get("t"), pt.get("p")
        try:
            ts_sec, prob = int(t), float(p)
        except (TypeError, ValueError):
            continue
        if not (0.0 <= prob <= 1.0):
            continue
        iso = datetime.fromtimestamp(ts_sec, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"ts": iso, "prob_home": round(prob, 4)})
    return out


def _market_window(date: str) -> tuple:
    """[date 00:00Z, date+2d 00:00Z) -- pad past midnight for extra innings."""
    d0 = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(d0.timestamp()), int((d0 + timedelta(days=2)).timestamp())


def build_game_doc(date: str, event_slug: str, sport: str, market: Dict[str, Any],
                    *, http: HttpGet = http_get_json) -> Optional[Dict[str, Any]]:
    """One market -> the per-game JSONL doc, or None if unparseable. Fetches
    price history for the HOME (outcome[0]) token only (away = 1 - home)."""
    outcomes = [str(o).strip() for o in _as_list(market.get("outcomes"))]
    tokens = [str(t) for t in _as_list(market.get("clobTokenIds"))]
    if len(outcomes) != 2 or len(tokens) != 2:
        return None
    start_ts, end_ts = _market_window(date)
    prices = fetch_price_history(tokens[0], start_ts, end_ts, http=http)
    return {
        "date": date, "event_slug": event_slug,
        "market_slug": str(market.get("slug") or ""),
        "sport": sport, "home": outcomes[0], "away": outcomes[1],
        "outcome_home_win": _resolve_outcome(market),
        "closed": bool(market.get("closed")),
        "token_home": tokens[0],
        "n_prices": len(prices), "prices": prices,
    }


def run_backfill(
    sport: str,
    start_date: str,
    end_date: str,
    *,
    out_dir: Optional[Path] = None,
    progress_path: Optional[Path] = None,
    max_requests: int = 1500,
    sleep_sec: float = 1.0,
    http: HttpGet = http_get_json,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Bounded, resumable tranche: walk day-by-day *start_date*..*end_date*
    (inclusive), confirm each day via exact-slug lookup, fetch every game
    market's price path, write one JSONL per game-day. Resumes from
    *progress_path* (last confirmed date + counts) if present."""
    out_base = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR / sport.lower()
    prog_path = Path(progress_path) if progress_path is not None else out_base / "_progress.json"
    progress = load_progress(prog_path)
    last_date = str(progress.get("last_date_done", "")) or None

    cur = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if last_date:
        resume_from = datetime.strptime(last_date, "%Y-%m-%d").date() + timedelta(days=1)
        if resume_from > cur:
            cur = resume_from

    n_requests = 0
    n_game_days = int(progress.get("n_game_days", 0))
    n_games = int(progress.get("n_games", 0))
    n_prices = int(progress.get("n_prices", 0))
    n_off_days = int(progress.get("n_off_days", 0))
    earliest = progress.get("earliest_date_confirmed")
    latest = progress.get("latest_date_confirmed")
    budget_hit = False

    while cur <= end:
        if n_requests >= max_requests:
            budget_hit = True
            break
        date = cur.isoformat()
        event = fetch_dailies_event(sport, date, http=http)
        n_requests += 1
        sleep_fn(sleep_sec)
        if event is None:
            n_off_days += 1
            cur += timedelta(days=1)
            continue
        event_slug = str(event.get("slug") or "")
        markets = event.get("markets") or []
        docs: List[Dict[str, Any]] = []
        for m in markets:
            if n_requests >= max_requests:
                budget_hit = True
                break
            doc = build_game_doc(date, event_slug, sport, m, http=http)
            n_requests += 1
            sleep_fn(sleep_sec)
            if doc is not None:
                docs.append(doc)
                n_prices += doc["n_prices"]
        if docs:
            out_base.mkdir(parents=True, exist_ok=True)
            out_path = out_base / ("%s_%s.jsonl" % (date, event_slug))
            with out_path.open("w", encoding="utf-8") as fh:
                for d in docs:
                    fh.write(json.dumps(d) + "\n")
            n_game_days += 1
            n_games += len(docs)
            if earliest is None or date < earliest:
                earliest = date
            if latest is None or date > latest:
                latest = date
        progress = {
            "sport": sport, "last_date_done": date,
            "n_game_days": n_game_days, "n_games": n_games, "n_prices": n_prices,
            "n_off_days": n_off_days,
            "earliest_date_confirmed": earliest, "latest_date_confirmed": latest,
        }
        save_progress(prog_path, progress)
        if budget_hit:
            break
        cur += timedelta(days=1)

    return {
        "sport": sport, "start_date": start_date, "end_date": end_date,
        "n_requests_this_run": n_requests,
        "n_game_days": n_game_days, "n_games": n_games, "n_prices": n_prices,
        "n_off_days": n_off_days,
        "earliest_date_confirmed": earliest, "latest_date_confirmed": latest,
        "budget_hit": budget_hit, "reached_end_date": cur > end,
        "out_dir": str(out_base),
    }


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="polymarket_intragame")
    ap.add_argument("--sport", default="mlb")
    ap.add_argument("--start", default=DEFAULT_MLB_START)
    ap.add_argument("--end", default=DEFAULT_MLB_END)
    ap.add_argument("--max-requests", type=int, default=1500)
    ap.add_argument("--sleep-sec", type=float, default=1.0)
    a = ap.parse_args()
    result = run_backfill(a.sport, a.start, a.end, max_requests=a.max_requests, sleep_sec=a.sleep_sec)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()


__all__ = [
    "fetch_dailies_event", "fetch_price_history", "build_game_doc", "run_backfill",
    "GAMMA_BASE", "CLOB_BASE", "DEFAULT_MLB_START", "DEFAULT_MLB_END",
]
