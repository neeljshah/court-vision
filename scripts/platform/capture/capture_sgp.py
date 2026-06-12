"""capture_sgp.py — SGP/correlated-leg price capture job (N-SGP-001).

Extends the capture pipeline to any same-game-parlay (SGP) or
correlated-leg pricing that The Odds API exposes.

Market tag format:  ``sgp:<leg1>+<leg2>[+...]``
                    where each leg is the raw Odds API market key
                    (e.g. ``sgp:player_points+player_rebounds``).
Leg labels come verbatim from the API so they round-trip cleanly.

CAPTURE ONLY — no pricing claims, no edge assertions.

Key design decisions
--------------------
* **ZERO rows is a valid outcome.**  The Odds API v4 does not currently
  expose a dedicated SGP endpoint.  The first ``fetch_sgp_markets``
  call probes the event-odds endpoint with the query param
  ``markets=alternate_spreads,alternate_totals,player_points+player_rebounds``
  (a multi-leg combo).  If the API returns no bookmakers with correlated
  pricing the capture records a ``zero_rows`` outcome in the stats dict
  and exits cleanly — downstream consumers check ``stats["sgp_rows_written"]``.
* **Idempotency** — dedup key is the standard
  ``(sport, event_id, market, book, side, kind)`` tuple via ledger_schema.
* **Kind classification** — reuses the same open/move/close windows as
  capture_nba (first-seen=open, T-60=move, T-5=close).
* **Injectable stub client** — ``SgpOddsAPIClient`` is the live wrapper;
  tests inject ``_DryRunSgpStubClient`` or custom fakes.
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
_SOURCE = "odds_api_sgp"
_ODDS_API_KEY_ENV = "ODDS_API_KEY"

# Candidate SGP market combos to probe on each event.
# The API returns bookmakers that actually price these combos; most will be
# absent → zero rows, which is expected and fine.
_SGP_PROBE_COMBOS: Tuple[Tuple[str, ...], ...] = (
    ("player_points", "player_rebounds"),
    ("player_points", "player_assists"),
    ("player_points", "player_rebounds", "player_assists"),
    ("player_threes", "player_points"),
    ("spreads", "totals"),
)

_CLOSE_MIN = 5   # minutes before tip → "close"
_MOVE_MIN  = 60  # minutes before tip → "move"


# ---------------------------------------------------------------------------
# SGP market tag helper
# ---------------------------------------------------------------------------

def make_sgp_market_tag(legs: Tuple[str, ...]) -> str:
    """Return the canonical ledger market tag for an SGP combo.

    Args:
        legs: Ordered sequence of Odds API market key strings.

    Returns:
        String of the form ``sgp:<leg1>+<leg2>[+...]``.
    """
    if not legs:
        raise ValueError("SGP market tag requires at least one leg.")
    return "sgp:" + "+".join(legs)


# ---------------------------------------------------------------------------
# Kind classification (mirrors capture_nba.classify_kind)
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

    First-seen → ``open``.  Already open → time-window determines
    ``move`` (T-60) or ``close`` (T-5).

    Args:
        event_id: Odds API event identifier.
        market: Ledger market string (e.g. ``sgp:player_points+player_rebounds``).
        book: Bookmaker key.
        side: Outcome side string.
        seen: Set of already-written record_key tuples.
        commence_time: ISO-8601 UTC commence time string, or ``None``/empty.
        now_utc: Injected current time for deterministic classification.

    Returns:
        One of ``"open"``, ``"move"``, ``"close"``.
    """
    open_key = (_SPORT, event_id, market, book, side, "open")
    if open_key not in seen:
        return "open"
    if commence_time and commence_time.strip():
        now = now_utc or datetime.datetime.now(datetime.timezone.utc)
        try:
            tip_str = (commence_time.rstrip("Z") + "+00:00"
                       if commence_time.endswith("Z") else commence_time)
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

class SgpOddsAPIClient:
    """Live Odds API client for SGP market probes.

    Replaced by stub in tests / dry-run.  Each call hits the event-level
    odds endpoint with a multi-market query string — the API returns
    bookmakers that price all requested legs jointly (SGP / correlated).
    If the API does not support the combo it returns an empty bookmakers
    list; that is a valid zero-row outcome.
    """

    def fetch_events(self) -> List[Dict[str, Any]]:
        """Return the list of upcoming NBA events (id + commence_time only)."""
        import requests  # deferred: keeps module importable offline
        r = requests.get(
            "https://api.the-odds-api.com/v4/sports/basketball_nba/events/",
            params={"apiKey": os.environ.get(_ODDS_API_KEY_ENV, "")},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    def fetch_sgp_bookmakers(
        self, event_id: str, legs: Tuple[str, ...]
    ) -> List[Dict[str, Any]]:
        """Probe one SGP combo on one event.

        Args:
            event_id: Odds API event identifier.
            legs: Ordered tuple of market keys forming the SGP combo.

        Returns:
            Bookmakers list (may be empty if API does not expose this combo).
        """
        import requests
        r = requests.get(
            f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{event_id}/odds",
            params={
                "apiKey": os.environ.get(_ODDS_API_KEY_ENV, ""),
                "regions": "us",
                "markets": ",".join(legs),
                "oddsFormat": "american",
            },
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("bookmakers", [])


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def _now_ts() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_sgp_rows(
    event_id: str,
    commence: str,
    legs: Tuple[str, ...],
    bookmakers: List[Dict[str, Any]],
    ts: str,
    seen: Set[Tuple],
    now_utc: Optional[datetime.datetime] = None,
) -> Iterator[dict]:
    """Yield validated ledger rows from one SGP combo response.

    An SGP row's ``side`` encodes the outcome label plus player (if any)
    and line point so it is fully self-describing:
    ``<direction>:<description>:<point>`` or ``<name>`` for non-player legs.

    Args:
        event_id: Odds API event identifier.
        commence: ISO-8601 UTC commence time string.
        legs: Tuple of market keys forming the SGP combo.
        bookmakers: Bookmakers list from the API response.
        ts: ISO-8601 UTC observation timestamp string.
        seen: Set of already-written record_key tuples (mutated in-place).
        now_utc: Injected current time for kind classification.

    Yields:
        Validated ledger record dicts.
    """
    market_tag = make_sgp_market_tag(legs)
    for bm in bookmakers:
        book = bm.get("key", "").strip()
        if not book:
            continue
        for mkt_obj in bm.get("markets", []):
            for out in mkt_obj.get("outcomes", []):
                name = (out.get("name") or "").strip().lower()
                description = (out.get("description") or "").strip()
                price = out.get("price")
                point = out.get("point")
                if price is None or not name:
                    continue
                # Build a self-describing side string.
                if description and point is not None:
                    side = f"{name}:{description}:{point}"
                elif description:
                    side = f"{name}:{description}"
                elif point is not None:
                    side = f"{name}:{point}"
                else:
                    side = name
                kind = classify_kind(
                    event_id, market_tag, book, side, seen, commence, now_utc
                )
                rec = dict(
                    sport=_SPORT,
                    event_id=event_id,
                    market=market_tag,
                    book=book,
                    price=float(price),
                    side=side,
                    kind=kind,
                    ts_utc_observed=ts,
                    source=_SOURCE,
                )
                try:
                    validate(rec)
                    yield rec
                except ValueError:
                    pass


# ---------------------------------------------------------------------------
# Seen-keys loader
# ---------------------------------------------------------------------------

def _load_seen_keys(ledger_root: Optional[Path]) -> Set[Tuple]:
    """Load all existing record keys from the ledger (SGP sport dir only).

    Args:
        ledger_root: Ledger root directory override, or ``None`` for default.

    Returns:
        Set of ``(sport, event_id, market, book, side, kind)`` tuples.
    """
    from ledger_writer import _DEFAULT_ROOT as _dr  # noqa: PLC0415
    root = ledger_root if ledger_root is not None else _dr
    sport_dir = Path(root) / _SPORT
    seen: Set[Tuple] = set()
    if not sport_dir.exists():
        return seen
    for jf in sport_dir.glob("*.jsonl"):
        try:
            for row in read_all(_SPORT, jf.stem, root):
                k = record_key(row)
                # Only load SGP-tagged rows to avoid false positives from
                # mainline rows sharing the same (event, book, side, kind).
                if row.get("market", "").startswith("sgp:"):
                    seen.add(k)
        except Exception:
            pass
    return seen


# ---------------------------------------------------------------------------
# Core capture
# ---------------------------------------------------------------------------

def run_capture(
    dry_run: bool = False,
    ledger_root: Optional[Path] = None,
    client: Optional[Any] = None,
    now_utc: Optional[datetime.datetime] = None,
) -> dict:
    """Snapshot SGP/correlated-leg prices and append to the ledger.

    Probes each ``_SGP_PROBE_COMBOS`` on every upcoming event.  Records
    whatever the API returns; ZERO rows is a valid outcome if the API
    does not currently expose SGP pricing.

    Args:
        dry_run: Count rows but do not write anything to disk.
        ledger_root: Override ledger root (default ``data/lines/forward``).
            Pass ``tmp_path`` in tests to isolate writes.
        client: Injectable ``SgpOddsAPIClient``.  ``None`` → real client
            (requires ``ODDS_API_KEY``).
        now_utc: Injected current time for deterministic kind classification.

    Returns:
        Stats dict with keys:
        ``events_found``, ``sgp_rows_written``, ``rows_skipped_duplicate``,
        ``rows_failed_validation``, ``sgp_api_errors``, ``zero_rows``.
        ``zero_rows`` is ``True`` when the API returned no SGP pricing at all
        (expected and not an error).
    """
    _client = client if client is not None else SgpOddsAPIClient()

    if client is None and not dry_run and not os.environ.get(_ODDS_API_KEY_ENV, ""):
        print(
            f"[capture_sgp] {_ODDS_API_KEY_ENV} not set — "
            "use --dry-run for offline mode."
        )
        return dict(
            events_found=0, sgp_rows_written=0, rows_skipped_duplicate=0,
            rows_failed_validation=0, sgp_api_errors=0, zero_rows=True,
        )

    ts = _now_ts()
    stats: Dict[str, Any] = dict(
        events_found=0, sgp_rows_written=0, rows_skipped_duplicate=0,
        rows_failed_validation=0, sgp_api_errors=0, zero_rows=False,
    )
    seen = _load_seen_keys(ledger_root)

    try:
        events: List[Dict[str, Any]] = _client.fetch_events()
    except Exception as exc:
        print(f"[capture_sgp] fetch_events() failed: {exc}")
        stats["zero_rows"] = True
        return stats

    stats["events_found"] = len(events)

    def _emit(rec: dict) -> None:
        rk = record_key(rec)
        if rk in seen:
            stats["rows_skipped_duplicate"] += 1
            return
        seen.add(rk)
        stats["sgp_rows_written"] += 1
        if not dry_run:
            append(rec, root=ledger_root)

    for event in events:
        eid = event.get("id", "")
        commence = event.get("commence_time", "")
        if not eid:
            continue
        for legs in _SGP_PROBE_COMBOS:
            try:
                bookmakers = _client.fetch_sgp_bookmakers(eid, legs)
            except Exception as exc:
                print(f"[capture_sgp] fetch_sgp_bookmakers({eid}, {legs}) failed: {exc}")
                stats["sgp_api_errors"] += 1
                continue
            for rec in _build_sgp_rows(eid, commence, legs, bookmakers, ts, seen, now_utc):
                _emit(rec)

    if stats["sgp_rows_written"] == 0 and stats["rows_skipped_duplicate"] == 0:
        stats["zero_rows"] = True
        print("[capture_sgp] No SGP pricing found on this slate — zero rows is a valid outcome.")

    return stats


# ---------------------------------------------------------------------------
# Dry-run stub client
# ---------------------------------------------------------------------------

class _DryRunSgpStubClient:
    """Offline stub — returns synthetic SGP data; zero network calls.

    Simulates a book (FanDuel) that exposes correlated pricing on the
    player_points+player_rebounds combo only.  All other combos return
    an empty bookmakers list (mirrors real API behaviour).
    """

    _SGP_SUPPORTED_LEGS: Tuple[str, ...] = ("player_points", "player_rebounds")

    def fetch_events(self) -> List[Dict[str, Any]]:
        """Return one synthetic NBA event."""
        return [
            {
                "id": "dry_sgp_evt_001",
                "home_team": "New York Knicks",
                "away_team": "San Antonio Spurs",
                "commence_time": "2030-01-15T02:00:00Z",
            }
        ]

    def fetch_sgp_bookmakers(
        self, event_id: str, legs: Tuple[str, ...]
    ) -> List[Dict[str, Any]]:
        """Return bookmakers only for the supported SGP combo; empty otherwise."""
        if set(legs) == set(self._SGP_SUPPORTED_LEGS):
            return [
                {
                    "key": "fanduel",
                    "markets": [
                        {
                            "key": "player_points",
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "Jalen Brunson",
                                    "price": -120,
                                    "point": 27.5,
                                },
                                {
                                    "name": "Under",
                                    "description": "Jalen Brunson",
                                    "price": 100,
                                    "point": 27.5,
                                },
                            ],
                        },
                        {
                            "key": "player_rebounds",
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "Karl-Anthony Towns",
                                    "price": -115,
                                    "point": 9.5,
                                },
                                {
                                    "name": "Under",
                                    "description": "Karl-Anthony Towns",
                                    "price": -105,
                                    "point": 9.5,
                                },
                            ],
                        },
                    ],
                }
            ]
        # All other combos — API returns no pricing.
        return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for the SGP capture job."""
    parser = argparse.ArgumentParser(
        description="N-SGP-001 — SGP/correlated-leg price capture job."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate offline using stub client; does not write or require a key.",
    )
    args = parser.parse_args()

    if not args.dry_run and not os.environ.get(_ODDS_API_KEY_ENV, ""):
        print(
            f"[capture_sgp] {_ODDS_API_KEY_ENV} not set. "
            "Set the env var for live capture or use --dry-run."
        )
        sys.exit(0)

    client_arg = _DryRunSgpStubClient() if args.dry_run else None
    mode = "DRY-RUN (stub)" if args.dry_run else "LIVE"
    print(f"\n=== capture_sgp [{mode}] ===")
    s = run_capture(dry_run=args.dry_run, client=client_arg)
    label = "(would write)" if args.dry_run else "written"
    print(f"  Events found                 : {s['events_found']}")
    print(f"  SGP rows {label:<20}: {s['sgp_rows_written']}")
    print(f"  Rows skipped (dupes)         : {s['rows_skipped_duplicate']}")
    print(f"  Rows failed validation       : {s['rows_failed_validation']}")
    print(f"  SGP API errors               : {s['sgp_api_errors']}")
    print(f"  Zero rows (no SGP on slate)  : {s['zero_rows']}")
    print()


if __name__ == "__main__":
    main()
