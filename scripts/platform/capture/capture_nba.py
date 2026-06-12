"""capture_nba.py — NBA opener/close capture job (N-CLV-002).

Snapshots spread/total/ML + 7 prop markets; writes via N-CLV-001 ledger writer.
kind in {open, move, close}: first-seen=open, T-60=move, T-5=close.
Idempotent per (sport, event_id, market, book, side, kind) — reruns write 0 dupes.
Offline-safe: --dry-run uses a stub client; no ODDS_API_KEY required.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from ledger_schema import record_key, validate  # noqa: E402
from ledger_writer import append, read_all  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SPORT = "nba"
_SOURCE = "odds_api_live"
_ODDS_API_KEY_ENV = "ODDS_API_KEY"

_PROP_MARKETS: Tuple[str, ...] = (
    "player_points", "player_rebounds", "player_assists", "player_threes",
    "player_blocks", "player_steals", "player_turnovers",
)

_MAINLINE_MAP: Dict[str, str] = {"spreads": "spread", "totals": "total", "h2h": "moneyline"}

_CLOSE_MIN = 5   # minutes before tip → "close"
_MOVE_MIN  = 60  # minutes before tip → "move"


# ---------------------------------------------------------------------------
# Kind classification
# ---------------------------------------------------------------------------

def classify_kind(
    event_id: str,
    market: str,
    book: str,
    side: str,
    seen: Set[Tuple],
    commence_time: Optional[str],
    now_utc: Optional[datetime.datetime] = None,
) -> str:
    """Return ``open`` / ``move`` / ``close`` for a snapshot row.

    First-seen → ``open``.  Already open → time-window determines move/close.
    Falls back to ``open`` (dedup-caught) if outside all windows.
    """
    open_key = (_SPORT, event_id, market, book, side, "open")
    if open_key not in seen:
        return "open"
    if commence_time and commence_time.strip():
        now = now_utc or datetime.datetime.now(datetime.timezone.utc)
        try:
            tip_str = commence_time.rstrip("Z") + "+00:00" if commence_time.endswith("Z") else commence_time
            tip = datetime.datetime.fromisoformat(tip_str)
            mins = (tip - now).total_seconds() / 60.0
            if mins <= _CLOSE_MIN:
                return "close"
            if mins <= _MOVE_MIN:
                return "move"
        except (ValueError, OverflowError):
            pass
    return "open"


# ---------------------------------------------------------------------------
# Odds API client (injectable)
# ---------------------------------------------------------------------------

class OddsAPIClient:
    """Live Odds API client.  Replaced by stub in tests / dry-run."""

    def fetch_games(self) -> List[Dict[str, Any]]:
        """Fetch mainlines (spreads/totals/h2h) for all NBA games."""
        import requests  # deferred: keeps module importable offline
        r = requests.get(
            "https://api.the-odds-api.com/v4/sports/basketball_nba/odds/",
            params={"apiKey": os.environ.get(_ODDS_API_KEY_ENV, ""),
                    "regions": "us", "markets": "h2h,spreads,totals",
                    "oddsFormat": "american"},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    def fetch_props(self, event_id: str, market: str) -> List[Dict[str, Any]]:
        """Fetch bookmakers list for one prop market on one event."""
        import requests
        r = requests.get(
            f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{event_id}/odds",
            params={"apiKey": os.environ.get(_ODDS_API_KEY_ENV, ""),
                    "regions": "us", "markets": market, "oddsFormat": "american"},
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("bookmakers", [])


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------

def _now_ts() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_mainline_rows(
    game: Dict[str, Any], ts: str, seen: Set[Tuple],
    now_utc: Optional[datetime.datetime] = None,
) -> Iterator[dict]:
    """Yield validated ledger rows for spread/total/ML from one game dict."""
    eid = game.get("id", "")
    commence = game.get("commence_time", "")
    if not eid:
        return
    for bm in game.get("bookmakers", []):
        book = bm.get("key", "").strip()
        if not book:
            continue
        for mkt_obj in bm.get("markets", []):
            ledger_mkt = _MAINLINE_MAP.get(mkt_obj.get("key", ""))
            if not ledger_mkt:
                continue
            for out in mkt_obj.get("outcomes", []):
                name = out.get("name", "").strip().lower()
                price = out.get("price")
                point = out.get("point")
                if price is None:
                    continue
                side = f"{name}:{point}" if (ledger_mkt in ("spread", "total") and point is not None) else name
                kind = classify_kind(eid, ledger_mkt, book, side, seen, commence, now_utc)
                rec = dict(sport=_SPORT, event_id=eid, market=ledger_mkt, book=book,
                           price=float(price), side=side, kind=kind,
                           ts_utc_observed=ts, source=_SOURCE)
                try:
                    validate(rec)
                    yield rec
                except ValueError:
                    pass


def _build_prop_rows(
    eid: str, commence: str, market: str,
    bookmakers: List[Dict[str, Any]], ts: str, seen: Set[Tuple],
    now_utc: Optional[datetime.datetime] = None,
) -> Iterator[dict]:
    """Yield validated ledger rows for one prop market."""
    for bm in bookmakers:
        book = bm.get("key", "").strip()
        if not book:
            continue
        for mkt_obj in bm.get("markets", []):
            for out in mkt_obj.get("outcomes", []):
                direction = out.get("name", "").strip().lower()
                player = (out.get("description") or "").strip()
                price = out.get("price")
                point = out.get("point")
                if direction not in ("over", "under") or price is None or not player:
                    continue
                side = f"{direction}:{player}:{point}" if point is not None else f"{direction}:{player}"
                kind = classify_kind(eid, market, book, side, seen, commence, now_utc)
                rec = dict(sport=_SPORT, event_id=eid, market=market, book=book,
                           price=float(price), side=side, kind=kind,
                           ts_utc_observed=ts, source=_SOURCE)
                try:
                    validate(rec)
                    yield rec
                except ValueError:
                    pass


# ---------------------------------------------------------------------------
# Core capture
# ---------------------------------------------------------------------------

def _load_seen_keys(ledger_root: Optional[Path]) -> Set[Tuple]:
    """Load all (sport,event,market,book,side,kind) keys from the ledger."""
    from ledger_writer import _DEFAULT_ROOT as _dr  # noqa: PLC0415
    root = ledger_root if ledger_root is not None else _dr
    sport_dir = Path(root) / _SPORT
    seen: Set[Tuple] = set()
    if not sport_dir.exists():
        return seen
    for jf in sport_dir.glob("*.jsonl"):
        try:
            for row in read_all(_SPORT, jf.stem, root):
                seen.add(record_key(row))
        except Exception:
            pass
    return seen


def run_capture(
    dry_run: bool = False,
    ledger_root: Optional[Path] = None,
    client: Optional[Any] = None,
    now_utc: Optional[datetime.datetime] = None,
) -> dict:
    """Snapshot NBA lines and append to the ledger.  Pass ledger_root=tmp_path in tests.

    Args:
        dry_run: Count rows but do not write.
        ledger_root: Override ledger root (default = data/lines/forward).
        client: Injectable OddsAPIClient.  None → real client (requires API key).
        now_utc: Injected current time for deterministic kind classification.

    Returns:
        Stats dict: games_found, rows_written, rows_skipped_duplicate,
                    rows_failed_validation, prop_api_errors.
    """
    _client = client if client is not None else OddsAPIClient()

    # Key guard applies only to the real (non-injected) client.
    if client is None and not dry_run and not os.environ.get(_ODDS_API_KEY_ENV, ""):
        print(f"[capture_nba] {_ODDS_API_KEY_ENV} not set — use --dry-run for offline mode.")
        return dict(games_found=0, rows_written=0, rows_skipped_duplicate=0,
                    rows_failed_validation=0, prop_api_errors=0)

    ts = _now_ts()
    stats: Dict[str, int] = dict(games_found=0, rows_written=0, rows_skipped_duplicate=0,
                                  rows_failed_validation=0, prop_api_errors=0)
    seen = _load_seen_keys(ledger_root)

    try:
        games: List[Dict[str, Any]] = _client.fetch_games()
    except Exception as exc:
        print(f"[capture_nba] fetch_games() failed: {exc}")
        return stats

    stats["games_found"] = len(games)
    commence_map = {g.get("id", ""): g.get("commence_time", "") for g in games}

    def _emit(rec: dict) -> None:
        rk = record_key(rec)
        if rk in seen:
            stats["rows_skipped_duplicate"] += 1
            return
        seen.add(rk)
        stats["rows_written"] += 1
        if not dry_run:
            append(rec, root=ledger_root)

    for game in games:
        for rec in _build_mainline_rows(game, ts, seen, now_utc):
            _emit(rec)

    for game in games:
        eid = game.get("id", "")
        if not eid:
            continue
        for prop_mkt in _PROP_MARKETS:
            try:
                bms = _client.fetch_props(eid, prop_mkt)
            except Exception as exc:
                print(f"[capture_nba] fetch_props({eid}, {prop_mkt}) failed: {exc}")
                stats["prop_api_errors"] += 1
                continue
            for rec in _build_prop_rows(eid, commence_map.get(eid, ""), prop_mkt, bms, ts, seen, now_utc):
                _emit(rec)

    return stats


# ---------------------------------------------------------------------------
# Dry-run stub client
# ---------------------------------------------------------------------------

class _DryRunStubClient:
    """Offline stub — returns synthetic data, zero network calls."""

    def fetch_games(self) -> List[Dict[str, Any]]:
        return [{"id": "dry_nba_001", "home_team": "New York Knicks",
                 "away_team": "San Antonio Spurs", "commence_time": "2030-01-15T02:00:00Z",
                 "bookmakers": [{"key": "draftkings", "markets": [
                     {"key": "spreads", "outcomes": [
                         {"name": "New York Knicks", "price": -110, "point": -2.5},
                         {"name": "San Antonio Spurs", "price": -110, "point": 2.5}]},
                     {"key": "totals", "outcomes": [
                         {"name": "Over", "price": -110, "point": 215.5},
                         {"name": "Under", "price": -110, "point": 215.5}]},
                     {"key": "h2h", "outcomes": [
                         {"name": "New York Knicks", "price": -130},
                         {"name": "San Antonio Spurs", "price": 110}]}]}]}]

    def fetch_props(self, event_id: str, market: str) -> List[Dict[str, Any]]:
        return [{"key": "draftkings", "markets": [{"key": market, "outcomes": [
            {"name": "Over", "description": "Jalen Brunson", "price": -115, "point": 27.5},
            {"name": "Under", "description": "Jalen Brunson", "price": -105, "point": 27.5}]}]}]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for the capture job."""
    parser = argparse.ArgumentParser(description="N-CLV-002 — NBA opener/close capture job.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate offline using stub client; does not write or require a key.")
    args = parser.parse_args()

    if not args.dry_run and not os.environ.get(_ODDS_API_KEY_ENV, ""):
        print(f"[capture_nba] {_ODDS_API_KEY_ENV} not set. "
              "Set the env var for live capture or use --dry-run.")
        sys.exit(0)

    client_arg = _DryRunStubClient() if args.dry_run else None
    mode = "DRY-RUN (stub)" if args.dry_run else "LIVE"
    print(f"\n=== capture_nba [{mode}] ===")
    s = run_capture(dry_run=args.dry_run, client=client_arg)
    label = "(would write)" if args.dry_run else "written"
    print(f"  Games found           : {s['games_found']}")
    print(f"  Rows {label:<23}: {s['rows_written']}")
    print(f"  Rows skipped (dupes)  : {s['rows_skipped_duplicate']}")
    print(f"  Rows failed validation: {s['rows_failed_validation']}")
    print(f"  Prop API errors       : {s['prop_api_errors']}")
    print()


if __name__ == "__main__":
    main()
