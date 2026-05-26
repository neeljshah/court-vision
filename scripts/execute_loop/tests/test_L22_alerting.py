"""test_L22_alerting.py — Unit tests for L22_alerting (BUILD L22).

All tests use monkeypatch to set env vars and intercept requests.post.
No real HTTP calls are made.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── make module importable without nba_api side-effect ───────────────────────
# L22_alerting does NOT import nba_api_headers_patch so no special handling needed.
_EXECUTE_LOOP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_EXECUTE_LOOP.parent.parent))  # project root


def _fresh_module(env_overrides: dict | None = None):
    """Re-import L22_alerting with a clean singleton, optionally patching env."""
    # Remove cached module so the singleton _router is rebuilt
    for key in list(sys.modules.keys()):
        if "L22_alerting" in key:
            del sys.modules[key]

    patches: list = []
    if env_overrides is not None:
        for k, v in env_overrides.items():
            patches.append(patch.dict("os.environ", {k: v}))
        for p in patches:
            p.start()

    mod = importlib.import_module("scripts.execute_loop.L22_alerting")
    # Reset singleton so each test starts fresh
    mod._router = None

    for p in patches:
        p.stop()

    return mod


# ── fixtures ──────────────────────────────────────────────────────────────────
def _clear_l22_pkg_attr() -> None:
    """Remove the L22_alerting attribute from the scripts.execute_loop package.

    This is necessary because ``import scripts.execute_loop.L22_alerting as X``
    binds X to the *package attribute*, not sys.modules, so deleting from
    sys.modules alone leaves a stale cached reference on the parent package.
    Subsequent tests that mock sys.modules["scripts.execute_loop.L22_alerting"]
    would still get the real module through the package attribute.
    """
    pkg = sys.modules.get("scripts.execute_loop")
    if pkg is not None:
        pkg.__dict__.pop("L22_alerting", None)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure module singleton and package attribute are reset between tests."""
    for key in list(sys.modules.keys()):
        if "L22_alerting" in key:
            del sys.modules[key]
    _clear_l22_pkg_attr()
    yield
    for key in list(sys.modules.keys()):
        if "L22_alerting" in key:
            del sys.modules[key]
    _clear_l22_pkg_attr()


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    """Default import with ALERTS_ENABLED=false, no webhook URLs."""
    monkeypatch.delenv("SLACK_WEBHOOK_URL",   raising=False)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("ALERTS_ENABLED", "false")
    monkeypatch.setenv("ALERTS_RATE_LIMIT_PER_MIN", "30")

    import scripts.execute_loop.L22_alerting as m

    # Redirect file paths to tmp_path to avoid polluting real dirs
    monkeypatch.setattr(m, "_QUEUE_PATH", tmp_path / "alert_queue.json")
    monkeypatch.setattr(m, "_LOG_DIR", tmp_path / "logs" / "alerts")
    (tmp_path / "logs" / "alerts").mkdir(parents=True, exist_ok=True)
    m._router = None  # force fresh singleton
    return m


# ── test 1: ALERTS_ENABLED=false → test-mode write, returns True, no HTTP ─────
def test_disabled_no_http_returns_true(mod, monkeypatch):
    post_mock = MagicMock()
    monkeypatch.setattr("requests.post", post_mock)

    result = mod.send_alert("system", "info", "T1", "body1")

    assert result is True
    post_mock.assert_not_called()


# ── test 2: No webhook URL → test mode forced, returns True ───────────────────
def test_no_webhook_forces_test_mode(mod, monkeypatch):
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    # no SLACK_WEBHOOK_URL or DISCORD_WEBHOOK_URL set (cleared in fixture)
    mod._router = None

    post_mock = MagicMock()
    monkeypatch.setattr("requests.post", post_mock)

    result = mod.send_alert("system", "info", "T2", "no webhooks")

    assert result is True
    post_mock.assert_not_called()


# ── test 3: 31 alerts with limit=30 → 31st queues, returns False ─────────────
def test_rate_limit_queues_on_overflow(mod, monkeypatch, tmp_path):
    monkeypatch.setenv("ALERTS_RATE_LIMIT_PER_MIN", "30")
    mod._router = None
    router = mod._get_router()
    # Drain all tokens
    router._bucket.tokens = 0.0
    router._bucket._last  = time.monotonic()

    post_mock = MagicMock()
    monkeypatch.setattr("requests.post", post_mock)

    result = mod.send_alert("system", "info", "overflow", "body")

    assert result is False
    # Item should be in queue
    q = json.loads(mod._QUEUE_PATH.read_text()) if mod._QUEUE_PATH.exists() else []
    assert len(q) == 1
    assert q[0]["title"] == "overflow"


# ── test 4: flush_pending sends queued alerts when tokens available ───────────
def test_flush_pending_drains_queue(mod, monkeypatch, tmp_path):
    router = mod._get_router()
    # Pre-populate queue with 2 items
    queue_items = [
        {"channel": "system", "level": "info", "title": f"q{i}",
         "body": "b", "fields": None, "queued_at": "2026-01-01T00:00:00+00:00"}
        for i in range(2)
    ]
    mod._QUEUE_PATH.write_text(json.dumps(queue_items))

    # Ensure tokens are full
    router._bucket.tokens = 30.0

    post_mock = MagicMock()
    monkeypatch.setattr("requests.post", post_mock)

    sent = mod.flush_pending()

    assert sent == 2
    remaining = json.loads(mod._QUEUE_PATH.read_text())
    assert remaining == []


# ── test 5: send_edge_alert produces correct Slack payload ────────────────────
def test_send_edge_alert_slack_payload(mod, monkeypatch):
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    mod._router = None

    captured: list[dict] = []

    def fake_post_slack(self, channel, level, title, body, fields):
        captured.append({"channel": channel, "level": level,
                          "title": title, "body": body, "fields": fields})
        return True

    monkeypatch.setattr(mod.AlertRouter, "_post_slack", fake_post_slack)
    monkeypatch.setattr(mod.AlertRouter, "_post_discord", lambda *a, **k: False)

    ok = mod.send_edge_alert("LeBron James", "PTS", 28.5, 31.2, 2.7, "over", 15.0)

    assert ok is True
    assert len(captured) == 1
    c = captured[0]
    assert c["channel"] == "edges"
    assert "LeBron James" in c["title"]
    assert c["fields"]["Player"] == "LeBron James"
    assert c["fields"]["Stat"] == "PTS"
    assert c["fields"]["Side"] == "over"


# ── test 6: send_drift_alert truncates body > 4000 chars ─────────────────────
def test_drift_alert_truncates_long_body(mod, monkeypatch):
    written: list[str] = []

    original_test_write = mod.AlertRouter._test_write

    def capture_test_write(self, channel, level, title, body, fields):
        written.append(body)
        original_test_write(self, channel, level, title, body, fields)

    monkeypatch.setattr(mod.AlertRouter, "_test_write", capture_test_write)

    # Craft a stat whose body description becomes huge via long stat name
    long_stat = "X" * 4100
    mod.send_drift_alert(long_stat, 2.5, 2.0, 7)

    assert len(written) == 1
    assert len(written[0]) <= mod._MAX_BODY
    assert written[0].endswith("...[truncated]")


# ── test 7: 2 consecutive 500 errors → service disabled, fallback test mode ───
def test_consecutive_failures_disable_service(mod, monkeypatch):
    monkeypatch.setenv("ALERTS_ENABLED",   "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    mod._router = None

    resp_500 = MagicMock()
    resp_500.status_code = 500
    resp_500.raise_for_status = MagicMock()

    post_mock = MagicMock(return_value=resp_500)
    monkeypatch.setattr("requests.post", post_mock)

    router = mod._get_router()

    # First failure
    router._post_slack("system", "info", "t1", "b", None)
    assert router._slack_fails == 1
    assert not router._slack_dead

    # Second failure → dead
    router._post_slack("system", "info", "t2", "b", None)
    assert router._slack_dead is True

    # Now send_alert should NOT call post again (service dead → test-mode)
    post_mock.reset_mock()
    result = mod.send_alert("system", "info", "after-dead", "body")
    assert result is True
    post_mock.assert_not_called()


# ── test 8: per-channel Discord webhook env var is preferred ──────────────────
def test_discord_per_channel_override(mod, monkeypatch):
    monkeypatch.setenv("ALERTS_ENABLED",                "true")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL",           "https://discord.com/global")
    monkeypatch.setenv("DISCORD_EDGES_WEBHOOK_URL",     "https://discord.com/edges-channel")
    mod._router = None

    used_urls: list[str] = []

    def fake_http_post(self, url: str, payload: dict, service: str) -> bool:
        used_urls.append(url)
        return True

    monkeypatch.setattr(mod.AlertRouter, "_http_post", fake_http_post)
    # Disable Slack so only Discord fires
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    mod.send_alert("edges", "info", "channel-test", "body")

    assert len(used_urls) == 1
    assert used_urls[0] == "https://discord.com/edges-channel"


# ── test 9: atomic write replaces pre-existing queue file ────────────────────
def test_atomic_write_replaces_existing_file(mod, monkeypatch, tmp_path):
    """_save_queue must replace an existing queue file atomically (no append)."""
    queue_path = tmp_path / "alert_queue.json"
    monkeypatch.setattr(mod, "_QUEUE_PATH", queue_path)

    # Pre-populate with stale data
    queue_path.write_text(json.dumps([{"stale": True}]), encoding="utf-8")

    router = mod._get_router()
    # _save_queue with an empty list should fully overwrite the file
    router._save_queue([])

    result = json.loads(queue_path.read_text(encoding="utf-8"))
    assert result == []


# ── test 10: atomic write leaves no partial file on os.replace failure ────────
def test_atomic_write_no_partial_on_failure(mod, monkeypatch, tmp_path):
    """If os.replace raises, the temp file is cleaned up and queue is unchanged."""
    queue_path = tmp_path / "alert_queue.json"
    original_data = [{"channel": "system", "level": "info", "title": "original",
                       "body": "b", "fields": None, "queued_at": "2026-01-01T00:00:00+00:00"}]
    queue_path.write_text(json.dumps(original_data), encoding="utf-8")
    monkeypatch.setattr(mod, "_QUEUE_PATH", queue_path)

    # Patch os.replace to simulate a mid-write failure
    original_replace = os.replace

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", boom)

    router = mod._get_router()
    # _save_queue swallows OSError via log.error — verify queue unchanged
    router._save_queue([{"new": "item"}])

    # Original file must be intact
    result = json.loads(queue_path.read_text(encoding="utf-8"))
    assert result == original_data

    # No orphaned .tmp files should remain in tmp_path
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Orphaned temp files found: {tmp_files}"


# ═══════════════════════════════════════════════════════════════════════════════
# L46 EventBus subscriber tests (tests 11–15)
# ═══════════════════════════════════════════════════════════════════════════════

# Helper: import L46 and L22 fresh, wiring them together on a clean bus.
def _fresh_modules_with_bus(monkeypatch, tmp_path):
    """Return (L22_mod, L46_mod, fresh_bus) with all singletons reset."""
    # Purge both modules from cache
    for key in list(sys.modules.keys()):
        if "L22_alerting" in key or "L46_event_bus" in key:
            del sys.modules[key]

    import scripts.execute_loop.L46_event_bus as L46
    import scripts.execute_loop.L22_alerting as L22

    # Give L22 a clean bus (not the global default) so tests are isolated
    bus = L46.EventBus()

    # Reset module-level state
    L22._router = None
    L22._subscribed = False

    # Redirect file I/O to tmp_path
    monkeypatch.setattr(L22, "_QUEUE_PATH", tmp_path / "alert_queue.json")
    monkeypatch.setattr(L22, "_LOG_DIR", tmp_path / "logs" / "alerts")
    (tmp_path / "logs" / "alerts").mkdir(parents=True, exist_ok=True)

    return L22, L46, bus


# ── test 11: register_subscribers creates handlers on the bus ─────────────────
def test_register_subscribers_creates_handlers(monkeypatch, tmp_path):
    L22, L46, bus = _fresh_modules_with_bus(monkeypatch, tmp_path)

    # Ensure ALERTS_VERBOSE_FILLS is off so we get exactly 4 subs
    monkeypatch.delenv("ALERTS_VERBOSE_FILLS", raising=False)

    L22.register_alert_subscribers(bus=bus)

    subs = [s for s in bus._subscriptions if s.layer == "L22"]
    assert len(subs) == 4, f"Expected 4 L22 subscribers, got {len(subs)}"
    patterns = {s.name_pattern for s in subs}
    assert "incident.opened"     in patterns
    assert "incident.classified" in patterns
    assert "drift.detected"      in patterns
    assert "risk_limit.breached" in patterns


# ── test 12: incident.opened P1 → send_alert called with level=error ──────────
def test_incident_opened_p1_triggers_error_alert(monkeypatch, tmp_path):
    L22, L46, bus = _fresh_modules_with_bus(monkeypatch, tmp_path)
    monkeypatch.delenv("ALERTS_VERBOSE_FILLS", raising=False)

    captured: list[dict] = []

    def fake_send_alert(channel, level, title, body, fields=None):
        captured.append({"channel": channel, "level": level, "title": title})
        return True

    monkeypatch.setattr(L22, "send_alert", fake_send_alert)

    L22.register_alert_subscribers(bus=bus)

    bus.publish(
        "incident.opened",
        source="L37",
        payload={"severity": "P1", "incident_id": "INC-001",
                 "description": "Executor heartbeat lost."},
    )

    assert len(captured) == 1
    assert captured[0]["level"] == "error"
    assert "INC-001" in captured[0]["title"]


# ── test 13: drift.detected error severity → send_alert called with level=warning
def test_drift_detected_error_triggers_warning_alert(monkeypatch, tmp_path):
    L22, L46, bus = _fresh_modules_with_bus(monkeypatch, tmp_path)
    monkeypatch.delenv("ALERTS_VERBOSE_FILLS", raising=False)

    captured: list[dict] = []

    def fake_send_alert(channel, level, title, body, fields=None):
        captured.append({"channel": channel, "level": level, "title": title})
        return True

    monkeypatch.setattr(L22, "send_alert", fake_send_alert)

    L22.register_alert_subscribers(bus=bus)

    bus.publish(
        "drift.detected",
        source="L18",
        payload={"severity": "error", "stat": "PTS",
                 "observed_mae": 5.1, "expected_mae": 4.6},
    )

    assert len(captured) == 1
    assert captured[0]["level"] == "warning"
    assert captured[0]["channel"] == "drift"


# ── test 14: risk_limit.breached → send_alert called with level=error ─────────
def test_risk_limit_breached_triggers_error_alert(monkeypatch, tmp_path):
    L22, L46, bus = _fresh_modules_with_bus(monkeypatch, tmp_path)
    monkeypatch.delenv("ALERTS_VERBOSE_FILLS", raising=False)

    captured: list[dict] = []

    def fake_send_alert(channel, level, title, body, fields=None):
        captured.append({"channel": channel, "level": level, "title": title})
        return True

    monkeypatch.setattr(L22, "send_alert", fake_send_alert)

    L22.register_alert_subscribers(bus=bus)

    bus.publish(
        "risk_limit.breached",
        source="L14",
        payload={"limit_type": "daily_loss", "current_value": -600, "threshold": -500},
    )

    assert len(captured) == 1
    assert captured[0]["level"] == "error"
    assert captured[0]["channel"] == "drawdown"


# ── test 15: register_alert_subscribers is idempotent ────────────────────────
def test_register_is_idempotent(monkeypatch, tmp_path):
    L22, L46, bus = _fresh_modules_with_bus(monkeypatch, tmp_path)
    monkeypatch.delenv("ALERTS_VERBOSE_FILLS", raising=False)

    L22.register_alert_subscribers(bus=bus)
    L22.register_alert_subscribers(bus=bus)  # second call — must be a no-op

    subs = [s for s in bus._subscriptions if s.layer == "L22"]
    assert len(subs) == 4, (
        f"Idempotency broken: expected 4 subs after 2 register calls, got {len(subs)}"
    )
