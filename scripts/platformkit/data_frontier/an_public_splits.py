"""scripts.platformkit.data_frontier.an_public_splits -- Action Network public
betting splits (frontier acquisition-queue rank 3; census row rank 8,
data/frontend/ops/data_frontier_census.json).

The 2026-07-09 offseason probe found the v1 scoreboard schema
(ml_home_public/ml_away_public/*_money) with ALL values null on the free tier.
In-season reprobe (this lane, 2026-07-09, MLB live slate):

  * /web/v1/scoreboard/mlb?date=20260709 -> 200, 13 games, but STILL
    0/3516 public/money fields non-null (v1 stays a dead shape in-season).
  * /web/v2/scoreboard/mlb?date=20260709 -> 200, 13 games, and
    bet_info.tickets.percent + bet_info.money.percent are POPULATED:
    1436/1696 non-null across 5 books (15/30/68/69/71), e.g. game 291677
    book 15 moneyline away = 72% tickets / 66% money. Populated even where
    is_free=false, so the game-level split is NOT pay-gated.

So the capture source is the v2 scoreboard (same endpoint family
src/data/action_network.py verified 2026-05-24 for NBA). One row per
(game, book, market-type, side) snapshot, appended to a date-keyed JSONL
store mirroring the line_history convention:

    data/cache/public_splits/<league>/<YYYY-MM-DD>.jsonl

Sentiment-vs-price is the axis nothing on disk has: the market corpus is
devigged consensus PRICE only; this store adds which side the public's
tickets and money are on. Calibration/feature input only -- no edge claim.

Politeness: 1 req/s, 35s timeout, no evasion; a non-200 is recorded honestly
in status.json (never worked around).

CLI: python -m scripts.platformkit.data_frontier.an_public_splits
     [--leagues mlb wnba] [--interval 86400]
"""
from __future__ import annotations

import argparse
import json
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests

from scripts.platformkit.data_frontier._politeness import (
    atomic_write_text,
    log_line,
    polite_sleep,
)

_REPO = Path(__file__).resolve().parents[3]
OUT_DIR = _REPO / "data" / "cache" / "public_splits"
STATUS_FP = OUT_DIR / "status.json"
_LOG_FP = _REPO / "data" / "cache" / "logs" / "an_public_splits.log"
HEARTBEAT_PATH = _REPO / "data" / "cache" / "daemon_heartbeats" / "m41_public_splits.txt"
STOP_FLAG_PATH = _REPO / ".bot_state" / "live_status.json"

_BASE = "https://api.actionnetwork.com/web/v2/scoreboard/{league}"
_HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.actionnetwork.com/",
}
DEFAULT_LEAGUES = ["mlb"]  # in-season now; extend via --leagues when others tip off
_MARKETS = ("moneyline", "spread", "total")
_MIN_INTERVAL_SEC = 1.0   # politeness rail: 1 req/s per host, absolute
_TIMEOUT_SEC = 35.0
DEFAULT_INTERVAL_SEC = 86400.0  # daily capture cadence (m41 spec)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def candidate_dates(now: Optional[datetime] = None) -> List[str]:
    """UTC and ET calendar dates as YYYYMMDD (deduped, sorted) -- date-keyed
    fetches must try BOTH candidate dates (repo rail: slates key on ET, the
    box clock on UTC; near midnight they differ)."""
    now = now or datetime.now(timezone.utc)
    utc_d = now.strftime("%Y%m%d")
    et_d = now.astimezone(ZoneInfo("America/New_York")).strftime("%Y%m%d")
    return sorted({utc_d, et_d})


def flatten(payload: Dict[str, Any], league: str, fetched_at: str) -> List[Dict[str, Any]]:
    """One row per (game, book, market-type, side) from a v2 scoreboard payload.
    Pure function, no network (unit-tested against a synthetic payload)."""
    rows: List[Dict[str, Any]] = []
    for game in payload.get("games") or []:
        abbr = {t.get("id"): t.get("abbr") for t in (game.get("teams") or [])}
        base = {
            "league": league,
            "game_id": game.get("id"),
            "start_time": game.get("start_time"),
            "game_status": game.get("status"),
            "home_team_id": game.get("home_team_id"),
            "away_team_id": game.get("away_team_id"),
            "home_abbr": abbr.get(game.get("home_team_id")),
            "away_abbr": abbr.get(game.get("away_team_id")),
            "num_bets_game": game.get("num_bets"),
            "is_free": game.get("is_free"),
            "fetched_at": fetched_at,
        }
        for book_id, book in (game.get("markets") or {}).items():
            for mtype, outcomes in (book.get("event") or {}).items():
                if mtype not in _MARKETS:
                    continue
                for o in outcomes or []:
                    bi = o.get("bet_info") or {}
                    rows.append({
                        **base,
                        "book_id": str(book_id),
                        "market": mtype,
                        "side": o.get("side"),
                        "odds": o.get("odds"),
                        "value": o.get("value"),
                        "tickets_pct": (bi.get("tickets") or {}).get("percent"),
                        "money_pct": (bi.get("money") or {}).get("percent"),
                    })
    return rows


def _append_rows(fp: Path, rows: List[Dict[str, Any]]) -> None:
    """Batch-append rows as JSONL via one read + one atomic replace (the
    per-row io_atomic helper re-reads the file per row -- O(n^2) for a slate)."""
    existing = ""
    if fp.is_file():
        existing = fp.read_text(encoding="ascii", errors="replace")
        if existing and not existing.endswith("\n"):
            existing += "\n"
    body = existing + "".join(
        json.dumps(r, ensure_ascii=True, sort_keys=True) + "\n" for r in rows)
    atomic_write_text(fp, body, encoding="ascii")


def pull(leagues: Optional[List[str]] = None, fetcher=None,
         out_dir: Optional[Path] = None,
         now: Optional[datetime] = None) -> Dict[str, Any]:
    """Fetch each league's scoreboard for BOTH candidate dates (1 req/s),
    dedupe games by id, flatten, append to the date-keyed store. Returns and
    writes an honest status dict (row counts / non-200 evidence)."""
    get = fetcher or requests.get
    out_dir = out_dir or OUT_DIR
    now = now or datetime.now(timezone.utc)
    fetched_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    et_day = now.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    last_call: Optional[float] = None
    per_league: Dict[str, Any] = {}

    for league in (leagues or DEFAULT_LEAGUES):
        games: Dict[Any, Dict[str, Any]] = {}
        errors: List[str] = []
        for d in candidate_dates(now):
            last_call = polite_sleep(_MIN_INTERVAL_SEC, last_call)
            try:
                r = get(_BASE.format(league=league), params={"date": d},
                        headers=_HDR, timeout=_TIMEOUT_SEC)
            except requests.RequestException as exc:
                errors.append(f"{d}: fetch failed: {exc}")
                continue
            if r.status_code != 200:
                errors.append(f"{d}: HTTP {r.status_code} body[:200]={r.text[:200]!r}")
                continue
            for g in (r.json().get("games") or []):
                if g.get("id") is not None:
                    games.setdefault(g["id"], g)

        rows = flatten({"games": list(games.values())}, league, fetched_at)
        filled = sum(1 for r in rows if r["tickets_pct"] is not None)
        fp = out_dir / league / f"{et_day}.jsonl"
        if rows:
            _append_rows(fp, rows)
        per_league[league] = {
            "games": len(games), "rows_appended": len(rows),
            "rows_with_tickets_pct": filled, "path": str(fp), "errors": errors,
        }
        log_line(_LOG_FP, f"{league} games={len(games)} rows={len(rows)} "
                          f"filled={filled} errors={len(errors)}")

    any_filled = any(v["rows_with_tickets_pct"] > 0 for v in per_league.values())
    status = {
        "verdict": "POPULATED" if any_filled else "EMPTY_OR_BLOCKED",
        "checked_at": fetched_at,
        "endpoint": _BASE,
        "per_league": per_league,
        "note": "v2 scoreboard bet_info tickets/money percents; v1 *_public "
                "fields remain null in-season (see module docstring evidence).",
    }
    atomic_write_text(STATUS_FP, json.dumps(status, indent=2))
    return status


def _should_stop() -> bool:
    """READ .bot_state/live_status.json stop_requested. Fail-safe: an
    unreadable flag halts. Never RUNS stop_bot.py."""
    try:
        if not STOP_FLAG_PATH.exists():
            return False
        doc = json.loads(STOP_FLAG_PATH.read_text(encoding="utf-8"))
        return bool(doc.get("stop_requested", False))
    except Exception:  # noqa: BLE001 -- unreadable stop flag -> halt
        return True


def serve_forever(interval_sec: float = DEFAULT_INTERVAL_SEC,
                  max_ticks: Optional[int] = None) -> int:
    """Daily capture loop for the m41 supervisor spec: stop-flag check before
    each tick, pull, heartbeat, sleep. Returns ticks run."""
    ticks = 0
    while not _should_stop():
        try:
            pull()
        except Exception as exc:  # noqa: BLE001 -- a bad tick never kills the daemon
            log_line(_LOG_FP, f"tick error: {exc}")
        try:
            HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
            HEARTBEAT_PATH.write_text(_now_iso(), encoding="ascii")
        except Exception:  # noqa: BLE001 -- heartbeat write is best-effort
            pass
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        _time.sleep(interval_sec)
    return ticks


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Action Network public-splits capture.")
    ap.add_argument("--leagues", nargs="+", default=DEFAULT_LEAGUES)
    ap.add_argument("--interval", type=float, default=None,
                    help="run as a daemon with this many seconds between ticks")
    args = ap.parse_args(argv)
    if args.interval is not None:
        return 0 if serve_forever(interval_sec=args.interval) >= 0 else 1
    print(json.dumps(pull(leagues=args.leagues), indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["candidate_dates", "flatten", "pull", "serve_forever", "main",
           "DEFAULT_LEAGUES", "OUT_DIR", "HEARTBEAT_PATH"]
