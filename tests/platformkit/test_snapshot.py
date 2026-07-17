"""Per-file test for scripts.platformkit.odds_provider.snapshot (offline, tmp dir).

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_snapshot.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts.platformkit.odds_provider.markets import (
    MONEYLINE, TOTAL, MarketQuote,
)
from scripts.platformkit.odds_provider.snapshot import write_quotes


def _quote(**kw):
    base = dict(
        sport="nba", game_id="G1", home="Knicks", away="Spurs",
        market_type=MONEYLINE, side="home", line=None, odds=1.91,
        book="espn:DraftKings", captured_at="2026-06-18T18:00:00+00:00",
        devigged_prob=0.52,
    )
    base.update(kw)
    return MarketQuote(**base)


def _read_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def test_writes_one_row_per_quote_to_sport_date_file(tmp_path):
    quotes = [
        _quote(side="home", odds=1.91),
        _quote(side="away", odds=2.05),
        _quote(market_type=TOTAL, side="over", line=220.5, odds=1.90),
    ]
    res = write_quotes(quotes, out_dir=tmp_path,
                       commence_by_game={"G1": "2026-06-18T23:00:00+00:00"})
    assert res["status"] == "ok"
    assert res["logged"] == 3
    assert res["skipped"] == 0
    f = tmp_path / "nba" / "2026-06-18.jsonl"
    assert f.exists()
    rows = _read_jsonl(f)
    assert len(rows) == 3
    r0 = rows[0]
    assert r0["sport"] == "nba"
    assert r0["game_id"] == "G1"
    assert r0["market_type"] == "moneyline"
    assert r0["commence_time"] == "2026-06-18T23:00:00+00:00"
    assert r0["odds"] == 1.91


def test_append_only_never_overwrites(tmp_path):
    write_quotes([_quote(captured_at="2026-06-18T18:00:00+00:00")], out_dir=tmp_path)
    write_quotes([_quote(captured_at="2026-06-18T19:00:00+00:00")], out_dir=tmp_path)
    f = tmp_path / "nba" / "2026-06-18.jsonl"
    rows = _read_jsonl(f)
    # Time series: both ticks appended, none overwritten.
    assert len(rows) == 2


def test_bad_row_skipped_never_raises(tmp_path):
    good = _quote(odds=1.91)
    bad_odds = _quote(odds=0.5)           # not a usable decimal price
    res = write_quotes([good, bad_odds], out_dir=tmp_path)
    assert res["status"] == "ok"
    assert res["logged"] == 1
    assert res["skipped"] == 1


def test_never_raises_on_garbage(tmp_path):
    # A non-MarketQuote object is tolerated and skipped, not raised on.
    res = write_quotes([object(), None], out_dir=tmp_path)
    assert res["status"].startswith(("ok", "error"))


def test_date_bucket_falls_back_to_now(tmp_path):
    q = _quote(captured_at="")  # no captured_at -> skipped (needs captured_at)
    res = write_quotes([q], out_dir=tmp_path,
                       now=datetime(2026, 6, 18, tzinfo=timezone.utc))
    assert res["skipped"] == 1


def test_captured_at_suspect_persists_to_row(tmp_path):
    write_quotes([_quote(captured_at_suspect=True)], out_dir=tmp_path)
    rows = _read_jsonl(tmp_path / "nba" / "2026-06-18.jsonl")
    assert rows[0]["captured_at_suspect"] is True


def test_captured_at_suspect_defaults_false(tmp_path):
    write_quotes([_quote()], out_dir=tmp_path)
    rows = _read_jsonl(tmp_path / "nba" / "2026-06-18.jsonl")
    assert rows[0]["captured_at_suspect"] is False
