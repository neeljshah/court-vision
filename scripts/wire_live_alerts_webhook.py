"""wire_live_alerts_webhook.py — fan cycle-88k alerts to Slack/Discord.

Cycle 88k's `scripts/live_alerts.py` prints alerts to stdout + writes a
log line. For a betting operator who isn't watching the terminal those
are invisible. This wrapper re-runs the same `process_once` machinery
and *also* forwards every newly-fired alert through
:class:`WebhookNotifier`.

We DO NOT modify cycle 88k's detection logic — we wrap it and react to
its return value, so the source of truth for what counts as an alert
stays in one place.

CLI
---
    # Run once, post to whichever webhook env vars are configured:
    python scripts/wire_live_alerts_webhook.py --once

    # Daemon, custom min severity, override interval:
    python scripts/wire_live_alerts_webhook.py --interval 60 \\
        --min-severity medium

    # Restrict to specific alert types (mirrors cycle 88k's --types):
    python scripts/wire_live_alerts_webhook.py --types EDGE_FLIP,FOUL_TROUBLE

Environment variables (read by :class:`WebhookNotifier`):

    SLACK_ALERT_WEBHOOK    optional incoming webhook URL
    DISCORD_ALERT_WEBHOOK  optional incoming webhook URL

If neither is set the script still runs (cycle 88k's stdout + log
output continues to work) but no webhook traffic is generated. A
warning is logged at startup so the operator notices.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date as _date
from typing import Optional, Set

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.live_alerts as la  # noqa: E402
from src.notifications.webhook_alerts import (  # noqa: E402
    WebhookNotifier, notify_from_alert,
)

log = logging.getLogger("wire_live_alerts_webhook")


_SEVERITY_BY_TYPE = {
    "EDGE_FLIP":         "high",
    "PROJECTION_SHIFT":  "medium",
    "BLOWOUT_RISK":      "medium",
    "FOUL_TROUBLE":      "high",
    "INACTIVE_LATE":     "high",
}


def severity_for(alert: dict) -> str:
    """Map a cycle-88k alert type to a severity tier."""
    return _SEVERITY_BY_TYPE.get(str(alert.get("type", "")), "high")


def run_once(*, notifier: Optional[WebhookNotifier] = None,
             date_str: Optional[str] = None,
             threshold: float = la._DEFAULT_THRESHOLD,
             types: Optional[Set[str]] = None,
             project_dir: Optional[str] = None,
             ring_bell: bool = False,
             stream=None) -> tuple[int, int]:
    """One pass: detect via cycle 88k, fan to webhook.

    Returns ``(alerts_fired, webhook_successes)``.
    """
    notifier = notifier or WebhookNotifier()
    alerts = la.process_once(
        date_str=date_str, threshold=threshold, types=types,
        project_dir=project_dir, ring_bell=ring_bell, stream=stream,
    )
    successes = 0
    for alert in alerts:
        if notify_from_alert(notifier, alert,
                             severity=severity_for(alert)):
            successes += 1
    return len(alerts), successes


def run_daemon(*, notifier: Optional[WebhookNotifier] = None,
               interval: float = la._DEFAULT_INTERVAL,
               threshold: float = la._DEFAULT_THRESHOLD,
               types: Optional[Set[str]] = None,
               project_dir: Optional[str] = None,
               max_ticks: Optional[int] = None,
               ring_bell: bool = False,
               sleep_fn=time.sleep,
               stream=None) -> int:
    """Poll loop wrapping `run_once`. Returns number of ticks executed."""
    notifier = notifier or WebhookNotifier()
    ticks = 0
    while True:
        if max_ticks is not None and ticks >= max_ticks:
            break
        ticks += 1
        try:
            run_once(notifier=notifier, threshold=threshold, types=types,
                     project_dir=project_dir, ring_bell=ring_bell,
                     stream=stream)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("iter %d crashed: %s", ticks, exc)
        if max_ticks is not None and ticks >= max_ticks:
            break
        sleep_fn(interval)
    return ticks


def _configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main(argv: Optional[list[str]] = None) -> int:
    _configure_logging()
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true",
                    help="Single pass then exit (default: daemon).")
    ap.add_argument("--interval", type=float, default=la._DEFAULT_INTERVAL)
    ap.add_argument("--threshold", type=float, default=la._DEFAULT_THRESHOLD)
    ap.add_argument("--types", type=la._parse_types, default=None,
                    help="Comma-separated subset of cycle 88k alert types.")
    ap.add_argument("--min-severity", default="high",
                    choices=("info", "medium", "high"))
    ap.add_argument("--date", default=None)
    args = ap.parse_args(argv)

    notifier = WebhookNotifier(min_severity=args.min_severity)
    if not notifier.enabled():
        log.warning("No SLACK_ALERT_WEBHOOK or DISCORD_ALERT_WEBHOOK env "
                    "var set — webhook fan-out is a no-op. Cycle 88k "
                    "stdout/log alerts still fire.")
    types = args.types if args.types else set(la.ALERT_TYPES)
    date_str = args.date or _date.today().isoformat()

    if args.once:
        fired, posted = run_once(
            notifier=notifier, date_str=date_str,
            threshold=args.threshold, types=types,
        )
        log.info("one-shot: fired=%d posted=%d", fired, posted)
        return 0

    log.info("daemon: interval=%.1fs threshold=%.2f types=%s severity>=%s",
             args.interval, args.threshold, sorted(types), args.min_severity)
    run_daemon(
        notifier=notifier, interval=args.interval,
        threshold=args.threshold, types=types,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
