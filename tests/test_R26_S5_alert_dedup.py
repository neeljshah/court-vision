"""tests/test_R26_S5_alert_dedup.py — R26_S5 alert rate-limit + dedup tests.

Covers the in-process LRU + persistent sidecar dedup layer added on top
of R21_N3's layered alert path:

* Same key fires up to cap, then every subsequent fire is suppressed.
* Different keys are independent.
* Cap varies by level: info=1, warn=3 (default), critical=5.
* Window rotates after _DEDUP_WINDOW_SEC of inactivity.
* Every 10th suppression emits a single meta-alert.
* On-disk state survives a "process restart" (clear LRU + re-hydrate).
* flush_dedup() resets both layers.
* Concurrent fires never double-count the cap.
* Dedup key is based on a 64-char message PREFIX so similar messages
  with different trailing payloads collapse onto one key.
* All R21_N3 backward-compat behaviour preserved.

Ship gate: 10+ tests, all must pass.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

import pytest

# Make `src.alerts...` importable without an install.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.alerts import discord_webhook as dw  # noqa: E402
from src.alerts.discord_webhook import (  # noqa: E402
    alert,
    flush_dedup,
    get_dedup_stats,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def paths(tmp_path):
    return {
        "vault":    str(tmp_path / "alerts.md"),
        "critical": str(tmp_path / "critical"),
        "fallback": str(tmp_path / "discord_fallback.jsonl"),
        "dedup":    str(tmp_path / "alert_dedup_state.json"),
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


@pytest.fixture
def clean_dedup(paths):
    """Ensure a clean slate before AND after each test."""
    flush_dedup(paths["dedup"])
    yield
    flush_dedup(paths["dedup"])


def _fire(msg: str, level: str, tag: str, paths_, **extra):
    return alert(
        msg,
        level=level,
        tag=tag,
        vault_path=paths_["vault"],
        critical_stack_dir=paths_["critical"],
        fallback_path=paths_["fallback"],
        dedup_state_path=paths_["dedup"],
        **extra,
    )


# ---------------------------------------------------------------------------
# 1. Identical warn alerts: cap=3 → 3 fire, rest suppressed.
# ---------------------------------------------------------------------------


def test_same_warn_alert_fires_cap_then_suppressed(
    monkeypatch, paths, captured_discord, clean_dedup
):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    fired, suppressed = 0, 0
    for _ in range(5):
        r = _fire("middle_finder crashed", "warn", "middle_finder_watch", paths)
        if r.get("suppressed"):
            suppressed += 1
        else:
            fired += 1

    assert fired == 3, f"expected 3 fires within warn cap, got {fired}"
    assert suppressed == 2, f"expected 2 suppressions, got {suppressed}"

    # Vault has exactly 3 entry lines for the message.
    with open(paths["vault"], encoding="utf-8") as fh:
        text = fh.read()
    assert text.count("middle_finder crashed") == 3


# ---------------------------------------------------------------------------
# 2. Different keys are independent — each gets its own quota.
# ---------------------------------------------------------------------------


def test_different_alerts_are_not_deduped(
    monkeypatch, paths, captured_discord, clean_dedup
):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    r1 = _fire("alert A", "warn", "tag_A", paths)
    r2 = _fire("alert B", "warn", "tag_B", paths)
    r3 = _fire("alert C", "warn", "tag_C", paths)

    assert all(not r.get("suppressed") for r in (r1, r2, r3))

    stats = get_dedup_stats(paths["dedup"])
    assert stats["keys_tracked"] == 3
    assert stats["total_fired"] == 3
    assert stats["total_suppressed"] == 0


# ---------------------------------------------------------------------------
# 3. Window expiry — after window rotates, the next fire is fresh.
# ---------------------------------------------------------------------------


def test_window_expiry_resets_quota(
    monkeypatch, paths, captured_discord, clean_dedup
):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    # Shrink window so we can test expiry deterministically.
    monkeypatch.setattr(dw, "_DEDUP_WINDOW_SEC", 0.10)

    for _ in range(3):
        _fire("flap", "warn", "flap_tag", paths)

    # 4th inside window → suppressed.
    r4 = _fire("flap", "warn", "flap_tag", paths)
    assert r4.get("suppressed") is True

    # Sleep past the window and fire again — should be allowed.
    time.sleep(0.15)
    r5 = _fire("flap", "warn", "flap_tag", paths)
    assert r5.get("suppressed") is False
    assert r5.get("fire_count") == 1


# ---------------------------------------------------------------------------
# 4. Critical level has a higher cap (5).
# ---------------------------------------------------------------------------


def test_critical_level_has_higher_cap(
    monkeypatch, paths, captured_discord, clean_dedup
):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    fired = 0
    for _ in range(8):
        r = _fire("RISK ALARM: bankroll drawdown", "critical", "bankroll", paths)
        if not r.get("suppressed"):
            fired += 1
    assert fired == 5, f"critical cap should be 5, got {fired}"

    # Stack should have 5 critical records.
    files = [
        f for f in os.listdir(paths["critical"])
        if f.startswith("critical_") and f.endswith(".json")
    ]
    assert len(files) == 1
    with open(os.path.join(paths["critical"], files[0]), encoding="utf-8") as fh:
        stack = json.load(fh)
    assert len(stack) == 5


# ---------------------------------------------------------------------------
# 5. Info level is capped at 1.
# ---------------------------------------------------------------------------


def test_info_level_capped_at_one(
    monkeypatch, paths, captured_discord, clean_dedup
):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    fired = 0
    suppressed = 0
    for _ in range(4):
        r = _fire("daily heartbeat", "info", "ops_heartbeat", paths)
        if r.get("suppressed"):
            suppressed += 1
        else:
            fired += 1
    assert fired == 1
    assert suppressed == 3


# ---------------------------------------------------------------------------
# 6. Meta-alert fires after the 10th suppression.
# ---------------------------------------------------------------------------


def test_meta_alert_fires_after_n_suppressions(
    monkeypatch, paths, captured_discord, clean_dedup
):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    # Use info (cap 1) so we hit suppressions fast.
    meta_fires = 0
    for _ in range(11):  # 1 fire + 10 suppressions
        r = _fire("identical info ping", "info", "spammy", paths)
        if r.get("meta_alert_fired"):
            meta_fires += 1

    assert meta_fires == 1, (
        f"meta should fire exactly once on the 10th suppression, got {meta_fires}"
    )

    # Vault should contain the meta-alert text.
    with open(paths["vault"], encoding="utf-8") as fh:
        text = fh.read()
    assert "10 identical alerts suppressed in last hour" in text
    assert "identical info ping" in text


# ---------------------------------------------------------------------------
# 7. State persists across "process restart" (clear LRU + re-hydrate).
# ---------------------------------------------------------------------------


def test_state_persists_across_process_restart(
    monkeypatch, paths, captured_discord, clean_dedup
):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    # Fire 3 warn alerts — should hit the cap.
    for _ in range(3):
        r = _fire("flap-persist", "warn", "watch", paths)
        assert not r.get("suppressed")

    # Sidecar must exist on disk.
    assert os.path.exists(paths["dedup"])
    with open(paths["dedup"], encoding="utf-8") as fh:
        blob = json.load(fh)
    assert blob["version"] == 1
    assert len(blob["entries"]) == 1

    # Simulate a process restart: wipe the in-process LRU + the
    # _DEDUP_LOADED_FROM cookie so the next call must re-hydrate.
    with dw._DEDUP_LOCK:
        dw._DEDUP_STATE.clear()
        dw._DEDUP_LOADED_FROM = None

    # The 4th fire (now after "restart") should still be suppressed
    # because state was rehydrated from disk.
    r4 = _fire("flap-persist", "warn", "watch", paths)
    assert r4.get("suppressed") is True, "state should rehydrate from disk"


# ---------------------------------------------------------------------------
# 8. Concurrent fires don't double-count the cap.
# ---------------------------------------------------------------------------


def test_concurrent_fires_respect_cap(
    monkeypatch, paths, captured_discord, clean_dedup
):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    n_threads = 20
    per = 5
    results: list = []
    lock = threading.Lock()

    def worker():
        local = []
        for _ in range(per):
            r = _fire("concurrent flap", "warn", "concurrent_tag", paths)
            local.append(bool(r.get("suppressed")))
        with lock:
            results.extend(local)

    ts = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    fired = sum(1 for s in results if s is False)
    suppressed = sum(1 for s in results if s is True)
    assert fired == 3, f"warn cap should hold under contention, got {fired} fires"
    assert suppressed == n_threads * per - 3


# ---------------------------------------------------------------------------
# 9. Dedup key is based on a 64-char message PREFIX.
# ---------------------------------------------------------------------------


def test_dedup_key_based_on_message_prefix(
    monkeypatch, paths, captured_discord, clean_dedup
):
    """Two alerts whose first 64 chars match should collapse onto one key
    even when their trailing payload differs."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    prefix = "watchdog restarted middle_finder daemon after crash detected"
    # Both messages share the first 64 chars but differ in the trailing
    # pid → should collapse onto a single dedup key.
    assert len(prefix) >= 60
    m1 = prefix + " (pid=1234)"
    m2 = prefix + " (pid=5678)"
    m3 = prefix + " (pid=9999)"
    m4 = prefix + " (pid=1111)"

    k1 = dw._dedup_key(m1, "warn", "watchdog")
    k2 = dw._dedup_key(m2, "warn", "watchdog")
    k3 = dw._dedup_key(m3, "warn", "watchdog")
    assert k1 == k2 == k3, "prefix-based dedup keys must collapse"

    # Fire 4 — warn cap=3, so the 4th must be suppressed.
    r1 = _fire(m1, "warn", "watchdog", paths)
    r2 = _fire(m2, "warn", "watchdog", paths)
    r3 = _fire(m3, "warn", "watchdog", paths)
    r4 = _fire(m4, "warn", "watchdog", paths)

    assert not r1.get("suppressed")
    assert not r2.get("suppressed")
    assert not r3.get("suppressed")
    assert r4.get("suppressed") is True

    # And the full message text (with the differing pid) was preserved in
    # the vault on the 3 that actually fired.
    with open(paths["vault"], encoding="utf-8") as fh:
        text = fh.read()
    assert "pid=1234" in text
    assert "pid=5678" in text
    assert "pid=9999" in text
    # The suppressed one's full text NEVER reached the vault.
    assert "pid=1111" not in text


# ---------------------------------------------------------------------------
# 10. flush_dedup() resets both the in-process LRU and the sidecar.
# ---------------------------------------------------------------------------


def test_flush_dedup_resets_state(
    monkeypatch, paths, captured_discord, clean_dedup
):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    # Hit the cap then verify suppression.
    for _ in range(3):
        _fire("burst", "warn", "burst_tag", paths)
    r_supp = _fire("burst", "warn", "burst_tag", paths)
    assert r_supp.get("suppressed") is True
    assert os.path.exists(paths["dedup"])

    # Flush.
    assert flush_dedup(paths["dedup"]) is True
    assert not os.path.exists(paths["dedup"])

    stats = get_dedup_stats(paths["dedup"])
    assert stats["keys_tracked"] == 0

    # The very next fire of the same alert should be allowed again.
    r_after = _fire("burst", "warn", "burst_tag", paths)
    assert r_after.get("suppressed") is False
    assert r_after.get("fire_count") == 1


# ---------------------------------------------------------------------------
# 11. get_dedup_stats reflects fire + suppression counts accurately.
# ---------------------------------------------------------------------------


def test_get_dedup_stats_accuracy(
    monkeypatch, paths, captured_discord, clean_dedup
):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    for _ in range(5):
        _fire("stats_check", "warn", "x", paths)  # 3 fire, 2 suppress
    _fire("stats_other", "warn", "y", paths)      # 1 fire

    stats = get_dedup_stats(paths["dedup"])
    assert stats["keys_tracked"] == 2
    assert stats["total_fired"] == 4   # 3 + 1
    assert stats["total_suppressed"] == 2
    assert stats["default_cap"] == 3
    assert stats["level_caps"]["info"] == 1
    assert stats["level_caps"]["critical"] == 5


# ---------------------------------------------------------------------------
# 12. Atomic write — no .tmp file is left dangling on success.
# ---------------------------------------------------------------------------


def test_atomic_state_write_leaves_no_tmp(
    monkeypatch, paths, captured_discord, clean_dedup
):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    _fire("atomic check", "warn", "atomic", paths)
    assert os.path.exists(paths["dedup"])
    assert not os.path.exists(paths["dedup"] + ".tmp")
