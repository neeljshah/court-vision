"""
scraper_monitor.py — Prometheus-format scraper health monitor.

Exposes metrics on http://localhost:9090/ (plain text, Prometheus exposition
format).  No external deps beyond stdlib + the project's own DB helpers.

Metrics published
-----------------
scraper_last_success_timestamp_seconds{source="<name>"}
    Unix timestamp of the most recent 'success' run for each source.
    Missing / never-succeeded sources emit 0.

scraper_last_run_status{source="<name>",status="<status>"}
    1 if the most recent run for this source has that status, else 0.
    status values: success | error | partial | running

Usage
-----
    # Run as a blocking HTTP server (Ctrl-C to stop):
    python -m src.monitoring.scraper_monitor

    # Or embed in another process:
    from src.monitoring.scraper_monitor import MonitorServer
    srv = MonitorServer(db_path="data/nba_ai.db", port=9090, stale_seconds=1800)
    srv.start()          # background thread — non-blocking
    # ...
    srv.stop()

Environment
-----------
    MONITOR_DB_PATH     SQLite database path (default: data/nba_ai.db)
    MONITOR_PORT        HTTP port (default: 9090)
    MONITOR_STALE_SEC   Staleness threshold in seconds (default: 1800 = 30 min)
    TELEGRAM_BOT_TOKEN  )  forwarded to telegram_alerter
    TELEGRAM_CHAT_ID    )
"""

from __future__ import annotations

import http.server
import logging
import os
import sqlite3
import threading
import time
from typing import Dict, List, NamedTuple, Optional

from src.monitoring.telegram_alerter import send_alert

log = logging.getLogger(__name__)

# ── defaults ────────────────────────────────────────────────────────────────
_DEFAULT_DB_PATH = os.environ.get("MONITOR_DB_PATH", "data/nba_ai.db")
_DEFAULT_PORT = int(os.environ.get("MONITOR_PORT", "9090"))
_DEFAULT_STALE_SEC = int(os.environ.get("MONITOR_STALE_SEC", "1800"))
_CHECK_INTERVAL_SEC = 60  # how often to poll for stale scrapers


class SourceState(NamedTuple):
    source: str
    last_success_ts: float  # Unix epoch, 0 if never succeeded
    last_status: str        # most recent run status


# ── DB helpers ───────────────────────────────────────────────────────────────

def _query_states(db_path: str) -> List[SourceState]:
    """Read scraper_runs and return one SourceState per source."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Most recent run_finished_at where status='success', per source
        cur.execute(
            """
            SELECT source,
                   MAX(run_finished_at) AS last_ok
            FROM   scraper_runs
            WHERE  status = 'success'
              AND  run_finished_at IS NOT NULL
            GROUP  BY source
            """
        )
        success_rows: Dict[str, Optional[str]] = {
            r["source"]: r["last_ok"] for r in cur.fetchall()
        }

        # Most recent status per source (any status)
        cur.execute(
            """
            SELECT source, status
            FROM   scraper_runs
            WHERE  run_started_at = (
                       SELECT MAX(run_started_at)
                       FROM   scraper_runs AS s2
                       WHERE  s2.source = scraper_runs.source
                   )
            """
        )
        latest_status: Dict[str, str] = {
            r["source"]: r["status"] for r in cur.fetchall()
        }
        conn.close()
    except sqlite3.OperationalError as exc:
        log.warning("DB query failed: %s", exc)
        return []

    states: List[SourceState] = []
    all_sources = set(success_rows) | set(latest_status)
    for src in sorted(all_sources):
        raw_ts = success_rows.get(src)
        ts: float = 0.0
        if raw_ts:
            try:
                import datetime
                dt = datetime.datetime.fromisoformat(raw_ts)
                ts = dt.timestamp()
            except (ValueError, TypeError):
                ts = 0.0
        states.append(
            SourceState(
                source=src,
                last_success_ts=ts,
                last_status=latest_status.get(src, "unknown"),
            )
        )
    return states


# ── Prometheus text format ────────────────────────────────────────────────────

def _render_metrics(states: List[SourceState]) -> str:
    """Return a Prometheus text-format payload for the given states."""
    lines: List[str] = []

    lines.append("# HELP scraper_last_success_timestamp_seconds "
                 "Unix timestamp of last successful scraper run")
    lines.append("# TYPE scraper_last_success_timestamp_seconds gauge")
    for s in states:
        lines.append(
            f'scraper_last_success_timestamp_seconds{{source="{s.source}"}} '
            f"{s.last_success_ts:.3f}"
        )

    all_statuses = ("success", "error", "partial", "running")
    lines.append("")
    lines.append("# HELP scraper_last_run_status "
                 "1 if the most recent run has this status")
    lines.append("# TYPE scraper_last_run_status gauge")
    for s in states:
        for st in all_statuses:
            val = 1 if s.last_status == st else 0
            lines.append(
                f'scraper_last_run_status{{source="{s.source}",status="{st}"}} {val}'
            )

    lines.append("")
    return "\n".join(lines)


# ── Staleness check + alerting ────────────────────────────────────────────────

def check_and_alert(
    states: List[SourceState],
    stale_seconds: int = _DEFAULT_STALE_SEC,
    now: Optional[float] = None,
) -> List[str]:
    """Return list of stale source names and fire Telegram alerts for each."""
    if now is None:
        now = time.time()

    stale: List[str] = []
    for s in states:
        age = now - s.last_success_ts if s.last_success_ts > 0 else float("inf")
        if age > stale_seconds:
            stale.append(s.source)
            mins = int(age // 60) if s.last_success_ts > 0 else None
            age_str = f"{mins}m" if mins is not None else "never"
            msg = (
                f"<b>Scraper stale</b>\n"
                f"source: <code>{s.source}</code>\n"
                f"last success: {age_str} ago\n"
                f"last status: {s.last_status}"
            )
            send_alert(msg)
            log.warning("Stale scraper: %s (last success %s)", s.source, age_str)

    return stale


# ── HTTP handler ──────────────────────────────────────────────────────────────

class _MetricsHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP handler — GET / returns Prometheus text."""

    monitor: "MonitorServer"  # injected by MonitorServer

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/", "/metrics"):
            self.send_response(404)
            self.end_headers()
            return
        body = self.server._get_metrics_body().encode()  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:  # silence access log
        pass


# ── MonitorServer ─────────────────────────────────────────────────────────────

class MonitorServer:
    """Background HTTP server + periodic staleness checker."""

    def __init__(
        self,
        db_path: str = _DEFAULT_DB_PATH,
        port: int = _DEFAULT_PORT,
        stale_seconds: int = _DEFAULT_STALE_SEC,
        check_interval: int = _CHECK_INTERVAL_SEC,
    ) -> None:
        self.db_path = db_path
        self.port = port
        self.stale_seconds = stale_seconds
        self.check_interval = check_interval
        self._states: List[SourceState] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._httpd: Optional[http.server.HTTPServer] = None
        self._http_thread: Optional[threading.Thread] = None
        self._check_thread: Optional[threading.Thread] = None

    # ── public API ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start HTTP server and check loop in background threads."""
        self._refresh_states()

        handler = _MetricsHandler
        handler.monitor = self  # type: ignore[attr-defined]

        server = http.server.HTTPServer(("", self.port), handler)
        server._get_metrics_body = self._get_metrics_body  # type: ignore[attr-defined]
        self._httpd = server

        self._http_thread = threading.Thread(
            target=server.serve_forever, daemon=True, name="scraper-monitor-http"
        )
        self._http_thread.start()
        log.info("Scraper monitor HTTP on :%s", self.port)

        self._check_thread = threading.Thread(
            target=self._check_loop, daemon=True, name="scraper-monitor-check"
        )
        self._check_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._httpd:
            self._httpd.shutdown()

    def get_states(self) -> List[SourceState]:
        with self._lock:
            return list(self._states)

    # ── internals ────────────────────────────────────────────────────────────

    def _refresh_states(self) -> None:
        states = _query_states(self.db_path)
        with self._lock:
            self._states = states

    def _get_metrics_body(self) -> str:
        with self._lock:
            return _render_metrics(self._states)

    def _check_loop(self) -> None:
        while not self._stop_event.is_set():
            self._refresh_states()
            with self._lock:
                states = list(self._states)
            check_and_alert(states, stale_seconds=self.stale_seconds)
            self._stop_event.wait(timeout=self.check_interval)


# ── CLI entry ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    srv = MonitorServer()
    srv.start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        srv.stop()
        log.info("Monitor stopped.")
