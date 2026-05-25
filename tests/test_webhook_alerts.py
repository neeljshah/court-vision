"""tests/test_webhook_alerts.py — tier-2 webhook transport (loop 5).

Six offline tests for src/notifications/webhook_alerts.WebhookNotifier.
We never hit a real Slack/Discord URL: every test monkeypatches
``urllib.request.urlopen`` so the payload is captured locally and the
network is never touched.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import List
from unittest.mock import MagicMock

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.notifications import webhook_alerts as wa  # noqa: E402
from src.notifications.webhook_alerts import (  # noqa: E402
    WebhookNotifier, notify_from_alert,
)


SLACK_URL = "https://hooks.slack.com/services/T000/B000/XXX"
DISCORD_URL = "https://discord.com/api/webhooks/000/yyy"


class _FakeResponse:
    """Minimal urlopen-context-manager stand-in."""

    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _capture_urlopen(captured: List[dict], *, statuses=None):
    """Return a fake ``urlopen`` that appends every request to `captured`.

    ``statuses`` is a dict {url-substring: http_status_or_Exception}. The
    matching substring controls what the fake returns / raises. Default
    is 200 for everything.
    """
    statuses = statuses or {}

    def _fake(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        body = req.data.decode("utf-8") if req.data else "{}"
        captured.append({
            "url":     url,
            "body":    json.loads(body),
            "timeout": timeout,
            "method":  req.get_method(),
            "headers": dict(req.header_items()),
        })
        # Pick the first matching status rule, else default 200.
        for key, val in statuses.items():
            if key in url:
                if isinstance(val, Exception):
                    raise val
                return _FakeResponse(status=val)
        return _FakeResponse(status=200)

    return _fake


# ── 1. Both webhooks receive the payload ────────────────────────────────────

def test_send_posts_to_both_slack_and_discord(monkeypatch):
    captured: List[dict] = []
    monkeypatch.setattr(urllib.request, "urlopen",
                         _capture_urlopen(captured))
    notifier = WebhookNotifier(slack_url=SLACK_URL, discord_url=DISCORD_URL,
                                 min_severity="high")
    ok = notifier.send("EDGE_FLIP", "Jokic OVER 28.5 flipped -EV",
                        severity="high",
                        tags={"player": "Jokic", "stat": "PTS"})
    assert ok is True
    urls = {c["url"] for c in captured}
    assert urls == {SLACK_URL, DISCORD_URL}
    # Both payloads must carry the round-trip-able structured payload.
    for c in captured:
        body = c["body"]
        if "embeds" in body:    # Discord
            assert body["payload"]["title"] == "EDGE_FLIP"
            assert body["payload"]["tags"]["player"] == "Jokic"
        else:                   # Slack
            payload = body["attachments"][0]["payload"]
            assert payload["title"] == "EDGE_FLIP"
            assert payload["tags"]["stat"] == "PTS"
    # And the request must have been a POST with JSON content-type.
    for c in captured:
        assert c["method"] == "POST"
        # urllib normalises header names; compare case-insensitively.
        ctypes = {k.lower(): v for k, v in c["headers"].items()}
        assert ctypes.get("Content-type".lower()) == "application/json"


# ── 2. min_severity filters out lower-tier alerts ──────────────────────────

def test_min_severity_high_filters_medium_and_info(monkeypatch):
    captured: List[dict] = []
    monkeypatch.setattr(urllib.request, "urlopen",
                         _capture_urlopen(captured))
    notifier = WebhookNotifier(slack_url=SLACK_URL, discord_url=DISCORD_URL,
                                 min_severity="high")
    assert notifier.send("X", "info body", severity="info") is False
    assert notifier.send("X", "medium body", severity="medium") is False
    assert notifier.send("X", "high body", severity="high") is True
    # Only the third call should have produced any network traffic.
    bodies = [c["body"] for c in captured]
    # Each high-send hits both webhooks → 2 captured requests total.
    assert len(bodies) == 2
    titles = []
    for body in bodies:
        if "embeds" in body:
            titles.append(body["embeds"][0]["description"])
        else:
            titles.append(body["attachments"][0]["text"])
    assert all("high body" in t for t in titles)


# ── 3. Slack fails → Discord still tries ──────────────────────────────────

def test_slack_network_failure_does_not_block_discord(monkeypatch):
    captured: List[dict] = []
    statuses = {
        "hooks.slack.com":   urllib.error.URLError("simulated slack outage"),
        "discord.com":       200,
    }
    monkeypatch.setattr(urllib.request, "urlopen",
                         _capture_urlopen(captured, statuses=statuses))
    notifier = WebhookNotifier(slack_url=SLACK_URL, discord_url=DISCORD_URL)
    ok = notifier.send("FOUL_TROUBLE", "Curry 4 PF Q3", severity="high")
    # At least one (discord) succeeded → True overall.
    assert ok is True
    urls = [c["url"] for c in captured]
    assert SLACK_URL in urls
    assert DISCORD_URL in urls


# ── 4. Both fail → returns False, does NOT raise ──────────────────────────

def test_both_webhooks_failing_returns_false_without_raising(monkeypatch):
    captured: List[dict] = []
    statuses = {
        "hooks.slack.com": urllib.error.URLError("slack down"),
        "discord.com":     urllib.error.URLError("discord down"),
    }
    monkeypatch.setattr(urllib.request, "urlopen",
                         _capture_urlopen(captured, statuses=statuses))
    notifier = WebhookNotifier(slack_url=SLACK_URL, discord_url=DISCORD_URL)
    ok = notifier.send("EDGE_FLIP", "everything down", severity="high")
    assert ok is False
    # We still tried both before giving up.
    urls = {c["url"] for c in captured}
    assert urls == {SLACK_URL, DISCORD_URL}


# ── 5. No env vars + no kwargs → no-op (graceful) ─────────────────────────

def test_no_config_is_graceful_noop(monkeypatch):
    # Strip any inherited env vars so the notifier truly sees nothing.
    monkeypatch.delenv("SLACK_ALERT_WEBHOOK", raising=False)
    monkeypatch.delenv("DISCORD_ALERT_WEBHOOK", raising=False)
    # If anything DOES try to POST, we want a loud failure.
    called = {"n": 0}

    def _explode(req, timeout=None):
        called["n"] += 1
        raise AssertionError("notifier should not POST when disabled")

    monkeypatch.setattr(urllib.request, "urlopen", _explode)
    notifier = WebhookNotifier()
    assert notifier.enabled() is False
    assert notifier.send("EDGE_FLIP", "no webhooks configured",
                         severity="high") is False
    assert called["n"] == 0


# ── 6. Payload includes title, body, severity, tags, timestamp ─────────────

def test_payload_includes_title_body_severity_tags_timestamp(monkeypatch):
    captured: List[dict] = []
    monkeypatch.setattr(urllib.request, "urlopen",
                         _capture_urlopen(captured))
    notifier = WebhookNotifier(slack_url=SLACK_URL, discord_url=DISCORD_URL)
    tags = {"player": "Doncic", "stat": "PTS", "line": 32.5}
    notifier.send("PROJECTION_SHIFT", "Doncic projected 36",
                   severity="high", tags=tags)
    # Reach into the structured payload from BOTH renderers.
    for c in captured:
        body = c["body"]
        if "embeds" in body:
            payload = body["payload"]
        else:
            payload = body["attachments"][0]["payload"]
        assert payload["title"] == "PROJECTION_SHIFT"
        assert payload["body"] == "Doncic projected 36"
        assert payload["severity"] == "high"
        assert payload["tags"] == tags
        # ISO-8601 timestamp present.
        assert isinstance(payload["timestamp"], str)
        # crude shape check: YYYY-MM-DDTHH:MM:SS
        assert "T" in payload["timestamp"] and len(payload["timestamp"]) >= 19


# ── 7 (bonus). notify_from_alert bridges cycle-88k alert dicts ────────────

def test_notify_from_alert_translates_88k_dict(monkeypatch):
    captured: List[dict] = []
    monkeypatch.setattr(urllib.request, "urlopen",
                         _capture_urlopen(captured))
    notifier = WebhookNotifier(slack_url=SLACK_URL)
    alert = {
        "type": "EDGE_FLIP",
        "message": "Jokic OVER 28.5 flipped against bet",
        "player": "Jokic",
        "stat": "PTS",
        "line": 28.5,
        "side": "OVER",
        "pregame": 31.0,
        "projected": 26.0,
        "key": "EDGE_FLIP|jokic|pts|OVER|28.5",
    }
    ok = notify_from_alert(notifier, alert, severity="high")
    assert ok is True
    assert len(captured) == 1
    payload = captured[0]["body"]["attachments"][0]["payload"]
    assert payload["title"] == "EDGE_FLIP"
    assert payload["tags"]["player"] == "Jokic"
    assert payload["tags"]["pregame"] == 31.0
    # The key field should NOT leak into tags (it's internal state).
    assert "key" not in payload["tags"]
