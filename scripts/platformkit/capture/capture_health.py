"""capture_health.py — N-CLV-005a: offline capture gap monitor.

Computes a GAP REPORT: given a game-day schedule (injected or read from a
cached JSON file), determines which games have NO ``kind="open"`` row in the
forward-capture ledger and therefore represent data-loss gaps.

Supports an opt-in ``--alert`` flag that calls an injectable webhook function
(tests pass a stub — no real network is ever touched by this module).

Writes a health JSON to ``.bot_state/capture_health.json`` idempotently
(each run overwrites the previous result — no append, no duplication).

Windows-scheduled-task registration and the live webhook URL are a SEPARATE
task (N-CLV-005b) — NOT implemented here.

Usage (offline, no alert):
    python scripts/platformkit/capture/capture_health.py \\
        --schedule data/schedules/nba_2026-06-12.json

Usage (offline + alert stub for testing):
    python scripts/platformkit/capture/capture_health.py --alert --dry-run

Public API (for tests):
    from capture_health import compute_gap_report, write_health_json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path wiring — importable standalone or from any CWD
# ---------------------------------------------------------------------------

_CAPTURE_DIR = Path(__file__).resolve().parent

if str(_CAPTURE_DIR) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_DIR))

# Re-export everything from the compute helper so all existing import paths
# remain valid (tests do: from capture_health import compute_gap_report, ...).
from capture_health_compute import (  # noqa: E402
    _HEALTH_STATE_PATH,
    _OPEN_KIND,
    _SPORT,
    AlertFn,
    _default_alert_fn,
    _load_schedule,
    compute_gap_report,
    maybe_alert,
    write_health_json,
)

__all__ = [
    "_HEALTH_STATE_PATH",
    "_OPEN_KIND",
    "_SPORT",
    "AlertFn",
    "_default_alert_fn",
    "_load_schedule",
    "compute_gap_report",
    "maybe_alert",
    "write_health_json",
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for the offline gap monitor (N-CLV-005a)."""
    parser = argparse.ArgumentParser(
        description="N-CLV-005a — offline capture gap monitor.",
    )
    parser.add_argument(
        "--schedule",
        metavar="PATH",
        help=(
            "Path to a cached game-day schedule JSON "
            "(array of {event_id, game_date, home, away} objects). "
            "Required unless running in --dry-run mode."
        ),
    )
    parser.add_argument(
        "--alert",
        action="store_true",
        help="Fire a webhook alert (via src.alerts.discord_webhook) if gaps are found.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Use a built-in synthetic schedule for offline testing. "
            "Writes to .bot_state/ but fires no real webhook."
        ),
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        default=None,
        help=f"Override the health JSON output path (default: {_HEALTH_STATE_PATH}).",
    )
    args = parser.parse_args()

    if args.dry_run:
        # Synthetic offline schedule — zero network, zero ledger reads needed.
        schedule = [
            {"event_id": "dry_nba_001", "game_date": "2030-01-15",
             "home": "New York Knicks", "away": "San Antonio Spurs"},
        ]
    elif args.schedule:
        schedule = _load_schedule(Path(args.schedule))
    else:
        parser.error("Provide --schedule <path> or use --dry-run.")
        return  # unreachable; satisfies type checkers

    report = compute_gap_report(schedule)
    out_path = Path(args.out) if args.out else None
    written = write_health_json(report, out_path)

    alerted = False
    if args.alert:
        alerted = maybe_alert(report)

    print(json.dumps(report, indent=2))
    print(f"\n[capture_health] health JSON written → {written}")
    if alerted:
        print(f"[capture_health] alert fired for {report['gap_count']} gap(s).")


if __name__ == "__main__":
    main()
