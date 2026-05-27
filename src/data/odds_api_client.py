"""odds_api_client.py — budget-gated client for the-odds-api.com.

ALL callers of the-odds-api must go through this client. Raw HTTP from
elsewhere defeats the budget gate.

Contracts:
  * Per-request disk cache at
      data/cache/odds_api/{endpoint}/{date}_{market}_{region}.json
    Cache hit (file exists AND age <30 days) returns the cached body
    without hitting the network.
  * Budget counter at data/cache/odds_api/_budget.json. When
    `used_units >= MAX_UNITS` (20000), all live fetches are blocked and
    callers must fall back to data/external/historical_lines/*.
  * Every live request is appended to data/cache/odds_api/_request_log.jsonl
    with (timestamp, endpoint, params, cost_units, remaining_from_header).
  * Endpoint enumeration of /sports is disallowed — sport key is fixed to
    `basketball_nba`. Use one region + one market per call.

Public surface:
  * fetch_historical_odds(date, market, region="us") — primary backtest source
  * fetch_event_odds(event_id, market, region="us") — live single-event quotes
  * list_events(date=None) — event index (uses /events; date narrows window)
  * BudgetExceeded — raised when budget gate trips
  * get_budget() / reset_budget() — introspection + manual reset
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "cache" / "odds_api"
BUDGET_PATH = CACHE_DIR / "_budget.json"
LOG_PATH = CACHE_DIR / "_request_log.jsonl"

API_BASE = "https://api.the-odds-api.com/v4"
SPORT_KEY = "basketball_nba"
MAX_UNITS = 20000  # actual paid-tier capacity (3687 used + 16313 remaining as of 2026-05-27)
CACHE_TTL_DAYS = 30
DEFAULT_REGION = "us"
ALLOWED_MARKETS = {
    "player_points", "player_rebounds", "player_assists",
    "player_threes", "player_steals", "player_blocks", "player_turnovers",
    "h2h", "spreads", "totals",
}


class BudgetExceeded(RuntimeError):
    """Raised when used_units >= MAX_UNITS — callers must fall back."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for sub in ("historical_odds", "events", "event_odds"):
        (CACHE_DIR / sub).mkdir(exist_ok=True)


def _api_key() -> str:
    # Accept either env var name — repo historically used THE_ODDS_API_KEY,
    # the loop spec uses ODDS_API_KEY.
    key = os.environ.get("ODDS_API_KEY") or os.environ.get("THE_ODDS_API_KEY")
    if not key:
        # Try .env at repo root.
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("ODDS_API_KEY=") or line.startswith("THE_ODDS_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        raise RuntimeError("ODDS_API_KEY (or THE_ODDS_API_KEY) not set")
    return key


def get_budget() -> dict[str, Any]:
    """Return {used_units, max_units, remaining_from_header, updated_at}."""
    _ensure_dirs()
    if BUDGET_PATH.exists():
        try:
            return json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("budget file corrupt — resetting")
    return {
        "used_units": 0,
        "max_units": MAX_UNITS,
        "remaining_from_header": None,
        "updated_at": _now_iso(),
    }


def _write_budget(state: dict[str, Any]) -> None:
    BUDGET_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def reset_budget() -> None:
    _ensure_dirs()
    _write_budget({
        "used_units": 0,
        "max_units": MAX_UNITS,
        "remaining_from_header": None,
        "updated_at": _now_iso(),
    })


def _log_request(entry: dict[str, Any]) -> None:
    _ensure_dirs()
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _cache_path(endpoint: str, key: str) -> Path:
    _ensure_dirs()
    safe = key.replace("/", "_").replace(":", "-")
    return CACHE_DIR / endpoint / f"{safe}.json"


def _cache_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(timezone.utc) - mtime) < timedelta(days=CACHE_TTL_DAYS)


def _read_cache(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_cache(path: Path, body: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")


def _http_get(url: str, timeout: float = 20.0) -> tuple[Any, dict[str, str]]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", errors="replace")
        headers = {k.lower(): v for k, v in r.headers.items()}
        return json.loads(body), headers


def _gate_or_fetch(
    endpoint: str,
    cache_key: str,
    url: str,
    params: dict[str, Any],
    cost_units: int = 1,
) -> Any:
    """Cache-first, budget-gated fetch. Returns parsed JSON body."""
    cache_path = _cache_path(endpoint, cache_key)
    if _cache_fresh(cache_path):
        log.debug("cache hit %s", cache_path.name)
        return _read_cache(cache_path)

    state = get_budget()
    if state["used_units"] >= MAX_UNITS:
        raise BudgetExceeded(
            f"used_units={state['used_units']} >= MAX_UNITS={MAX_UNITS}; "
            "fall back to data/external/historical_lines/*"
        )

    log.info("FETCH %s %s", endpoint, cache_key)
    body, headers = _http_get(url)
    remaining_header = headers.get("x-requests-remaining")
    used_header = headers.get("x-requests-used")

    state["used_units"] = int(state.get("used_units", 0)) + cost_units
    state["remaining_from_header"] = (
        int(remaining_header) if remaining_header and remaining_header.isdigit() else None
    )
    state["used_from_header"] = (
        int(used_header) if used_header and used_header.isdigit() else None
    )
    state["updated_at"] = _now_iso()
    _write_budget(state)

    _log_request({
        "timestamp": _now_iso(),
        "endpoint": endpoint,
        "params": {k: v for k, v in params.items() if k != "apiKey"},
        "cost_units": cost_units,
        "remaining_from_header": state["remaining_from_header"],
        "used_from_header": state.get("used_from_header"),
        "local_used_units": state["used_units"],
    })

    _write_cache(cache_path, body)
    return body


def _validate_market(market: str) -> None:
    if market not in ALLOWED_MARKETS:
        raise ValueError(
            f"market={market!r} not allowed. Use one of {sorted(ALLOWED_MARKETS)}"
        )


def fetch_historical_odds(
    date: str,
    market: str,
    region: str = DEFAULT_REGION,
) -> Any:
    """Pull /historical/sports/basketball_nba/odds for one (date, market, region).

    `date` accepts YYYY-MM-DD or full ISO8601. Cost = 10 units per the-odds-api
    historical pricing. One region + one market per call.
    """
    _validate_market(market)
    if "T" not in date:
        date_iso = f"{date}T12:00:00Z"
    else:
        date_iso = date
    params = {
        "apiKey": _api_key(),
        "regions": region,
        "markets": market,
        "oddsFormat": "american",
        "date": date_iso,
    }
    url = (
        f"{API_BASE}/historical/sports/{SPORT_KEY}/odds?"
        + urllib.parse.urlencode(params)
    )
    cache_key = f"{date[:10]}_{market}_{region}"
    return _gate_or_fetch("historical_odds", cache_key, url, params, cost_units=10)


def list_events(date: str | None = None) -> Any:
    """List events. `date` (YYYY-MM-DD) narrows to that game day if given.

    Cost = 1 unit. Never use /sports for enumeration — sport key is fixed.
    """
    params: dict[str, Any] = {"apiKey": _api_key()}
    if date:
        params["dateFormat"] = "iso"
        params["commenceTimeFrom"] = f"{date}T00:00:00Z"
        params["commenceTimeTo"] = f"{date}T23:59:59Z"
    url = f"{API_BASE}/sports/{SPORT_KEY}/events?" + urllib.parse.urlencode(params)
    cache_key = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _gate_or_fetch("events", f"{cache_key}_events", url, params, cost_units=1)


def fetch_event_odds(
    event_id: str,
    market: str,
    region: str = DEFAULT_REGION,
) -> Any:
    """Pull odds for a single event/market. Cost = 1 unit."""
    _validate_market(market)
    params = {
        "apiKey": _api_key(),
        "regions": region,
        "markets": market,
        "oddsFormat": "american",
    }
    url = (
        f"{API_BASE}/sports/{SPORT_KEY}/events/{event_id}/odds?"
        + urllib.parse.urlencode(params)
    )
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache_key = f"{today}_{event_id}_{market}_{region}"
    return _gate_or_fetch("event_odds", cache_key, url, params, cost_units=1)


def list_historical_events(date: str) -> Any:
    """Pull /historical/sports/basketball_nba/events at the given snapshot.

    `date` accepts YYYY-MM-DD (12:00 UTC default) or full ISO8601. Cost = 1 unit.
    Returns the events active near `date` (within the API's time window).
    Required before player-props historical fetches — those use event_id.
    """
    if "T" not in date:
        date_iso = f"{date}T12:00:00Z"
    else:
        date_iso = date
    params = {"apiKey": _api_key(), "date": date_iso}
    url = (
        f"{API_BASE}/historical/sports/{SPORT_KEY}/events?"
        + urllib.parse.urlencode(params)
    )
    cache_key = f"{date[:10]}_events"
    return _gate_or_fetch("historical_events", cache_key, url, params, cost_units=1)


def fetch_historical_event_odds(
    event_id: str,
    date: str,
    market: str,
    region: str = DEFAULT_REGION,
) -> Any:
    """Pull /historical/sports/basketball_nba/events/{id}/odds for a player-prop market.

    Player-level markets (player_points, player_rebounds, etc.) are NOT served by
    the bulk /historical/sports/.../odds endpoint — they require the per-event
    historical variant. Cost = 10 units per call. One region + one market.
    """
    _validate_market(market)
    if "T" not in date:
        date_iso = f"{date}T12:00:00Z"
    else:
        date_iso = date
    params = {
        "apiKey": _api_key(),
        "regions": region,
        "markets": market,
        "oddsFormat": "american",
        "date": date_iso,
    }
    url = (
        f"{API_BASE}/historical/sports/{SPORT_KEY}/events/{event_id}/odds?"
        + urllib.parse.urlencode(params)
    )
    cache_key = f"{date[:10]}_{event_id}_{market}_{region}"
    return _gate_or_fetch(
        "historical_event_odds", cache_key, url, params, cost_units=10
    )


__all__ = [
    "BudgetExceeded",
    "MAX_UNITS",
    "fetch_historical_odds",
    "fetch_historical_event_odds",
    "fetch_event_odds",
    "list_events",
    "list_historical_events",
    "get_budget",
    "reset_budget",
]
