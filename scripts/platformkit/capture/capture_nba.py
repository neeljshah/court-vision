"""capture_nba.py — NBA opener/close capture job (N-CLV-002).

Snapshots spread/total/ML + 7 prop markets; writes via N-CLV-001 ledger writer.
kind in {open, move, close}: first-seen=open, T-60=move, T-5=close.
Idempotent per (sport, event_id, market, book, side, kind) — reruns write 0 dupes.
Offline-safe: --dry-run uses a stub client; no ODDS_API_KEY required.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from ledger_writer import append  # noqa: E402

# Re-export all public names from the helper so all existing import paths resolve.
from capture_nba_client import (  # noqa: E402
    _SPORT,
    _SOURCE,
    _ODDS_API_KEY_ENV,
    _PROP_MARKETS,
    _MAINLINE_MAP,
    _CLOSE_MIN,
    _MOVE_MIN,
    classify_kind,
    OddsAPIClient,
    _now_ts,
    _build_mainline_rows,
    _build_prop_rows,
    _load_seen_keys,
    _DryRunStubClient,
)
from ledger_schema import record_key  # noqa: E402


# ---------------------------------------------------------------------------
# Core capture
# ---------------------------------------------------------------------------

def run_capture(
    dry_run: bool = False,
    ledger_root: Optional[Path] = None,
    client: Optional[Any] = None,
    now_utc: Optional[Any] = None,
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
