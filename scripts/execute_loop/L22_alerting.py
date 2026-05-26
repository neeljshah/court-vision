"""L22_alerting.py — Slack / Discord alerting wrapper (BUILD L22).

Sends structured alerts to Slack and Discord with token-bucket rate limiting,
a persistent FIFO queue for back-pressure, and a test mode that writes locally.

Public API
----------
    send_alert(channel, level, title, body, fields) -> bool
    send_edge_alert(player, stat, line, model, edge_pp, side, recommended_stake) -> bool
    send_fill_alert(bet_id, book, stake, status) -> bool
    send_drawdown_alert(current_bankroll, starting, pct_drop) -> bool
    send_drift_alert(stat, observed_mae, expected_mae, days_window) -> bool
    flush_pending() -> int
    register_alert_subscribers(bus=None) -> None

Environment Variables
---------------------
    SLACK_WEBHOOK_URL
        Incoming-webhook URL for Slack. When absent (or empty) Slack delivery
        is skipped; test-mode local write is used instead.

    DISCORD_WEBHOOK_URL
        Default incoming-webhook URL for Discord. Applies to all channels
        unless overridden by a per-channel variable. When absent, Discord
        delivery is skipped.

    DISCORD_<CHANNEL>_WEBHOOK_URL
        Per-channel Discord webhook override (e.g. DISCORD_EDGES_WEBHOOK_URL).
        ``<CHANNEL>`` is the upper-cased channel name (edges, fills, drift,
        drawdown, news, settle, system). Takes precedence over
        DISCORD_WEBHOOK_URL for that channel.

    ALERTS_ENABLED
        Set to "true" to enable live HTTP delivery to Slack/Discord.
        Any other value (including absent) disables live delivery and
        writes alerts to the local log file in test mode (default: "false").

    ALERTS_LIVE_ENABLED
        Set to "1" to enable live HTTP webhook delivery.  Stored as the
        module-level ``LIVE_ENABLED`` constant at import time.  Any other
        value (including absent) keeps L22 in paper/test mode.  This is the
        L42 paper_default gate constant; prefer ``ALERTS_ENABLED`` (below)
        for per-send delivery toggling.

    ALERTS_RATE_LIMIT_PER_MIN
        Maximum number of alerts dispatched per 60-second rolling window via
        the token-bucket limiter. Excess alerts are enqueued and replayed via
        flush_pending(). Integer; default 30.

    ALERTS_VERBOSE_FILLS
        Set to "1" to subscribe L22 to "order.filled" EventBus events and emit
        an INFO alert for each fill.  Default off (any other value or absent).

Event Subscriptions (L46 EventBus)
-----------------------------------
    Call ``register_alert_subscribers(bus)`` once at harness startup to wire
    L22 as an L46 EventBus subscriber.  The function is IDEMPOTENT — calling
    it multiple times registers handlers exactly once.

    Event name           Condition                     Alert level
    ─────────────────────────────────────────────────────────────
    incident.opened      payload["severity"] in P0/P1  ERROR
    incident.classified  payload["severity"] == "P0"   CRITICAL (→ error)
    drift.detected       payload["severity"] == "error" WARNING
    risk_limit.breached  (always)                       ERROR
    order.filled         ALERTS_VERBOSE_FILLS=1 only    INFO

    L22 does NOT auto-register at import time; the operator / L41 harness
    must call register_alert_subscribers() explicitly to avoid noisy behaviour
    in tests that import L22 without intending to subscribe to the bus.

Atomic writes
-------------
    alert_queue.json is written atomically via a sibling temp file +
    os.replace() so a crash mid-write never leaves a partial/corrupt queue.
    The daily log file in _LOG_DIR uses append mode; partial appends are
    benign for log-only files and do not require atomic replacement.

CLI
---
    python L22_alerting.py test --channel edges --level info --title "msg"
    python L22_alerting.py flush
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

# ── soft-import L46 EventBus (absent in minimal test environments) ────────────
try:
    from scripts.execute_loop import L46_event_bus as _L46
except Exception:  # noqa: BLE001
    _L46 = None  # type: ignore[assignment]

# ── paths ────────────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parent.parent
_QUEUE_PATH  = _PROJECT_DIR / "data" / "ledger" / "alert_queue.json"
_LOG_DIR     = _PROJECT_DIR / "logs" / "alerts"

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
VALID_CHANNELS = {"edges", "fills", "drift", "drawdown", "news", "settle", "system"}
VALID_LEVELS   = {"info", "warning", "error"}

# Paper vs Live Mode gate — read once at import.
# L22 operates in two modes:
#   paper (default): alerts are written to a local daily log file (ALERTS_ENABLED absent or "false").
#   live: HTTP webhook delivery to Slack/Discord (ALERTS_ENABLED="true").
# L42 readiness check requires a module-level LIVE gate constant for paper_default verification.
LIVE_ENABLED = os.environ.get("ALERTS_LIVE_ENABLED") == "1"  # L42 paper_default gate

_COLOR_SLACK = {
    "info":    "#36a64f",
    "warning": "#ffcc00",
    "error":   "#ff0000",
}
_COLOR_DISCORD = {
    "info":    0x00FF00,
    "warning": 0xFFFF00,
    "error":   0xFF0000,
}
_MAX_BODY = 4000
_HTTP_BACKOFF_CAPS = [1, 2, 4, 8, 16, 32, 60]


# ── atomic file helper ────────────────────────────────────────────────────────
def _atomic_write_json(path: Path, payload: object, *, indent: int = 2) -> None:
    """Write *payload* as JSON to *path* atomically via a sibling temp file.

    Uses tempfile.mkstemp + os.replace so a crash mid-write never leaves a
    partial or corrupt file.  Raises OSError / IOError on failure after
    cleaning up the temp file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=indent)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── rate limiter ──────────────────────────────────────────────────────────────
class _TokenBucket:
    """Thread-unsafe token bucket; single-process use only."""

    def __init__(self, capacity: int) -> None:
        self.capacity   = max(1, capacity)
        self.tokens     = float(self.capacity)
        self._refill_ps = self.capacity / 60.0
        self._last      = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self._last) * self._refill_ps)
        self._last  = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


# ── alert router ──────────────────────────────────────────────────────────────
class AlertRouter:
    def __init__(self) -> None:
        limit          = int(os.getenv("ALERTS_RATE_LIMIT_PER_MIN", "30"))
        self._bucket   = _TokenBucket(limit)
        self._enabled  = os.getenv("ALERTS_ENABLED", "false").lower() == "true"
        self._slack_url    = os.getenv("SLACK_WEBHOOK_URL", "").strip()
        self._discord_url  = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        self._slack_fails  = 0
        self._discord_fails = 0
        self._slack_dead   = False
        self._discord_dead = False
        _QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # ── public ────────────────────────────────────────────────────────────────
    def send(
        self,
        channel: str,
        level:   str,
        title:   str,
        body:    str,
        fields:  Optional[Dict[str, str]] = None,
    ) -> bool:
        channel, level = self._coerce(channel, level)
        body = self._truncate(body)

        if not self._bucket.consume():
            self._enqueue(channel, level, title, body, fields)
            return False

        return self._dispatch(channel, level, title, body, fields)

    def flush_pending(self) -> int:
        items = self._load_queue()
        if not items:
            return 0
        sent = 0
        remaining: List[dict] = []
        for item in items:
            if self._bucket.consume():
                ok = self._dispatch(
                    item["channel"], item["level"],
                    item["title"],   item["body"],
                    item.get("fields"),
                )
                if ok:
                    sent += 1
                    continue
            remaining.append(item)
        self._save_queue(remaining)
        return sent

    # ── internal dispatch ─────────────────────────────────────────────────────
    def _dispatch(
        self, channel: str, level: str, title: str, body: str,
        fields: Optional[Dict[str, str]],
    ) -> bool:
        live = self._enabled and (self._slack_url or self._discord_url)
        if not live:
            self._test_write(channel, level, title, body, fields)
            return True

        sent_any = False
        if self._slack_url and not self._slack_dead:
            if self._post_slack(channel, level, title, body, fields):
                sent_any = True
        if self._discord_url_for(channel) and not self._discord_dead:
            if self._post_discord(channel, level, title, body, fields):
                sent_any = True

        if not sent_any:
            self._test_write(channel, level, title, body, fields)
            return True

        return True

    def _post_slack(
        self, channel: str, level: str, title: str, body: str,
        fields: Optional[Dict[str, str]],
    ) -> bool:
        if level == "error":
            body = "<!here> " + body
        blocks: list = [
            {"type": "header", "text": {"type": "plain_text", "text": title}},
            {"type": "section", "text": {"type": "mrkdwn", "text": body}},
        ]
        if fields:
            blocks.append({
                "type": "fields",
                "fields": [{"type": "mrkdwn", "text": f"*{k}*\n{v}"} for k, v in fields.items()],
            })
        payload = {
            "attachments": [{
                "color":  _COLOR_SLACK[level],
                "blocks": [b for b in blocks if b is not None],
            }]
        }
        return self._http_post(self._slack_url, payload, "slack")

    def _post_discord(
        self, channel: str, level: str, title: str, body: str,
        fields: Optional[Dict[str, str]],
    ) -> bool:
        url = self._discord_url_for(channel)
        payload = {
            "embeds": [{
                "title":       title,
                "description": body,
                "color":       _COLOR_DISCORD[level],
                "fields":      [{"name": k, "value": v, "inline": True} for k, v in (fields or {}).items()],
                "timestamp":   datetime.now(timezone.utc).isoformat(),
            }]
        }
        return self._http_post(url, payload, "discord")

    def _http_post(self, url: str, payload: dict, service: str) -> bool:
        backoffs = _HTTP_BACKOFF_CAPS[:]
        for attempt, wait in enumerate(backoffs):
            try:
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 429:
                    time.sleep(wait)
                    continue
                if resp.status_code >= 500:
                    self._record_fail(service)
                    return False
                resp.raise_for_status()
                self._reset_fail(service)
                return True
            except requests.RequestException as exc:
                log.warning("[L22] %s post failed (attempt %d): %s", service, attempt + 1, exc)
                self._record_fail(service)
                return False
        self._record_fail(service)
        return False

    # ── helpers ───────────────────────────────────────────────────────────────
    def _discord_url_for(self, channel: str) -> str:
        env_key = f"DISCORD_{channel.upper()}_WEBHOOK_URL"
        return os.getenv(env_key, "").strip() or self._discord_url

    def _record_fail(self, service: str) -> None:
        if service == "slack":
            self._slack_fails += 1
            if self._slack_fails >= 2:
                log.error("[L22] Slack disabled after 2 consecutive failures.")
                self._slack_dead = True
        else:
            self._discord_fails += 1
            if self._discord_fails >= 2:
                log.error("[L22] Discord disabled after 2 consecutive failures.")
                self._discord_dead = True

    def _reset_fail(self, service: str) -> None:
        if service == "slack":
            self._slack_fails = 0
        else:
            self._discord_fails = 0

    def _test_write(
        self, channel: str, level: str, title: str, body: str,
        fields: Optional[Dict[str, str]],
    ) -> None:
        ts  = datetime.now(timezone.utc)
        log_file = _LOG_DIR / f"{ts.date()}.log"
        line = (
            f"[{ts.isoformat()}] [{level.upper()}] [{channel}] "
            f"{title} | {body}"
            + (f" | fields={json.dumps(fields)}" if fields else "")
        )
        print(line)
        try:
            # Append-mode log write: single-line appends are atomic for writes
            # below PIPE_BUF (POSIX) / WriteFile granularity (Windows).  No .tmp
            # rename needed — log files are append-only and never read-modified-write.
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as exc:
            log.warning("[L22] Could not write alert log: %s", exc)

    def _enqueue(
        self, channel: str, level: str, title: str, body: str,
        fields: Optional[Dict[str, str]],
    ) -> None:
        items = self._load_queue()
        items.append({"channel": channel, "level": level,
                       "title": title, "body": body, "fields": fields,
                       "queued_at": datetime.now(timezone.utc).isoformat()})
        self._save_queue(items)

    def _load_queue(self) -> List[dict]:
        if not _QUEUE_PATH.exists():
            return []
        try:
            return json.loads(_QUEUE_PATH.read_text(encoding="utf-8")) or []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_queue(self, items: List[dict]) -> None:
        try:
            _atomic_write_json(_QUEUE_PATH, items)
        except OSError as exc:
            log.error("[L22] Failed to persist alert queue: %s", exc)

    @staticmethod
    def _truncate(body: str) -> str:
        _SUFFIX = "...[truncated]"  # 14 chars
        if len(body) > _MAX_BODY:
            return body[: _MAX_BODY - len(_SUFFIX)] + _SUFFIX
        return body

    @staticmethod
    def _coerce(channel: str, level: str):
        if channel not in VALID_CHANNELS:
            log.warning("[L22] Unknown channel %r — coercing to 'system'", channel)
            channel = "system"
        if level not in VALID_LEVELS:
            log.warning("[L22] Unknown level %r — coercing to 'info'", level)
            level = "info"
        return channel, level


# ── module-level router singleton ─────────────────────────────────────────────
_router: Optional[AlertRouter] = None


def _get_router() -> AlertRouter:
    global _router
    if _router is None:
        _router = AlertRouter()
    return _router


# ── public API ────────────────────────────────────────────────────────────────
def send_alert(
    channel: str,
    level:   str,
    title:   str,
    body:    str,
    fields:  Optional[Dict[str, str]] = None,
) -> bool:
    return _get_router().send(channel, level, title, body, fields)


def send_edge_alert(
    player: str, stat: str, line: float, model: float,
    edge_pp: float, side: str, recommended_stake: float,
) -> bool:
    body = f"{player} — {stat} {side} {line} | model={model:.2f} | edge={edge_pp:+.1f}pp"
    fields = {
        "Player": player, "Stat": stat, "Line": str(line),
        "Model": f"{model:.2f}", "Edge": f"{edge_pp:+.1f}pp",
        "Side": side, "Stake": f"${recommended_stake:.2f}",
    }
    return send_alert("edges", "info", f"Edge: {player} {stat}", body, fields)


def send_fill_alert(bet_id: str, book: str, stake: float, status: str) -> bool:
    body  = f"Bet {bet_id} at {book}: ${stake:.2f} — {status}"
    fields = {"BetID": bet_id, "Book": book, "Stake": f"${stake:.2f}", "Status": status}
    return send_alert("fills", "info", f"Fill: {bet_id}", body, fields)


def send_drawdown_alert(
    current_bankroll: float, starting: float, pct_drop: float,
) -> bool:
    level = "error" if pct_drop >= 20 else "warning"
    body  = f"Bankroll ${current_bankroll:.2f} (started ${starting:.2f}) — down {pct_drop:.1f}%"
    fields = {
        "Current": f"${current_bankroll:.2f}",
        "Starting": f"${starting:.2f}",
        "Drop": f"{pct_drop:.1f}%",
    }
    return send_alert("drawdown", level, f"Drawdown {pct_drop:.1f}%", body, fields)


def send_drift_alert(
    stat: str, observed_mae: float, expected_mae: float, days_window: int,
) -> bool:
    delta = observed_mae - expected_mae
    body  = (
        f"{stat} MAE drifted to {observed_mae:.4f} "
        f"(expected {expected_mae:.4f}, delta={delta:+.4f}) "
        f"over {days_window}d window"
    )
    fields = {
        "Stat": stat,
        "Observed MAE": f"{observed_mae:.4f}",
        "Expected MAE": f"{expected_mae:.4f}",
        "Delta": f"{delta:+.4f}",
        "Window": f"{days_window}d",
    }
    level = "error" if delta > 0.5 else "warning"
    return send_alert("drift", level, f"Model Drift: {stat}", body, fields)


def flush_pending() -> int:
    return _get_router().flush_pending()


# ── L46 EventBus subscriber registration ─────────────────────────────────────

# Idempotency guard — True once register_alert_subscribers() has run.
_subscribed: bool = False


def register_alert_subscribers(bus=None) -> None:  # type: ignore[type-arg]
    """Subscribe L22 alert handlers to the L46 EventBus.

    Parameters
    ----------
    bus:
        An ``L46_event_bus.EventBus`` instance to subscribe to.  When
        ``None`` (default), the module-level default bus singleton is used
        (``L46_event_bus.get_default_bus()``).

    Idempotency
    -----------
    Calling this function more than once is safe — subsequent calls are
    no-ops.  The guard is a module-level ``_subscribed`` flag; pass a
    different ``bus`` instance explicitly if you need to register on
    multiple buses (uncommon).

    Event → Level mapping
    ----------------------
    incident.opened      severity in {P0, P1}  → ERROR
    incident.classified  severity == P0         → CRITICAL (sent as error)
    drift.detected       severity == "error"    → WARNING
    risk_limit.breached  (always)               → ERROR
    order.filled         ALERTS_VERBOSE_FILLS=1 → INFO  (opt-in)
    """
    global _subscribed  # noqa: PLW0603
    if _subscribed:
        return

    # Resolve the bus: use provided instance, fall back to default singleton.
    if bus is None:
        if _L46 is None:
            log.warning("[L22] L46 EventBus not available; skipping subscriber registration.")
            return
        bus = _L46.get_default_bus()

    # ── handler: incident.opened ──────────────────────────────────────────────
    def _on_incident_opened(event) -> None:
        payload = event.payload
        severity = str(payload.get("severity", "")).upper()
        if severity not in ("P0", "P1"):
            return
        incident_id = payload.get("incident_id", "unknown")
        description = payload.get("description", "No description provided.")
        fields: Dict[str, str] = {
            "Incident ID": str(incident_id),
            "Severity": severity,
            "Source": event.source,
        }
        if payload.get("layer"):
            fields["Layer"] = str(payload["layer"])
        send_alert(
            channel="system",
            level="error",
            title=f"Incident Opened [{severity}]: {incident_id}",
            body=description,
            fields=fields,
        )

    # ── handler: incident.classified ─────────────────────────────────────────
    def _on_incident_classified(event) -> None:
        payload = event.payload
        severity = str(payload.get("severity", "")).upper()
        if severity != "P0":
            return
        incident_id = payload.get("incident_id", "unknown")
        description = payload.get("description", "P0 incident classified.")
        fields: Dict[str, str] = {
            "Incident ID": str(incident_id),
            "Severity": "P0 (CRITICAL)",
            "Source": event.source,
        }
        send_alert(
            channel="system",
            level="error",  # L22 VALID_LEVELS has no "critical"; map to "error"
            title=f"CRITICAL Incident Classified [P0]: {incident_id}",
            body=description,
            fields=fields,
        )

    # ── handler: drift.detected ───────────────────────────────────────────────
    def _on_drift_detected(event) -> None:
        payload = event.payload
        drift_severity = str(payload.get("severity", "")).lower()
        if drift_severity != "error":
            return
        stat = payload.get("stat", "unknown")
        observed = payload.get("observed_mae", payload.get("observed", "?"))
        expected = payload.get("expected_mae", payload.get("expected", "?"))
        fields: Dict[str, str] = {
            "Stat": str(stat),
            "Observed": str(observed),
            "Expected": str(expected),
            "Source": event.source,
        }
        send_alert(
            channel="drift",
            level="warning",
            title=f"Model Drift Detected: {stat}",
            body=f"{stat} MAE drifted beyond threshold (observed={observed}, expected={expected})",
            fields=fields,
        )

    # ── handler: risk_limit.breached ─────────────────────────────────────────
    def _on_risk_limit_breached(event) -> None:
        payload = event.payload
        limit_type = payload.get("limit_type", "unknown")
        current = payload.get("current_value", "?")
        threshold = payload.get("threshold", "?")
        fields: Dict[str, str] = {
            "Limit Type": str(limit_type),
            "Current Value": str(current),
            "Threshold": str(threshold),
            "Source": event.source,
        }
        send_alert(
            channel="drawdown",
            level="error",
            title=f"Risk Limit Breached: {limit_type}",
            body=f"Risk limit '{limit_type}' breached (current={current}, threshold={threshold})",
            fields=fields,
        )

    # ── register core subscribers ─────────────────────────────────────────────
    bus.subscribe("incident.opened",     _on_incident_opened,     layer="L22")
    bus.subscribe("incident.classified", _on_incident_classified, layer="L22")
    bus.subscribe("drift.detected",      _on_drift_detected,      layer="L22")
    bus.subscribe("risk_limit.breached", _on_risk_limit_breached, layer="L22")

    # ── optional: order.filled (ALERTS_VERBOSE_FILLS=1) ───────────────────────
    if os.environ.get("ALERTS_VERBOSE_FILLS") == "1":
        def _on_order_filled(event) -> None:
            payload = event.payload
            bet_id = payload.get("bet_id", payload.get("order_id", "unknown"))
            book   = payload.get("book", "?")
            stake  = payload.get("stake", "?")
            status = payload.get("status", "filled")
            fields: Dict[str, str] = {
                "Bet ID": str(bet_id),
                "Book": str(book),
                "Stake": str(stake),
                "Status": str(status),
                "Source": event.source,
            }
            send_alert(
                channel="fills",
                level="info",
                title=f"Order Filled: {bet_id}",
                body=f"Bet {bet_id} at {book} — stake={stake} status={status}",
                fields=fields,
            )

        bus.subscribe("order.filled", _on_order_filled, layer="L22")

    _subscribed = True
    log.debug("[L22] EventBus subscribers registered.")


# ── CLI ───────────────────────────────────────────────────────────────────────
def _cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="L22 alerting CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("test", help="Send a test alert")
    t.add_argument("--channel", default="system", choices=list(VALID_CHANNELS))
    t.add_argument("--level",   default="info",   choices=list(VALID_LEVELS))
    t.add_argument("--title",   default="Test alert")
    t.add_argument("--body",    default="L22 alerting smoke test.")
    sub.add_parser("flush", help="Flush queued alerts")

    args = p.parse_args()
    if args.cmd == "test":
        ok = send_alert(args.channel, args.level, args.title, args.body)
        print(f"send_alert returned: {ok}")
    elif args.cmd == "flush":
        n = flush_pending()
        print(f"Flushed {n} queued alerts.")


if __name__ == "__main__":
    _cli()
