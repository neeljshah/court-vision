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
    python scripts/platform/capture/capture_health.py \\
        --schedule data/schedules/nba_2026-06-12.json

Usage (offline + alert stub for testing):
    python scripts/platform/capture/capture_health.py --alert --dry-run

Public API (for tests):
    from capture_health import compute_gap_report, write_health_json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path wiring — importable standalone or from any CWD
# ---------------------------------------------------------------------------

_CAPTURE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CAPTURE_DIR.parents[2]

if str(_CAPTURE_DIR) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_DIR))

from ledger_writer import read_all as _read_all  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SPORT = "nba"
_HEALTH_STATE_PATH: Path = _REPO_ROOT / ".bot_state" / "capture_health.json"

# A game is considered "captured" if at least one row with kind="open" for
# its event_id exists in the ledger on the game's scheduled date.
_OPEN_KIND = "open"


# ---------------------------------------------------------------------------
# Schedule helpers
# ---------------------------------------------------------------------------

def _load_schedule(schedule_path: Path) -> List[Dict[str, Any]]:
    """Load a cached schedule JSON.

    Expected format — a JSON array of objects, each with at least::

        {"event_id": str, "game_date": "YYYY-MM-DD", "home": str, "away": str}

    The ``home`` / ``away`` fields are optional — used only for human-readable
    output; ``event_id`` and ``game_date`` are required.

    Args:
        schedule_path: Path to the JSON schedule file.

    Returns:
        List of game dicts.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the JSON is not a list.
    """
    if not schedule_path.exists():
        raise FileNotFoundError(
            f"Schedule file not found: {schedule_path}. "
            "Provide --schedule <path> or inject a schedule dict list."
        )
    with open(str(schedule_path), "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(
            f"Schedule file must contain a JSON array; got {type(data).__name__}."
        )
    return data


# ---------------------------------------------------------------------------
# Gap computation
# ---------------------------------------------------------------------------

def compute_gap_report(
    schedule: List[Dict[str, Any]],
    ledger_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Compute a gap report for the given game schedule.

    For each game in *schedule*, checks whether the forward-capture ledger
    contains at least one row with ``event_id == game["event_id"]`` and
    ``kind == "open"`` on the scheduled ``game_date``.  Games with no such
    row are reported as gaps (data loss).

    Args:
        schedule: List of game dicts.  Each must have ``event_id`` (str) and
            ``game_date`` (``"YYYY-MM-DD"`` str).
        ledger_root: Override the ledger root (default = ``data/lines/forward``
            under repo root).  Pass ``tmp_path`` in tests.

    Returns:
        A JSON-serialisable dict::

            {
                "generated_at": "<ISO-8601 UTC>",
                "sport": "nba",
                "games_checked": int,
                "games_captured": int,
                "gaps": [
                    {
                        "event_id": str,
                        "game_date": str,
                        "home": str | None,
                        "away": str | None,
                    },
                    ...
                ],
                "gap_count": int,
                "status": "ok" | "gap_detected",
            }
    """
    # Build a lookup: game_date → set of event_ids that have an "open" row.
    # We read the ledger once per date referenced by the schedule.
    dates_needed = {g.get("game_date", "") for g in schedule if g.get("game_date")}

    captured_by_date: Dict[str, set] = {}
    for date in dates_needed:
        if not date:
            continue
        rows = _read_all(_SPORT, date, ledger_root)
        captured_by_date[date] = {
            r["event_id"] for r in rows if r.get("kind") == _OPEN_KIND
        }

    gaps: List[Dict[str, Any]] = []
    games_captured = 0

    for game in schedule:
        eid = game.get("event_id", "").strip()
        gdate = game.get("game_date", "").strip()
        if not eid or not gdate:
            # Malformed entry — skip silently (not a capture failure)
            continue
        captured_ids = captured_by_date.get(gdate, set())
        if eid in captured_ids:
            games_captured += 1
        else:
            gaps.append({
                "event_id": eid,
                "game_date": gdate,
                "home": game.get("home") or None,
                "away": game.get("away") or None,
            })

    games_checked = len(
        [g for g in schedule if g.get("event_id", "").strip() and g.get("game_date", "").strip()]
    )

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sport": _SPORT,
        "games_checked": games_checked,
        "games_captured": games_captured,
        "gaps": gaps,
        "gap_count": len(gaps),
        "status": "ok" if not gaps else "gap_detected",
    }


# ---------------------------------------------------------------------------
# Health JSON writer — idempotent overwrite
# ---------------------------------------------------------------------------

def write_health_json(
    report: Dict[str, Any],
    out_path: Optional[Path] = None,
) -> Path:
    """Write the gap report to a health JSON file, overwriting any prior run.

    The write is atomic: data is written to a ``.tmp`` sibling first, then
    ``os.replace()`` swaps it in so concurrent readers never see a torn file.

    Args:
        report: JSON-serialisable dict returned by :func:`compute_gap_report`.
        out_path: Override output path (default = ``.bot_state/capture_health.json``).

    Returns:
        The ``Path`` that was written.
    """
    target = out_path if out_path is not None else _HEALTH_STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / (target.name + ".tmp")
    with open(str(tmp), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    os.replace(str(tmp), str(target))
    return target


# ---------------------------------------------------------------------------
# Alert dispatcher — injectable for tests
# ---------------------------------------------------------------------------

AlertFn = Callable[[str, List[Dict[str, Any]]], None]
"""Type alias for an injectable alert callback.

Called as ``alert_fn(message, gaps)`` where *message* is a human-readable
summary and *gaps* is the list of gap dicts from the report.
"""


def _default_alert_fn(message: str, gaps: List[Dict[str, Any]]) -> None:
    """Production alert: delegates to the existing layered webhook helper.

    Imports ``src.alerts.discord_webhook.alert`` at call time so the module
    stays importable without the full ``src/`` tree on PYTHONPATH — the import
    only happens when ``--alert`` is actually used.
    """
    try:
        sys.path.insert(0, str(_REPO_ROOT))
        from src.alerts.discord_webhook import alert as _discord_alert  # type: ignore[import]
        _discord_alert(
            message,
            level="warn",
            tag="capture_health",
            body=json.dumps(gaps, indent=2),
        )
    except ImportError:
        # Graceful degradation: webhook module absent → print to stderr only
        print(f"[capture_health] ALERT (webhook unavailable): {message}", file=sys.stderr)


def maybe_alert(
    report: Dict[str, Any],
    alert_fn: Optional[AlertFn] = None,
) -> bool:
    """Fire an alert if the report contains gaps.

    Args:
        report: Gap report dict from :func:`compute_gap_report`.
        alert_fn: Injectable alert callback.  ``None`` → production
            :func:`_default_alert_fn`.  Tests pass a stub.

    Returns:
        ``True`` if an alert was fired (gaps exist), ``False`` otherwise.
    """
    if not report.get("gaps"):
        return False

    fn = alert_fn if alert_fn is not None else _default_alert_fn
    gap_count = report["gap_count"]
    games_checked = report["games_checked"]
    msg = (
        f"[capture_health] {gap_count}/{games_checked} game(s) missing "
        f"opener rows in the forward ledger: "
        + ", ".join(g["event_id"] for g in report["gaps"])
    )
    fn(msg, report["gaps"])
    return True


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
