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


def test_missing_ledger_is_an_empty_history_not_an_error(tmp_path):
    # No file = no graded rows = CAPPED-but-under-cap, the same as an empty one.
    res = ib.allow("win_home", _NOW, tmp_path / "absent.jsonl")
    assert res["allowed"] is True and res["state"] == "CAPPED"


def test_unreadable_ledger_fails_closed(tmp_path, monkeypatch):
    # Audit 2026-09-17 defect #7: allow() used to return allowed=True on ANY
    # exception. A safety interlock whose state cannot be read is not known to be
    # clear, and the grade capture upstream is never gated by this, so failing
    # closed suppresses the placement only -- it never freezes measurement.
    p = _ledger(tmp_path, [{"channel": "paper_ingame", "market": "win_home",
                            "ts": "2026-07-19T01:00:00+00:00"}])

    def _boom(*args, **kwargs):
        raise OSError("device or resource busy")

    monkeypatch.setattr(ib.Path, "open", _boom)
    res = ib.allow("win_home", _NOW, p)
    assert res["allowed"] is False
    assert res["state"] == "ERROR_FAIL_CLOSED"


def _raw(tmp_path, text):
    p = tmp_path / "clv_ledger.jsonl"
    p.write_text(text, encoding="utf-8")
    return p


_GOOD = ('{"channel": "paper_ingame", "market": "win_home", '
         '"clv_pct": 2.0, "ts": "2026-07-19T01:00:00+00:00"}')


def test_garbled_middle_line_fails_closed(tmp_path):
    # A bad line SKIPPED is a garbled ledger read as a clean empty one. Only a
    # trailing partial line is benign.
    p = _raw(tmp_path, "\n".join([_GOOD, "{not json at all", _GOOD]) + "\n")
    res = ib.allow("win_home", _NOW, p)
    assert res["allowed"] is False
    assert res["state"] == "ERROR_FAIL_CLOSED"


def test_trailing_partial_line_is_tolerated(tmp_path):
    # What a concurrent append looks like mid-write: the complete rows still
    # grade and the breaker behaves exactly as if the partial line were absent.
    clean = tmp_path / "clean.jsonl"
    clean.write_text("\n".join([_GOOD] * 6) + "\n", encoding="utf-8")
    partial = _raw(tmp_path, "\n".join([_GOOD] * 6) + '\n{"channel": "paper_i')
    assert len(ib._load_channel_rows(partial)) == 6
    assert ib.allow("win_home", _NOW, partial) == ib.allow("win_home", _NOW, clean)


def test_blank_lines_are_never_treated_as_corruption(tmp_path):
    p = _raw(tmp_path, "\n".join([_GOOD, "", _GOOD, ""]) + "\n")
    assert len(ib._load_channel_rows(p)) == 2


def test_empty_ledger_file_is_still_an_empty_history(tmp_path):
    res = ib.allow("win_home", _NOW, _raw(tmp_path, ""))
    assert res["allowed"] is True and res["state"] == "CAPPED"


def test_unreadable_ledger_raises_rather_than_reading_empty(tmp_path, monkeypatch):
    p = _ledger(tmp_path, [{"channel": "paper_ingame", "market": "win_home",
                            "ts": "2026-07-19T01:00:00+00:00"}])

    def _boom(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(ib.Path, "open", _boom)
    try:
        ib._load_channel_rows(p)
    except ib.LedgerUnreadable:
        return
    raise AssertionError("an unreadable ledger must not read as an empty one")


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


def test_taker_series_rows_never_blend_into_maker_pool(tmp_path):
    # READ-TIME CLV-series separation: a future taker row must not pollute the
    # maker series' breaker statistics; untagged legacy rows stay maker.
    rows = [
        {"channel": "paper_ingame", "market": "win_home", "clv_pct": 2.0,
         "taken_book": "paper_ingame_maker", "ts": "2026-07-19T01:00:00+00:00"},
        {"channel": "paper_ingame", "market": "win_home", "clv_pct": -50.0,
         "taken_book": "paper_ingame_taker", "ts": "2026-07-19T02:00:00+00:00"},
        {"channel": "paper_ingame", "market": "win_home", "clv_pct": 2.0,
         "ts": "2026-07-19T03:00:00+00:00"},  # legacy untagged -> maker
    ]
    p = _ledger(tmp_path, rows)
    loaded = ib._load_channel_rows(p)
    assert len(loaded) == 2
    assert all(r.get("taken_book") != "paper_ingame_taker" for r in loaded)
    taker = ib._load_channel_rows(p, series="paper_ingame_taker")
    assert len(taker) == 1 and taker[0]["clv_pct"] == -50.0
