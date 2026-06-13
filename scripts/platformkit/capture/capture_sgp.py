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
from typing import Any, Dict, List, Optional, Set, Tuple

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from ledger_schema import record_key  # noqa: E402
from ledger_writer import append  # noqa: E402

# Re-export helpers so all existing import paths keep working.
from capture_sgp_builder import (  # noqa: E402
    classify_kind,
    make_sgp_market_tag,
    _build_sgp_rows,
    _load_seen_keys,
    _now_ts,
)
from capture_sgp_client import (  # noqa: E402
    SgpOddsAPIClient,
    _DryRunSgpStubClient,
)

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
    seen: Set[Tuple] = _load_seen_keys(ledger_root)

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
