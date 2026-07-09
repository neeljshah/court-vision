"""Per-file test for disk_space. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_disk_space.py -q
"""
from __future__ import annotations

import os
from collections import namedtuple
from pathlib import Path

from scripts.platformkit.ops_sentinel import disk_space as ds

_Usage = namedtuple("usage", "total used free")


def _table(tmp_path: Path, cadence: float = 600.0):
    d = tmp_path / "capture"
    d.mkdir()
    return d, {"capture": ds._Dir(d, cadence)}


def test_free_gb_thresholds():
    red = ds.check_free_gb(usage_fn=lambda p: _Usage(1, 1, 2e9))
    yel = ds.check_free_gb(usage_fn=lambda p: _Usage(1, 1, 10e9))
    grn = ds.check_free_gb(usage_fn=lambda p: _Usage(1, 1, 100e9))
    assert (red["status"], yel["status"], grn["status"]) == ("RED", "YELLOW", "GREEN")


def test_stall_red_only_inside_slate(tmp_path):
    d, table = _table(tmp_path)
    f = d / "x.jsonl"
    f.write_text("row")
    now = os.stat(f).st_mtime + 5000.0  # 5000s > 2x600s cadence

    rows = ds.check_all(now=now, table=table, slate_fn=lambda t: True,
                        usage_fn=lambda p: _Usage(1, 1, 100e9))
    by = {r["name"]: r for r in rows}
    assert by["capture"]["status"] == "RED"
    assert by["capture"]["reason"] == "growth_stalled"

    rows = ds.check_all(now=now, table=table, slate_fn=lambda t: False,
                        usage_fn=lambda p: _Usage(1, 1, 100e9))
    assert {r["name"]: r for r in rows}["capture"]["status"] == "IDLE"


def test_fresh_dir_green_and_missing_dir_red(tmp_path):
    d, table = _table(tmp_path)
    sub = d / "mlb"
    sub.mkdir()
    f = sub / "y.jsonl"
    f.write_text("row")
    now = os.stat(f).st_mtime + 100.0  # well within 2x cadence
    table["gone"] = ds._Dir(tmp_path / "does_not_exist", 600.0)
    rows = ds.check_all(now=now, table=table, slate_fn=lambda t: True,
                        usage_fn=lambda p: _Usage(1, 1, 100e9))
    by = {r["name"]: r for r in rows}
    assert by["capture"]["status"] == "GREEN"     # recursive newest-mtime seen
    assert by["gone"]["status"] == "RED" and by["gone"]["reason"] == "missing_dir"


def test_empty_dir_in_slate_is_red(tmp_path):
    _d, table = _table(tmp_path)
    rows = ds.check_all(now=1e9, table=table, slate_fn=lambda t: True,
                        usage_fn=lambda p: _Usage(1, 1, 100e9))
    assert {r["name"]: r for r in rows}["capture"]["status"] == "RED"


def test_real_table_dirs_mostly_exist():
    # 5 key dirs are registered; each path is under the repo data tree
    assert set(ds.TABLE) == {"gumbo_live", "ingame_grade", "ingame_grade_joined",
                             "kalshi_trades", "line_history"}
    missing = [n for n, e in ds.TABLE.items() if not e.path.exists()]
    assert missing == [], "registered capture dirs absent: %s" % missing
