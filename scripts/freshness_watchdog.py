"""freshness_watchdog.py — per-book staleness + low-volume monitor for CourtVision.

Runs as a long-lived asyncio task (started via task_supervisor).  Every
POLL_INTERVAL_SEC it reads the latest CSV for each registered book, checks:

  1. STALENESS  — if the most-recent row's captured_at is > STALE_THRESHOLD_SEC
                  old the book is flagged STALE.  Three consecutive stale checks
                  → alert emitted.

  2. LOW_VOLUME — rolling 24 h max of rows-per-tick is stored in
                  data/cache/scraper_baselines.json.  If the current tick writes
                  < 50 % of that baseline for 3 consecutive ticks → LOW_VOLUME alert.

Alerts are written to data/cache/staleness_alerts.jsonl and, when
SLACK_WEBHOOK_URL env var is set, POSTed to the Slack incoming-webhook URL.
A TOPIC_BOOK_STALE event is also published on the shared event bus.

/api/health/books endpoint response (handled in live_v2_app.py):
    {
      "books": {
        "dk":        {"csv_age_sec": 8,   "status": "ok",    "last_capture": "..."},
        "pin":       {"csv_age_sec": 412, "status": "STALE", "stale_for_checks": 7},
        "pointsbet": {"csv_age_sec": 91,  "status": "ok",    "last_capture": "..."}
      },
      "overall": "degraded" | "healthy"
    }
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import sys
import time
from datetime import date as _date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger("freshness_watchdog")

# ── constants ─────────────────────────────────────────────────────────────────
POLL_INTERVAL_SEC = 60
STALE_THRESHOLD_SEC = 300          # 5 minutes
STALE_ALERT_AFTER_N_CHECKS = 3
LOW_VOLUME_FRACTION = 0.50         # < 50 % of baseline
LOW_VOLUME_ALERT_AFTER_N_CHECKS = 3

LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
ALERTS_PATH = os.path.join(CACHE_DIR, "staleness_alerts.jsonl")
BASELINES_PATH = os.path.join(CACHE_DIR, "scraper_baselines.json")

# Canonical book names → CSV filename suffix pattern (date-prefixed)
# Format: data/lines/<date>_<suffix>.csv
BOOK_CSV_SUFFIX: Dict[str, str] = {
    "dk":         "dk",
    "fd":         "fd",
    "betrivers":  "betrivers",
    "pointsbet":  "pointsbet",
    "pin":        "pin",
    "bov":        "bov",
}

# ── module-level state shared with /api/health/books ─────────────────────────
# Keyed by book name.  Updated in-place each poll cycle so the REST endpoint
# always returns the last observed state without blocking on disk I/O.
_book_status: Dict[str, Dict[str, Any]] = {}


# ── baseline persistence ──────────────────────────────────────────────────────

def _load_baselines() -> Dict[str, Any]:
    try:
        with open(BASELINES_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_baselines(data: Dict[str, Any]) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(BASELINES_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError as exc:
        log.warning("could not save baselines: %s", exc)


# ── alert helpers ─────────────────────────────────────────────────────────────

def _append_alert(alert: Dict[str, Any]) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(ALERTS_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(alert) + "\n")
    except OSError as exc:
        log.warning("could not write alert: %s", exc)


async def _slack_post(msg: str) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        import urllib.request
        payload = json.dumps({"text": msg}).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, urllib.request.urlopen, req)
    except Exception as exc:  # noqa: BLE001
        log.warning("Slack webhook failed: %s", exc)


async def _emit_alert(book: str, kind: str, detail: str) -> None:
    """Persist + Slack + event-bus publish for one alert."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    alert: Dict[str, Any] = {
        "ts": ts, "book": book, "kind": kind, "detail": detail,
    }
    log.warning("[watchdog] ALERT book=%s kind=%s %s", book, kind, detail)
    _append_alert(alert)
    await _slack_post(f":warning: CourtVision watchdog | book={book} | {kind} | {detail}")
    # Publish on event bus (import lazily so this module is importable standalone)
    try:
        from src.live.event_bus import TOPIC_BOOK_STALE, get_bus
        bus = get_bus()
        await bus.publish(TOPIC_BOOK_STALE, alert)
    except Exception as exc:  # noqa: BLE001
        log.debug("event-bus publish skipped: %s", exc)


# ── CSV inspection ────────────────────────────────────────────────────────────

def _latest_csv_path(book: str, date_str: str) -> Optional[str]:
    """Return path to today's CSV for *book*, or None if absent."""
    suffix = BOOK_CSV_SUFFIX.get(book)
    if not suffix:
        return None
    path = os.path.join(LINES_DIR, f"{date_str}_{suffix}.csv")
    return path if os.path.isfile(path) else None


def _read_last_captured_at(path: str) -> Optional[float]:
    """Return the epoch float of the most-recent captured_at in *path*, or None."""
    last_ts: Optional[float] = None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                raw = row.get("captured_at") or ""
                if not raw:
                    continue
                try:
                    # Support ISO formats with or without 'Z'.
                    raw_clean = raw.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(raw_clean)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    ts = dt.timestamp()
                    if last_ts is None or ts > last_ts:
                        last_ts = ts
                except (ValueError, TypeError):
                    continue
    except OSError:
        pass
    return last_ts


def _count_rows(path: str) -> int:
    """Count data rows (excluding header) in a CSV file."""
    count = 0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            next(reader, None)  # skip header
            for _ in reader:
                count += 1
    except OSError:
        pass
    return count


# ── public helper called by /api/health/books ─────────────────────────────────

def check_book_freshness(date_str: Optional[str] = None) -> Dict[str, Any]:
    """Synchronous snapshot of the last-known book status.

    Returns the same structure as the /api/health/books JSON response.
    Suitable for import by live_v2_app.py.

    Args:
        date_str: ISO date string to override today (used for testing).
    """
    if date_str is None:
        date_str = _date.today().isoformat()

    now = time.time()
    result: Dict[str, Any] = {}

    for book in BOOK_CSV_SUFFIX:
        # Prefer the live in-memory state updated by the watchdog loop.
        if book in _book_status:
            result[book] = dict(_book_status[book])
            continue

        # Fallback: compute fresh from disk (used when watchdog hasn't started yet).
        path = _latest_csv_path(book, date_str)
        if path is None:
            result[book] = {
                "csv_age_sec": None,
                "status": "NO_DATA",
                "last_capture": None,
                "stale_for_checks": 0,
            }
            continue

        last_ts = _read_last_captured_at(path)
        if last_ts is None:
            result[book] = {
                "csv_age_sec": None,
                "status": "NO_DATA",
                "last_capture": None,
                "stale_for_checks": 0,
            }
        else:
            age = now - last_ts
            status = "STALE" if age > STALE_THRESHOLD_SEC else "ok"
            result[book] = {
                "csv_age_sec": round(age, 1),
                "status": status,
                "last_capture": datetime.utcfromtimestamp(last_ts).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"),
                "stale_for_checks": 0,
            }

    overall = ("degraded"
               if any(b.get("status") not in ("ok",) for b in result.values())
               else "healthy")
    return {"books": result, "overall": overall}


# ── main watchdog loop ────────────────────────────────────────────────────────

async def run_freshness_watchdog() -> None:
    """Long-running coroutine.  Intended to be started via task_supervisor."""
    log.info("[watchdog] starting; poll_interval=%ds stale_threshold=%ds",
             POLL_INTERVAL_SEC, STALE_THRESHOLD_SEC)

    # Per-book consecutive failure counters.
    stale_count: Dict[str, int] = {b: 0 for b in BOOK_CSV_SUFFIX}
    low_vol_count: Dict[str, int] = {b: 0 for b in BOOK_CSV_SUFFIX}
    # Track last row-count per book (used for low-volume detection).
    last_row_count: Dict[str, int] = {b: 0 for b in BOOK_CSV_SUFFIX}

    # Load persisted baselines.
    baselines: Dict[str, Any] = _load_baselines()

    while True:
        await asyncio.sleep(POLL_INTERVAL_SEC)
        date_str = _date.today().isoformat()
        now = time.time()

        for book in BOOK_CSV_SUFFIX:
            path = _latest_csv_path(book, date_str)

            if path is None:
                _book_status[book] = {
                    "csv_age_sec": None,
                    "status": "NO_DATA",
                    "last_capture": None,
                    "stale_for_checks": stale_count[book],
                }
                # Don't count missing file as stale — scraper may not have
                # run for today yet (off-season, no games scheduled).
                stale_count[book] = 0
                continue

            # ── staleness check ───────────────────────────────────────────
            last_ts = _read_last_captured_at(path)
            age: Optional[float] = (now - last_ts) if last_ts is not None else None

            if age is not None and age > STALE_THRESHOLD_SEC:
                stale_count[book] += 1
                status = "STALE"
                if stale_count[book] == STALE_ALERT_AFTER_N_CHECKS:
                    await _emit_alert(
                        book, "STALE",
                        f"csv_age={age:.0f}s > {STALE_THRESHOLD_SEC}s for "
                        f"{stale_count[book]} consecutive checks",
                    )
            else:
                stale_count[book] = 0
                status = "ok"

            last_cap_str = (
                datetime.utcfromtimestamp(last_ts).strftime("%Y-%m-%dT%H:%M:%SZ")
                if last_ts is not None else None
            )

            _book_status[book] = {
                "csv_age_sec": round(age, 1) if age is not None else None,
                "status": status,
                "last_capture": last_cap_str,
                "stale_for_checks": stale_count[book],
            }

            # ── low-volume check ──────────────────────────────────────────
            current_rows = _count_rows(path)
            row_delta = max(0, current_rows - last_row_count[book])
            last_row_count[book] = current_rows

            # Update rolling 24 h max baseline.
            book_bl = baselines.setdefault(book, {})
            prev_max: int = book_bl.get("max_rows_per_tick", 0)
            if row_delta > prev_max:
                book_bl["max_rows_per_tick"] = row_delta
                book_bl["max_updated_at"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                _save_baselines(baselines)

            max_tick: int = book_bl.get("max_rows_per_tick", 0)
            if max_tick > 0 and row_delta < LOW_VOLUME_FRACTION * max_tick:
                low_vol_count[book] += 1
                _book_status[book]["low_volume"] = True
                if low_vol_count[book] == LOW_VOLUME_ALERT_AFTER_N_CHECKS:
                    await _emit_alert(
                        book, "LOW_VOLUME",
                        f"tick_rows={row_delta} < 50% of baseline={max_tick} for "
                        f"{low_vol_count[book]} consecutive ticks",
                    )
            else:
                low_vol_count[book] = 0
                _book_status[book]["low_volume"] = False

        log.debug("[watchdog] tick done; statuses=%s",
                  {b: s.get("status") for b, s in _book_status.items()})


if __name__ == "__main__":
    # Quick import / standalone smoke test.
    result = check_book_freshness("2026-05-27")
    print(json.dumps(result, indent=2))
