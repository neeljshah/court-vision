"""live_inplay_daemon.py — operational glue between cycle-88a + 88n.

Cycle 93e (loop 5). Cycle 88a's `live_game_poll.py` writes one JSON
snapshot per game per tick to `data/live/`. Cycle 88n's
`save_live_predictions.py` reads the LATEST snapshot for each game and
appends one row per (player, stat) to
`data/predictions/<date>_inplay.csv` — but only when the user invokes
it. Cycle 89e's `probe_inplay_vs_pregame.py` is the consumer: it
expects the in-play ledger to accumulate over the course of a game so
it can compute per-quarter MAE.

Until this script existed, the in-play ledger never accumulated:
nothing was driving the periodic save. live_run.py (cycle 88h) chains
sub-processes but doesn't call save_live_predictions per snapshot.

This daemon plugs that gap. Every --interval-min minutes it:

    1. Discovers today's slate via scripts.live_game_poll.
    2. Polls every game id via the cycle-88a CDN fetch helper, writing
       one snapshot JSON per game to data/live/ (the same dir cycle 88n
       reads from).
    3. For each game whose snapshot is LIVE, derives in-play
       projections via save_live_predictions.derive_inplay_predictions
       and appends them to data/predictions/<date>_inplay.csv.
    4. Prints one status line and rotates the daemon log.

Design constraints
------------------
* Offseason safe — no slate → no-op, daemon stays up until
  ``--max-iterations`` or auto-stop kicks in.
* No modifications to cycle-88a or cycle-88n source. We import their
  helpers and reuse the pure functions only.
* Transient API errors get exactly one 30-second retry. A second
  failure logs and is dropped (next iteration retries the slate).
* Ctrl-C writes a ``data/live_daemon.stopped`` sentinel so external
  monitors can detect a clean shutdown vs a crash.

CLI
---
    python scripts/live_inplay_daemon.py
    python scripts/live_inplay_daemon.py --interval-min 5 --max-iterations 12
    python scripts/live_inplay_daemon.py --dry-run        # plan + exit
    python scripts/live_inplay_daemon.py --auto-stop-iters 6   # quit after
                                                                 6 empty ticks
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date as _date_cls, datetime
from logging.handlers import RotatingFileHandler
from typing import Callable, Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Cycle-88a + 88n helpers. We import the *modules* (not the functions)
# so monkey-patching in tests is straightforward.
import scripts.live_game_poll as lgp  # noqa: E402
import scripts.save_live_predictions as slp  # noqa: E402

# ── constants ─────────────────────────────────────────────────────────────

DEFAULT_INTERVAL_MIN: float = 5.0
DEFAULT_AUTO_STOP_ITERS: int = 6   # 6 empty ticks ≈ 30 min @ 5-min interval
RETRY_SLEEP_S: float = 30.0
SECONDS_PER_MIN: float = 60.0

LOG_PATH = os.path.join(PROJECT_DIR, "data", "live_daemon.log")
STOPPED_SENTINEL = os.path.join(PROJECT_DIR, "data", "live_daemon.stopped")
LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")
PRED_DIR = os.path.join(PROJECT_DIR, "data", "predictions")


# ── logging setup ─────────────────────────────────────────────────────────

def configure_logger(log_path: str = LOG_PATH,
                       *, level: int = logging.INFO) -> logging.Logger:
    """Wire a rotating file handler + stdout handler. Idempotent."""
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    log = logging.getLogger("live_inplay_daemon")
    if log.handlers:
        return log
    log.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3)
    fh.setFormatter(fmt)
    log.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)
    log.propagate = False
    return log


# ── iteration logic ───────────────────────────────────────────────────────

class IterationResult:
    """Lightweight DTO so tests + status-print can introspect each tick."""

    __slots__ = ("active_count", "snapshots_written", "inplay_rows",
                 "had_error", "date_str")

    def __init__(self, active_count: int, snapshots_written: int,
                 inplay_rows: int, had_error: bool, date_str: str) -> None:
        self.active_count = active_count
        self.snapshots_written = snapshots_written
        self.inplay_rows = inplay_rows
        self.had_error = had_error
        self.date_str = date_str

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return (f"IterationResult(active={self.active_count}, "
                f"snaps={self.snapshots_written}, "
                f"inplay={self.inplay_rows}, err={self.had_error})")


def _retry_once(fn: Callable[[], object], *,
                  sleep_fn: Callable[[float], None],
                  logger: logging.Logger,
                  retry_sleep: float = RETRY_SLEEP_S):
    """Run ``fn`` once. If it raises, sleep ``retry_sleep`` and retry once.

    Returns whatever ``fn()`` returns on success. Re-raises on second
    failure so the caller can log + continue to the next iteration.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - intentional broad catch
        logger.warning("transient error: %s; retrying in %.0fs",
                        exc, retry_sleep)
        sleep_fn(retry_sleep)
        return fn()


def run_one_iteration(*,
                       date_str: Optional[str] = None,
                       live_dir: str = LIVE_DIR,
                       pred_dir: str = PRED_DIR,
                       dry_run: bool = False,
                       sleep_fn: Callable[[float], None] = time.sleep,
                       logger: Optional[logging.Logger] = None,
                       discover_fn: Optional[Callable[[Optional[str]], List[str]]] = None,
                       fetch_fn: Optional[Callable[[str], dict]] = None,
                       trigger_alerts: bool = False,
                       alert_threshold: float = 3.0,
                       alert_min_severity: str = "high",
                       ) -> IterationResult:
    """One poll + save pass. Pure of side effects when ``dry_run=True``."""
    log = logger or configure_logger()
    date_str = date_str or _date_cls.today().isoformat()
    discover_fn = discover_fn or lgp.discover_games_for_today
    fetch_fn = fetch_fn or lgp.fetch_live_boxscore

    # 1) Discover the slate (with one retry).
    try:
        game_ids = _retry_once(lambda: discover_fn(date_str),
                                  sleep_fn=sleep_fn, logger=log) or []
    except Exception as exc:  # noqa: BLE001
        log.error("slate discovery failed twice: %s", exc)
        return IterationResult(0, 0, 0, True, date_str)

    if not game_ids:
        log.info("[%s] no slate today; nothing to poll.", date_str)
        return IterationResult(0, 0, 0, False, date_str)

    if dry_run:
        log.info("[dry-run] would poll %d game(s) -> %s",
                  len(game_ids), live_dir)
        return IterationResult(len(game_ids), 0, 0, False, date_str)

    # 2) Poll once across the slate. lgp.poll_once writes the JSON
    #    snapshots and returns {game_id: snapshot_dict}.
    try:
        snapshots = _retry_once(
            lambda: lgp.poll_once(game_ids,
                                       fetch_fn=fetch_fn,
                                       sleep_fn=lambda _s: None,
                                       api_sleep=0.0,
                                       live_dir=live_dir),
            sleep_fn=sleep_fn, logger=log,
        ) or {}
    except Exception as exc:  # noqa: BLE001
        log.error("poll_once failed twice: %s", exc)
        return IterationResult(0, 0, 0, True, date_str)

    snapshots_written = len(snapshots)

    # 3) Derive in-play projections for every LIVE snapshot and append.
    out_path = os.path.join(pred_dir, f"{date_str}_inplay.csv")
    inplay_total = 0
    active_count = 0
    for gid, snap in snapshots.items():
        if (snap or {}).get("game_status") != "LIVE":
            continue
        active_count += 1
        try:
            rows = slp.derive_inplay_predictions(snap, date_str)
        except Exception as exc:  # noqa: BLE001
            log.warning("derive_inplay_predictions failed for %s: %s",
                          gid, exc)
            continue
        if not rows:
            continue
        try:
            inplay_total += slp.append_to_ledger(rows, out_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("append_to_ledger failed for %s: %s", gid, exc)

    # 4) (Optional) fan cycle-88k alerts through the webhook notifier.
    if trigger_alerts:
        try:
            # Imported lazily so the daemon's hot path doesn't pay the
            # cost (and so missing optional deps never block the poller).
            from scripts.wire_live_alerts_webhook import run_once as _alert_run
            from src.notifications.webhook_alerts import WebhookNotifier
            notifier = WebhookNotifier(min_severity=alert_min_severity)
            fired, posted = _alert_run(
                notifier=notifier, date_str=date_str,
                threshold=alert_threshold,
            )
            if fired:
                log.info("[%s] alerts fired=%d posted=%d", date_str,
                          fired, posted)
        except Exception as exc:  # noqa: BLE001 - alerts must never crash the poller
            log.warning("alert trigger failed: %s", exc)

    log.info("[%s] active=%d snapshots=%d inplay_rows=%d",
              date_str, active_count, snapshots_written, inplay_total)
    return IterationResult(active_count, snapshots_written,
                              inplay_total, False, date_str)


# ── main loop ─────────────────────────────────────────────────────────────

def run_daemon(*,
                interval_min: float = DEFAULT_INTERVAL_MIN,
                max_iterations: Optional[int] = None,
                auto_stop_iters: int = DEFAULT_AUTO_STOP_ITERS,
                dry_run: bool = False,
                date_str: Optional[str] = None,
                live_dir: str = LIVE_DIR,
                pred_dir: str = PRED_DIR,
                sleep_fn: Callable[[float], None] = time.sleep,
                logger: Optional[logging.Logger] = None,
                trigger_alerts: bool = False,
                alert_threshold: float = 3.0,
                alert_min_severity: str = "high",
                ) -> int:
    """Drive the iteration loop. Returns total iterations executed."""
    log = logger or configure_logger()
    # Clear any prior stopped-sentinel so a fresh run isn't misread.
    try:
        if os.path.exists(STOPPED_SENTINEL):
            os.remove(STOPPED_SENTINEL)
    except OSError:
        pass

    log.info("daemon start: interval=%.1fmin max_iter=%s auto_stop=%d "
              "dry_run=%s", interval_min, max_iterations,
              auto_stop_iters, dry_run)

    interval_s = max(0.0, interval_min * SECONDS_PER_MIN)
    iters = 0
    empty_streak = 0
    try:
        while True:
            if max_iterations is not None and iters >= max_iterations:
                log.info("max_iterations reached (%d); exiting", iters)
                break
            iters += 1
            try:
                result = run_one_iteration(
                    date_str=date_str, live_dir=live_dir,
                    pred_dir=pred_dir, dry_run=dry_run,
                    sleep_fn=sleep_fn, logger=log,
                    trigger_alerts=trigger_alerts,
                    alert_threshold=alert_threshold,
                    alert_min_severity=alert_min_severity,
                )
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001
                log.error("iteration crashed: %s", exc)
                result = IterationResult(0, 0, 0, True,
                                            date_str or _date_cls.today().isoformat())

            if result.active_count == 0:
                empty_streak += 1
            else:
                empty_streak = 0

            if auto_stop_iters > 0 and empty_streak >= auto_stop_iters:
                log.info("auto-stop: %d consecutive empty iterations; exiting",
                          empty_streak)
                break

            if max_iterations is not None and iters >= max_iterations:
                continue   # outer loop check will catch it
            sleep_fn(interval_s)
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt — graceful shutdown")
    finally:
        _write_stopped_sentinel(log)

    log.info("daemon stop: ran %d iteration(s)", iters)
    return iters


def _write_stopped_sentinel(log: logging.Logger) -> None:
    try:
        os.makedirs(os.path.dirname(STOPPED_SENTINEL) or ".", exist_ok=True)
        with open(STOPPED_SENTINEL, "w", encoding="utf-8") as fh:
            fh.write(datetime.now().isoformat() + "\n")
    except OSError as exc:
        log.warning("could not write stopped sentinel: %s", exc)


# ── CLI ───────────────────────────────────────────────────────────────────

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Poll active NBA games every N minutes and accumulate "
                    "in-play predictions into data/predictions/<date>_inplay.csv.")
    ap.add_argument("--interval-min", type=float, default=DEFAULT_INTERVAL_MIN,
                    help="Minutes between polls (default 5).")
    ap.add_argument("--max-iterations", type=int, default=None,
                    help="Stop after this many iterations (default: infinite).")
    ap.add_argument("--auto-stop-iters", type=int, default=DEFAULT_AUTO_STOP_ITERS,
                    help="Stop after N consecutive iterations with zero active "
                         "games (default 6; set 0 to disable).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Discover the slate + log the plan, write nothing.")
    ap.add_argument("--date", default=None,
                    help="Override the slate date (default: today).")
    ap.add_argument("--trigger-alerts", action="store_true",
                    help="After each poll, run cycle 88k alert detection "
                         "and fan results to Slack/Discord via "
                         "src.notifications.webhook_alerts (env: "
                         "SLACK_ALERT_WEBHOOK / DISCORD_ALERT_WEBHOOK).")
    ap.add_argument("--alert-threshold", type=float, default=3.0,
                    help="PROJECTION_SHIFT threshold (stat units, default 3.0).")
    ap.add_argument("--alert-min-severity", default="high",
                    choices=("info", "medium", "high"),
                    help="Drop alerts below this severity (default high).")
    return ap.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    log = configure_logger()
    iters = run_daemon(
        interval_min=args.interval_min,
        max_iterations=args.max_iterations,
        auto_stop_iters=args.auto_stop_iters,
        dry_run=args.dry_run,
        date_str=args.date,
        logger=log,
        trigger_alerts=args.trigger_alerts,
        alert_threshold=args.alert_threshold,
        alert_min_severity=args.alert_min_severity,
    )
    return 0 if iters >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
