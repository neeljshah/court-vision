"""
test_failure_alerting.py — Tests for the failure alerting pipeline.

Covers:
  1. Alert file creation on stage failure
  2. vault/alerts.log append on failure
  3. send_alert() returns False when Telegram env vars are missing
  4. send_telegram.py CLI exits 1 when no Telegram env vars are set
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent


def _write_alert(alerts_dir: Path, vault_log: Path, date: str, stage: str) -> None:
    """Replicate the _fail() logic from daily_run.sh in Python for unit testing."""
    alerts_dir.mkdir(parents=True, exist_ok=True)
    msg = f"Daily pipeline FAILED at stage: {stage} (date={date})"
    alert_file = alerts_dir / f"ALERT_{date}.txt"
    alert_file.write_text(msg)
    with vault_log.open("a") as fh:
        fh.write(f"2026-05-21T00:00:00Z {msg}\n")


# ---------------------------------------------------------------------------
# Test 1: alert file is created on failure
# ---------------------------------------------------------------------------

def test_alert_file_created(tmp_path: Path) -> None:
    alerts_dir = tmp_path / "data" / "output" / "alerts"
    vault_log = tmp_path / "vault" / "alerts.log"
    vault_log.parent.mkdir(parents=True, exist_ok=True)
    date = "2026-05-21"

    _write_alert(alerts_dir, vault_log, date, "record_slate_results")

    alert_file = alerts_dir / f"ALERT_{date}.txt"
    assert alert_file.exists(), "ALERT file was not created"
    content = alert_file.read_text()
    assert "record_slate_results" in content
    assert date in content


# ---------------------------------------------------------------------------
# Test 2: vault/alerts.log is appended on failure
# ---------------------------------------------------------------------------

def test_vault_log_appended(tmp_path: Path) -> None:
    alerts_dir = tmp_path / "data" / "output" / "alerts"
    vault_log = tmp_path / "vault" / "alerts.log"
    vault_log.parent.mkdir(parents=True, exist_ok=True)
    date = "2026-05-21"

    # Call twice to verify append (not overwrite)
    _write_alert(alerts_dir, vault_log, date, "stage_one")
    _write_alert(alerts_dir, vault_log, date, "stage_two")

    lines = vault_log.read_text().splitlines()
    assert len(lines) == 2, f"Expected 2 log lines, got {len(lines)}"
    assert "stage_one" in lines[0]
    assert "stage_two" in lines[1]


# ---------------------------------------------------------------------------
# Test 3: send_alert returns False when env vars are missing
# ---------------------------------------------------------------------------

def test_send_telegram_no_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    # Import after env manipulation to ensure clean state
    from src.monitoring.telegram_alerter import send_alert  # noqa: PLC0415

    result = send_alert("test alert — no creds")
    assert result is False, "send_alert should return False when credentials are absent"


# ---------------------------------------------------------------------------
# Test 4: send_telegram.py CLI exits 1 when no Telegram env vars are set
# ---------------------------------------------------------------------------

def test_send_telegram_cli() -> None:
    cli = PROJECT_ROOT / "scripts" / "bot_guards" / "send_telegram.py"
    assert cli.exists(), f"send_telegram.py not found at {cli}"

    env = {k: v for k, v in os.environ.items()}
    env.pop("TELEGRAM_BOT_TOKEN", None)
    env.pop("TELEGRAM_CHAT_ID", None)

    result = subprocess.run(
        [sys.executable, str(cli), "test alert"],
        capture_output=True,
        env=env,
    )
    assert result.returncode == 1, (
        f"Expected exit code 1 (no creds), got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
