"""Tests for src/alerts/discord_webhook.py — R18 K3.

Covers: payload format, severity → color mapping, env-unset no-op,
rate-limit bucket, fallback queue, embed structure, smoke (one alert
per severity).
"""
from __future__ import annotations

import json
import os
import sys

import pytest

# Make `src.alerts...` importable without an install.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.alerts import discord_webhook as dw  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_discord(monkeypatch, tmp_path):
    """Capture every `_do_post` call.  Returns the captured list."""
    captured = []

    def _capture(url, payload):
        captured.append({"url": url, "payload": payload})
        return True

    monkeypatch.setattr("src.alerts.discord_webhook._do_post", _capture)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://mock/test")
    dw._reset_rate_limit()
    yield captured
    dw._reset_rate_limit()


@pytest.fixture
def fallback_path(tmp_path):
    return str(tmp_path / "discord_fallback.jsonl")


# ---------------------------------------------------------------------------
# 1. Embed payload format
# ---------------------------------------------------------------------------


def test_post_format_embed_keys(mock_discord):
    """Posted payload must wrap a single Discord embed with required keys."""
    ok = dw.post_alert("INFO", "test", "hello", "world")
    assert ok is True
    assert len(mock_discord) == 1
    payload = mock_discord[0]["payload"]
    assert "embeds" in payload
    assert len(payload["embeds"]) == 1
    embed = payload["embeds"][0]
    for key in ("title", "description", "color", "footer", "timestamp"):
        assert key in embed
    assert embed["footer"]["text"] == "source: test"
    assert "world" in embed["description"]
    assert "hello" in embed["title"]


def test_embed_structure_optional_fields(mock_discord):
    """When `fields` are passed they must appear as Discord field objects."""
    dw.post_alert(
        "URGENT",
        "auto_place_daemon",
        "FIRED Jokic OVER 28.5",
        "kelly=2.3%  stake=$57.50",
        fields=[
            {"name": "edge_pct", "value": "6.4%"},
            {"name": "book", "value": "fanduel"},
        ],
    )
    embed = mock_discord[0]["payload"]["embeds"][0]
    assert "fields" in embed
    assert len(embed["fields"]) == 2
    assert embed["fields"][0] == {"name": "edge_pct", "value": "6.4%",
                                    "inline": True}
    assert embed["fields"][1]["name"] == "book"


# ---------------------------------------------------------------------------
# 2. Severity colour mapping
# ---------------------------------------------------------------------------


def test_severity_colors_each_level(mock_discord):
    """Every documented severity maps to its documented color."""
    expected = {
        "URGENT": 0xE74C3C,
        "WARN":   0xF1C40F,
        "INFO":   0x2ECC71,
        "STEAM":  0x3498DB,
    }
    for sev, color in expected.items():
        dw._reset_rate_limit()
        mock_discord.clear()
        dw.post_alert(sev, "smoke", f"{sev} test", "body")
        assert mock_discord, f"no post captured for {sev}"
        assert mock_discord[0]["payload"]["embeds"][0]["color"] == color


def test_severity_unknown_falls_back_to_info(mock_discord):
    """Unknown severity → INFO color (no crash)."""
    dw.post_alert("MYSTERY", "smoke", "?", "?")
    assert mock_discord[0]["payload"]["embeds"][0]["color"] == 0x2ECC71


# ---------------------------------------------------------------------------
# 3. Env-unset → no-op
# ---------------------------------------------------------------------------


def test_env_unset_is_noop(monkeypatch):
    """When DISCORD_WEBHOOK_URL is missing post_alert returns False, no POST."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    calls = []
    monkeypatch.setattr("src.alerts.discord_webhook._do_post",
                         lambda u, p: calls.append((u, p)) or True)
    ok = dw.post_alert("URGENT", "test", "should not fire", "...")
    assert ok is False
    assert calls == []


def test_env_empty_string_is_noop(monkeypatch):
    """An empty/whitespace-only env var also no-ops."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "   ")
    calls = []
    monkeypatch.setattr("src.alerts.discord_webhook._do_post",
                         lambda u, p: calls.append((u, p)) or True)
    assert dw.post_alert("INFO", "t", "t", "b") is False
    assert calls == []


# ---------------------------------------------------------------------------
# 4. Rate-limit bucket
# ---------------------------------------------------------------------------


def test_rate_limit_caps_at_burst(monkeypatch, mock_discord, fallback_path):
    """Exactly _RATE_LIMIT_BURST messages get through within the window."""
    # Send burst + 3 — only burst should be POSTed.
    n = dw._RATE_LIMIT_BURST + 3
    for i in range(n):
        dw.post_alert("INFO", "rl", f"#{i}", "x",
                      fallback_path=fallback_path)
    assert len(mock_discord) == dw._RATE_LIMIT_BURST
    assert os.path.exists(fallback_path)
    with open(fallback_path) as fh:
        spilled = [json.loads(line) for line in fh]
    assert len(spilled) == 3
    assert all(s["reason"] == "rate_limited" for s in spilled)


def test_rate_limit_window_recovers(monkeypatch, mock_discord, fallback_path):
    """After the sliding window elapses, posting resumes."""
    # Patch monotonic so we don't actually sleep.
    fake_now = [1000.0]
    monkeypatch.setattr("src.alerts.discord_webhook.time.monotonic",
                         lambda: fake_now[0])
    # Fill the bucket.
    for i in range(dw._RATE_LIMIT_BURST):
        assert dw.post_alert("INFO", "rl", f"#{i}", "x",
                              fallback_path=fallback_path) is True
    assert dw.post_alert("INFO", "rl", "overflow", "x",
                          fallback_path=fallback_path) is False
    # Advance past the window.
    fake_now[0] += dw._RATE_LIMIT_WINDOW_SEC + 0.1
    mock_discord.clear()
    assert dw.post_alert("INFO", "rl", "after-window", "x",
                          fallback_path=fallback_path) is True
    assert len(mock_discord) == 1


# ---------------------------------------------------------------------------
# 5. Fallback queue on POST failure
# ---------------------------------------------------------------------------


def test_fallback_on_post_failure(monkeypatch, fallback_path):
    """If `_do_post` returns False the payload is appended to fallback JSONL."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://mock/test")
    monkeypatch.setattr("src.alerts.discord_webhook._do_post",
                         lambda u, p: False)
    dw._reset_rate_limit()
    ok = dw.post_alert("URGENT", "fail-test", "boom", "down",
                       fallback_path=fallback_path)
    assert ok is False
    assert os.path.exists(fallback_path)
    with open(fallback_path) as fh:
        lines = [json.loads(line) for line in fh]
    assert len(lines) == 1
    assert lines[0]["reason"] == "post_failed"
    assert lines[0]["payload"]["embeds"][0]["title"].startswith("[URGENT]")


# ---------------------------------------------------------------------------
# 6. Build embed unit (no network)
# ---------------------------------------------------------------------------


def test_build_embed_strips_oversized_text():
    """Title >256 chars and body >4000 chars get trimmed to Discord limits."""
    long_title = "X" * 500
    long_body = "Y" * 5000
    payload = dw.build_embed("URGENT", "trim", long_title, long_body)
    embed = payload["embeds"][0]
    # `[URGENT] ` prefix means the kept slice is 256 chars of title preceded
    # by the bracketed severity.
    assert embed["title"].startswith("[URGENT] ")
    # The original title is truncated to 256 before the bracket is added.
    assert len(embed["title"]) <= 256 + len("[URGENT] ")
    assert len(embed["description"]) == 4000


def test_build_embed_handles_tuple_fields():
    """Field list accepts (name, value) tuples as well as dicts."""
    payload = dw.build_embed("INFO", "t", "title", "body",
                              fields=[("k1", "v1"), {"name": "k2", "value": "v2"}])
    fields = payload["embeds"][0]["fields"]
    assert {"name": "k1", "value": "v1", "inline": True} in fields
    assert {"name": "k2", "value": "v2", "inline": True} in fields


# ---------------------------------------------------------------------------
# 7. Smoke — one alert per severity (matches the runbook smoke test)
# ---------------------------------------------------------------------------


def test_smoke_one_post_per_severity(mock_discord):
    """Posting one of each severity yields four captured embeds."""
    for sev in ("URGENT", "WARN", "INFO", "STEAM"):
        dw.post_alert(sev, "smoke", f"{sev} headline", f"{sev} body")
    titles = [p["payload"]["embeds"][0]["title"] for p in mock_discord]
    assert any("URGENT" in t for t in titles)
    assert any("WARN" in t for t in titles)
    assert any("INFO" in t for t in titles)
    assert any("STEAM" in t for t in titles)
    assert len(mock_discord) == 4
