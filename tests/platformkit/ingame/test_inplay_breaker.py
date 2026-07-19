"""Per-file test for scripts.platformkit.ingame.inplay_breaker.

Run: python -m pytest tests/platformkit/ingame/test_inplay_breaker.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts.platformkit.ingame import inplay_breaker as ib


def _ledger(tmp_path, rows):
    p = tmp_path / "clv_ledger.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


def test_missing_ledger_fails_open(tmp_path):
    res = ib.allow("win_home", _NOW, tmp_path / "absent.jsonl")
    assert res["allowed"] is True


def test_no_graded_rows_caps_channel(tmp_path):
    # No graded CLV yet -> breaker is CAPPED (median None), but under-cap allows.
    p = _ledger(tmp_path, [
        {"channel": "paper_ingame", "market": "win_home",
         "ts": "2026-07-19T01:00:00+00:00"}])
    res = ib.allow("win_home", _NOW, p)
    assert res["state"] == "CAPPED" and res["allowed"] is True


def test_negative_median_clv_caps_and_daily_cap_binds(tmp_path):
    from scripts.platformkit.execution.thresholds import BREAKER_CAPPED_MAX_PER_DAY
    graded = [
        {"channel": "paper_ingame", "market": "win_home", "clv_pct": -5.0,
         "ts": "2026-07-19T01:00:00+00:00"} for _ in range(6)]
    today = [
        {"channel": "paper_ingame", "market": "win_home",
         "ts": "2026-07-20T01:00:00+00:00"} for _ in range(BREAKER_CAPPED_MAX_PER_DAY)]
    p = _ledger(tmp_path, graded + today)
    res = ib.allow("win_home", _NOW, p)
    assert res["state"] == "CAPPED" and res["allowed"] is False
    assert res["reason"] == "cap_reached"


def test_positive_median_clv_stays_live(tmp_path):
    graded = [
        {"channel": "paper_ingame", "market": "win_home", "clv_pct": 2.0,
         "ts": "2026-07-19T01:00:00+00:00"} for _ in range(6)]
    p = _ledger(tmp_path, graded)
    res = ib.allow("win_home", _NOW, p)
    assert res["state"] == "LIVE" and res["allowed"] is True


def test_other_channels_ignored(tmp_path):
    # Pregame-channel rows must not leak into the in-game breaker's window.
    rows = [{"channel": "pregame", "market": "win_home", "clv_pct": -9.0,
             "ts": "2026-07-19T01:00:00+00:00"} for _ in range(9)]
    p = _ledger(tmp_path, rows)
    assert ib._load_channel_rows(p) == []
