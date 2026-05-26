"""tests/test_alert_fallback.py — R21_N3 layered alert fallback tests.

Covers the layered ``alert()`` helper:

* DISCORD_WEBHOOK_URL set    → Discord POST (mocked) + vault append.
* DISCORD_WEBHOOK_URL unset  → vault append + critical-stack JSON
                               + ``discord_sent=False`` (no raise).
* level=critical             → critical stack written REGARDLESS of URL.
* Vault file is APPEND-ONLY  → multiple alerts don't truncate.
* Concurrent alerts          → vault file stays well-formed under threads.

Ship gate: every assertion below must hold for R21_N3 to count as done.
"""
from __future__ import annotations

import json
import os
import sys
import threading

import pytest

# Make `src.alerts...` importable without an install.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.alerts import discord_webhook as dw  # noqa: E402
from src.alerts.discord_webhook import alert, post_alert  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — pin every path under tmp_path so tests are hermetic.
# ---------------------------------------------------------------------------


@pytest.fixture
def paths(tmp_path):
    return {
        "vault":    str(tmp_path / "alerts.md"),
        "critical": str(tmp_path / "critical"),
        "fallback": str(tmp_path / "discord_fallback.jsonl"),
    }


@pytest.fixture
def captured_discord(monkeypatch):
    """Capture every ``_do_post`` call (URL + payload)."""
    sink = []

    def _capture(url, payload):
        sink.append({"url": url, "payload": payload})
        return True

    monkeypatch.setattr("src.alerts.discord_webhook._do_post", _capture)
    dw._reset_rate_limit()
    yield sink
    dw._reset_rate_limit()


# ---------------------------------------------------------------------------
# 1. With DISCORD_WEBHOOK_URL set → Discord + vault.
# ---------------------------------------------------------------------------


def test_url_set_posts_discord_and_appends_vault(monkeypatch, paths, captured_discord):
    """Webhook configured → Discord POST fires AND vault gets the line."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://mock/webhook")

    result = alert(
        "Watchdog restarted bankroll_monitor (rc=0)",
        level="warn",
        tag="daemon_watchdog",
        vault_path=paths["vault"],
        critical_stack_dir=paths["critical"],
        fallback_path=paths["fallback"],
    )

    assert result["discord_sent"] is True
    assert result["vault_appended"] is True
    # warn level + URL set → no critical-stack push.
    assert result["file_written"] is False

    # Discord captured the embed.
    assert len(captured_discord) == 1
    assert captured_discord[0]["url"] == "http://mock/webhook"

    # Vault file got the entry.
    assert os.path.exists(paths["vault"])
    with open(paths["vault"], encoding="utf-8") as fh:
        text = fh.read()
    assert "Watchdog restarted bankroll_monitor (rc=0)" in text
    assert "[WARN]" in text
    assert "[daemon_watchdog]" in text


# ---------------------------------------------------------------------------
# 2. Without URL set → vault + critical stack only, returns False.
# ---------------------------------------------------------------------------


def test_url_unset_writes_vault_and_critical_stack(monkeypatch, paths, captured_discord):
    """No webhook → vault + critical stack still receive the alert."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    result = alert(
        "Bankroll dropped below stop-loss",
        level="warn",
        tag="bankroll_monitor_daemon",
        vault_path=paths["vault"],
        critical_stack_dir=paths["critical"],
        fallback_path=paths["fallback"],
    )

    assert result["discord_sent"] is False           # no URL → no POST
    assert result["vault_appended"] is True          # durable record
    assert result["file_written"] is True            # URL-unset triggers stack

    # No Discord POST attempted.
    assert captured_discord == []

    # Vault has the line.
    with open(paths["vault"], encoding="utf-8") as fh:
        assert "Bankroll dropped below stop-loss" in fh.read()

    # Critical stack file exists and contains the record.
    files = [f for f in os.listdir(paths["critical"])
             if f.startswith("critical_") and f.endswith(".json")]
    assert len(files) == 1
    with open(os.path.join(paths["critical"], files[0]), encoding="utf-8") as fh:
        stack = json.load(fh)
    assert isinstance(stack, list) and len(stack) == 1
    assert stack[0]["message"] == "Bankroll dropped below stop-loss"
    assert stack[0]["tag"] == "bankroll_monitor_daemon"


def test_url_unset_does_not_raise(monkeypatch, paths):
    """No URL → call still returns a dict, never raises."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    # No mock — real _do_post would be unreachable anyway since URL is empty.
    out = alert(
        "smoke",
        level="info",
        vault_path=paths["vault"],
        critical_stack_dir=paths["critical"],
        fallback_path=paths["fallback"],
    )
    assert isinstance(out, dict)
    assert out["discord_sent"] is False


# ---------------------------------------------------------------------------
# 3. Critical level → critical stack ALWAYS, even with URL set.
# ---------------------------------------------------------------------------


def test_critical_always_writes_stack_even_with_url(monkeypatch, paths, captured_discord):
    """level=critical → stack written even when Discord POST succeeded."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://mock/webhook")

    result = alert(
        "RISK ALARM: drawdown breach",
        level="critical",
        tag="bankroll_monitor_daemon",
        vault_path=paths["vault"],
        critical_stack_dir=paths["critical"],
        fallback_path=paths["fallback"],
    )

    assert result["discord_sent"] is True
    assert result["vault_appended"] is True
    assert result["file_written"] is True  # critical → stack regardless

    files = [f for f in os.listdir(paths["critical"])
             if f.startswith("critical_") and f.endswith(".json")]
    assert len(files) == 1


# ---------------------------------------------------------------------------
# 4. Vault is append-only — multiple alerts accumulate, never truncate.
# ---------------------------------------------------------------------------


def test_vault_is_append_only(monkeypatch, paths, captured_discord):
    """Firing N alerts leaves N entry lines in the vault file."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://mock/webhook")

    for i in range(5):
        alert(
            f"alert-#{i}",
            level="info",
            tag="probe",
            vault_path=paths["vault"],
            critical_stack_dir=paths["critical"],
            fallback_path=paths["fallback"],
        )

    with open(paths["vault"], encoding="utf-8") as fh:
        lines = fh.readlines()
    # Header (2 lines) + blank + 5 alert lines.
    entry_lines = [ln for ln in lines if ln.startswith("- ")]
    assert len(entry_lines) == 5
    for i in range(5):
        assert any(f"alert-#{i}" in ln for ln in entry_lines)


def test_critical_stack_is_append_only(monkeypatch, paths):
    """Firing N critical alerts grows the stack JSON array to N records."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    for i in range(4):
        alert(
            f"crit-#{i}",
            level="critical",
            tag="probe",
            vault_path=paths["vault"],
            critical_stack_dir=paths["critical"],
            fallback_path=paths["fallback"],
        )
    files = [f for f in os.listdir(paths["critical"])
             if f.startswith("critical_") and f.endswith(".json")]
    assert len(files) == 1
    with open(os.path.join(paths["critical"], files[0]), encoding="utf-8") as fh:
        stack = json.load(fh)
    assert len(stack) == 4
    assert [r["message"] for r in stack] == [f"crit-#{i}" for i in range(4)]


# ---------------------------------------------------------------------------
# 5. Concurrency — N threads firing alerts don't corrupt the vault file.
# ---------------------------------------------------------------------------


def test_concurrent_alerts_do_not_corrupt_vault(monkeypatch, paths, captured_discord):
    """20 threads × 5 alerts each → 100 well-formed entry lines, no tearing."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://mock/webhook")

    threads = 20
    per = 5
    errors: list = []

    def worker(tid: int) -> None:
        try:
            for i in range(per):
                alert(
                    f"t{tid}-i{i}",
                    level="info",
                    tag=f"thread-{tid}",
                    vault_path=paths["vault"],
                    critical_stack_dir=paths["critical"],
                    fallback_path=paths["fallback"],
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert errors == []

    with open(paths["vault"], encoding="utf-8") as fh:
        lines = fh.readlines()

    # Every entry line starts with "- " and ends with newline — no torn writes.
    entry_lines = [ln for ln in lines if ln.startswith("- ")]
    assert len(entry_lines) == threads * per
    for ln in entry_lines:
        # well-formed: tag bracket present, ends in newline.
        assert ln.endswith("\n")
        assert "[INFO]" in ln
        assert "[thread-" in ln


def test_concurrent_critical_stack_not_corrupted(monkeypatch, paths):
    """10 threads × 3 critical alerts → stack JSON parses with 30 records."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    threads = 10
    per = 3
    errors: list = []

    def worker(tid: int) -> None:
        try:
            for i in range(per):
                alert(
                    f"crit-t{tid}-i{i}",
                    level="critical",
                    tag=f"thread-{tid}",
                    vault_path=paths["vault"],
                    critical_stack_dir=paths["critical"],
                    fallback_path=paths["fallback"],
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert errors == []

    files = [f for f in os.listdir(paths["critical"])
             if f.startswith("critical_") and f.endswith(".json")]
    assert len(files) == 1

    # File must be valid JSON (atomic-replace + lock → no tearing).
    with open(os.path.join(paths["critical"], files[0]), encoding="utf-8") as fh:
        stack = json.load(fh)
    assert isinstance(stack, list)
    assert len(stack) == threads * per


# ---------------------------------------------------------------------------
# 6. Legacy post_alert backward-compat — bool return + layered side effects.
# ---------------------------------------------------------------------------


def test_legacy_post_alert_still_returns_bool_and_layers(monkeypatch, paths, captured_discord):
    """R18_K3 callers gate on `post_alert(...) is True`. Must keep working."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://mock/webhook")

    ok = post_alert(
        "URGENT",
        "auto_place_daemon",
        "LIVE FIRE — Jokic OVER 28.5",
        "kelly=2.3%  stake=$57.50",
        vault_path=paths["vault"],
        critical_stack_dir=paths["critical"],
        fallback_path=paths["fallback"],
    )
    assert ok is True  # Discord HTTP outcome preserved

    # Vault still got the durable record.
    with open(paths["vault"], encoding="utf-8") as fh:
        assert "Jokic OVER 28.5" in fh.read()

    # URGENT maps to critical → stack written even with URL set.
    files = [f for f in os.listdir(paths["critical"])
             if f.startswith("critical_") and f.endswith(".json")]
    assert len(files) == 1


def test_legacy_post_alert_url_unset_returns_false_still_layers(monkeypatch, paths):
    """URL unset → bool False (R18_K3 contract) but vault + stack still fire."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    ok = post_alert(
        "URGENT",
        "auto_place_daemon",
        "headline",
        "body",
        vault_path=paths["vault"],
        critical_stack_dir=paths["critical"],
        fallback_path=paths["fallback"],
    )
    assert ok is False
    assert os.path.exists(paths["vault"])
    files = [f for f in os.listdir(paths["critical"])
             if f.startswith("critical_") and f.endswith(".json")]
    assert len(files) == 1
