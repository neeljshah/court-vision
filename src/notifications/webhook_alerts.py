"""webhook_alerts.py — Slack/Discord webhook transport for live alerts.

Tier-2 follow-up to cycle 88k's `scripts/live_alerts.py`. That cycle prints
alerts to the terminal only — invisible to an operator who isn't watching
the console. This module wires those same alert dicts to a Slack or
Discord webhook so they reach a phone / channel.

Usage
-----
    from src.notifications.webhook_alerts import WebhookNotifier
    n = WebhookNotifier()              # picks up SLACK_ALERT_WEBHOOK /
                                       # DISCORD_ALERT_WEBHOOK env vars
    n.send("EDGE_FLIP", "Jokic OVER 28.5 flipped -EV",
           severity="high", tags={"player": "Jokic"})

Environment variables (preferred — never hardcode webhook URLs):

    SLACK_ALERT_WEBHOOK    https://hooks.slack.com/services/...
    DISCORD_ALERT_WEBHOOK  https://discord.com/api/webhooks/.../...

Either, both, or neither can be set. With neither set, ``send`` is a
no-op that returns ``False`` (graceful degradation — never raises so
callers can fire-and-forget from inside the alert loop).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

_SEVERITY_RANK = {"info": 0, "medium": 1, "high": 2}
_DEFAULT_TIMEOUT = 6


class WebhookNotifier:
    """Post alert payloads to Slack and/or Discord incoming webhooks.

    Both transports are best-effort: a failure on one webhook never
    blocks the other, and a total failure returns ``False`` rather than
    raising — the alert loop must keep running.
    """

    def __init__(self, slack_url: Optional[str] = None,
                 discord_url: Optional[str] = None,
                 min_severity: str = "high",
                 timeout: int = _DEFAULT_TIMEOUT) -> None:
        self.slack_url = slack_url or os.environ.get("SLACK_ALERT_WEBHOOK") or None
        self.discord_url = discord_url or os.environ.get("DISCORD_ALERT_WEBHOOK") or None
        if min_severity not in _SEVERITY_RANK:
            raise ValueError(
                f"min_severity must be one of {list(_SEVERITY_RANK)}; "
                f"got {min_severity!r}")
        self.min_severity = min_severity
        self.timeout = timeout

    # ── public ──────────────────────────────────────────────────────────

    def enabled(self) -> bool:
        """True if at least one webhook URL is configured."""
        return bool(self.slack_url or self.discord_url)

    def send(self, title: str, body: str, severity: str = "high",
             tags: Optional[dict] = None) -> bool:
        """Post the alert to all configured webhooks.

        Parameters
        ----------
        title : str
            Short headline (alert TYPE in live_alerts terminology).
        body : str
            Human-readable alert message.
        severity : str
            One of ``info``, ``medium``, ``high``. Anything below
            :attr:`min_severity` is dropped silently.
        tags : dict, optional
            Free-form context (player, stat, line, game_id, ...). Embedded
            in the payload so dashboards can filter on it.

        Returns
        -------
        bool
            ``True`` if AT LEAST ONE webhook accepted the POST. ``False``
            if both failed, no webhook was configured, or the alert was
            filtered out by ``min_severity``.
        """
        severity = (severity or "high").lower()
        if severity not in _SEVERITY_RANK:
            log.warning("unknown severity %r; treating as 'high'", severity)
            severity = "high"
        if _SEVERITY_RANK[severity] < _SEVERITY_RANK[self.min_severity]:
            return False
        if not self.enabled():
            # Graceful no-op: caller fires from inside the alert loop and
            # should not need to gate on configuration.
            log.debug("webhook notifier disabled (no URLs); dropping %s",
                      title)
            return False

        payload = self._build_payload(title, body, severity, tags or {})
        ok = False
        if self.slack_url:
            ok = self._post(self.slack_url,
                            self._render_slack(payload), "slack") or ok
        if self.discord_url:
            ok = self._post(self.discord_url,
                            self._render_discord(payload), "discord") or ok
        return ok

    # ── internals ───────────────────────────────────────────────────────

    @staticmethod
    def _build_payload(title: str, body: str, severity: str,
                       tags: dict) -> dict:
        return {
            "title":     title,
            "body":      body,
            "severity":  severity,
            "tags":      dict(tags),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    @staticmethod
    def _render_slack(payload: dict) -> dict:
        """Slack incoming-webhook JSON shape with attachment + colour."""
        colour = {
            "info":   "#36a64f",   # green
            "medium": "#daa520",   # gold
            "high":   "#d10000",   # red
        }.get(payload["severity"], "#888888")
        tag_lines = "\n".join(
            f"*{k}*: {v}" for k, v in payload["tags"].items()
        ) or "—"
        return {
            "text": f"[{payload['severity'].upper()}] {payload['title']}",
            "attachments": [{
                "color": colour,
                "title": payload["title"],
                "text":  payload["body"],
                "fields": [
                    {"title": "Severity", "value": payload["severity"],
                     "short": True},
                    {"title": "Time", "value": payload["timestamp"],
                     "short": True},
                    {"title": "Tags", "value": tag_lines, "short": False},
                ],
                "ts": payload["timestamp"],
                # Keep the full structured payload alongside the rendered
                # version so downstream consumers / log scrapers can
                # round-trip without re-parsing the text.
                "footer": "courtvision live alerts",
                "mrkdwn_in": ["text", "fields"],
                "payload": payload,
            }],
        }

    @staticmethod
    def _render_discord(payload: dict) -> dict:
        """Discord webhook JSON shape with embed + colour."""
        colour_int = {
            "info":   0x36A64F,
            "medium": 0xDAA520,
            "high":   0xD10000,
        }.get(payload["severity"], 0x888888)
        fields = [
            {"name": k, "value": str(v), "inline": True}
            for k, v in payload["tags"].items()
        ]
        return {
            "content": f"**[{payload['severity'].upper()}] {payload['title']}**",
            "embeds": [{
                "title":       payload["title"],
                "description": payload["body"],
                "color":       colour_int,
                "timestamp":   payload["timestamp"],
                "fields":      fields,
                "footer":      {"text": "courtvision live alerts"},
            }],
            # Mirror the structured payload outside the embed so consumers
            # can read it without HTML-stripping.
            "payload":   payload,
        }

    def _post(self, url: str, body: dict, label: str) -> bool:
        """POST ``body`` to ``url`` as JSON. Returns True on 2xx."""
        try:
            data = json.dumps(body).encode("utf-8")
        except (TypeError, ValueError) as exc:
            log.warning("%s webhook payload not JSON-serialisable: %s",
                        label, exc)
            return False
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = getattr(resp, "status", 0)
                if 200 <= status < 300:
                    return True
                log.warning("%s webhook returned HTTP %s", label, status)
                return False
        except urllib.error.URLError as exc:
            log.warning("%s webhook network error: %s", label, exc)
            return False
        except Exception as exc:  # noqa: BLE001
            log.warning("%s webhook unexpected error: %s", label, exc)
            return False


# ── alert-dict bridge ───────────────────────────────────────────────────

def notify_from_alert(notifier: WebhookNotifier, alert: dict,
                      *, severity: str = "high") -> bool:
    """Translate a cycle-88k alert dict into a webhook send.

    Lets the alert loop call one helper instead of unpacking every alert
    dict at the call site. Reuses the EXISTING alert schema (``type``,
    ``message``, plus any player/stat/line/game_id fields) without
    modifying it.
    """
    if not alert:
        return False
    title = str(alert.get("type") or "ALERT")
    body = str(alert.get("message") or "")
    tag_keys = ("player", "stat", "line", "side", "pregame", "projected",
                "delta", "game_id", "period", "margin", "matchup", "pf")
    tags = {k: alert[k] for k in tag_keys if k in alert and alert[k] is not None}
    return notifier.send(title, body, severity=severity, tags=tags)
