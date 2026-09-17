"""The daily CLV readout must age off the REAL clock, not a frozen literal.

Defect 4 (execution readiness audit 2026-09-17): clv_daily_readout.main() pinned
now_iso to "2026-09-03T00:00:00+00:00" and write_readout stamped
staleness_days=0 unconditionally, so the artifact asserted it was current no
matter how old its newest settled row was.

Run: python -m pytest tests/platformkit/pm_trading/test_clv_daily_readout_clock.py -q
"""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta, timezone

from scripts.platformkit.pm_trading import clv_daily_readout as m

_NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def _ledger(tmp_path, settled_at):
    path = tmp_path / "clv_ledger.jsonl"
    rows = [{"channel": "paper_ingame", "market": "win_home", "status": "settled",
             "outcome": "win", "clv_units": 0.01, "maker_fee_units": 0.01,
             "taken_book": "paper_ingame_maker", "venue": "kalshi",
             "settled_at": settled_at} for _ in range(9)]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def _run(tmp_path, settled_at, now=_NOW):
    return m.write_readout(_ledger(tmp_path, settled_at), tmp_path / "out.json",
                           tmp_path / "memo.md", now_iso=now.isoformat())


def test_old_last_row_reports_its_real_age(tmp_path):
    doc = _run(tmp_path, (_NOW - timedelta(days=45)).isoformat())
    assert doc["status"] == "ok"
    assert 44.9 < doc["staleness_days"] < 45.1


def test_fresh_last_row_is_not_stale(tmp_path):
    doc = _run(tmp_path, (_NOW - timedelta(hours=2)).isoformat())
    assert doc["staleness_days"] < 1.0


def test_z_suffixed_timestamp_still_parses(tmp_path):
    # Py3.10's datetime.fromisoformat has no native Z support; the readout must
    # still date a Z-stamped ledger row rather than falling back to INSUFFICIENT.
    doc = _run(tmp_path, "2026-08-18T12:00:00Z")
    assert 30.0 - 0.1 < doc["staleness_days"] < 30.0 + 0.1


def test_unparseable_as_of_is_insufficient_never_zero(tmp_path):
    doc = _run(tmp_path, "not-a-timestamp")
    assert doc["staleness_days"] == "INSUFFICIENT"


def test_default_now_is_the_real_clock(tmp_path):
    before = datetime.now(timezone.utc)
    doc = m.write_readout(_ledger(tmp_path, (before - timedelta(days=3)).isoformat()),
                          tmp_path / "out.json", tmp_path / "memo.md")
    assert 2.9 < doc["staleness_days"] < 3.1
    assert m._parse_iso(doc["generated_at"]) >= before


def test_cli_entry_point_carries_no_frozen_clock():
    assert "2026-09-03" not in inspect.getsource(m.main)
