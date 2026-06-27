"""Per-file test for pm_paper_tick_runner -- supervised M12 daemon (W11).

NO full pytest. Run only this file:
  cd /c/Users/neelj/nba-ai-system &&
  python -m pytest tests/platformkit/test_pm_paper_tick_runner.py -q
"""
from __future__ import annotations

import json
import pathlib

from scripts.platformkit.pm_trading import pm_paper_tick_runner as r


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _no_sleep(s):
    pass


def _make_pairs(*pairs):
    return lambda now: list(pairs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bounded_run_stops_at_max_ticks(tmp_path):
    """run() with max_ticks=3 executes exactly 3 ticks."""
    n = r.run(capture_fn=lambda now: [],
              pm_dir=tmp_path,
              clock=lambda: 1.0, sleep=_no_sleep, max_ticks=3)
    assert n == 3


def test_heartbeat_at_boot_and_per_tick(monkeypatch, tmp_path):
    """Heartbeat advanced at boot + after each tick."""
    beats = []
    monkeypatch.setattr(r, "_beat", lambda now=None: beats.append(now))
    r.run(capture_fn=lambda now: [],
          pm_dir=tmp_path,
          clock=lambda: 7.0, sleep=_no_sleep, max_ticks=2)
    assert len(beats) == 3
    assert 7.0 in beats


def test_pairs_written_to_jsonl(tmp_path):
    """Pairs are appended to per-market JSONL files."""
    pairs = [
        {"market_id": "NBA_GM1_OU", "market_prob": 0.52, "model_prob": 0.55,
         "units": 0.5, "tier": "B", "clv_status": "INSUFFICIENT_DATA"},
        {"market_id": "NBA_GM1_OU", "market_prob": 0.51, "model_prob": 0.54,
         "units": 0.4, "tier": "B", "clv_status": "INSUFFICIENT_DATA"},
        {"market_id": "NBA_GM2_ML", "market_prob": 0.60, "model_prob": 0.62,
         "units": 0.3, "tier": "C", "clv_status": "INSUFFICIENT_DATA"},
    ]
    written = r.tick(now=999.0, capture_fn=lambda now: pairs, pm_dir=tmp_path)
    assert "NBA_GM1_OU" in written
    assert "NBA_GM2_ML" in written
    f1 = tmp_path / "NBA_GM1_OU.jsonl"
    assert f1.exists()
    lines = [l for l in f1.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(lines) == 2
    row = json.loads(lines[0])
    # UNITS not $: no dollar P&L field
    assert "dollar_pnl" not in row
    assert "pnl_usd" not in row


def test_no_dollar_pnl_in_output(tmp_path):
    """capture_fn rows with dollar_pnl stripped before writing."""
    pairs = [{"market_id": "MKT1", "dollar_pnl": 50.0, "model_prob": 0.6,
              "units": 1.0}]
    r.tick(now=1.0, capture_fn=lambda now: pairs, pm_dir=tmp_path)
    f = tmp_path / "MKT1.jsonl"
    if f.exists():
        raw = f.read_text(encoding="ascii")
        assert "dollar_pnl" not in raw


def test_capture_fn_raise_does_not_crash(tmp_path):
    """A raising capture_fn leaves written=[] but loop continues."""
    def _boom(now):
        raise ConnectionError("no PM feed")

    n = r.run(capture_fn=_boom,
              pm_dir=tmp_path,
              clock=lambda: 0.0, sleep=_no_sleep, max_ticks=2)
    assert n == 2


def test_append_is_cumulative(tmp_path):
    """Two ticks to the same market accumulate rows (append, not overwrite)."""
    pairs_a = [{"market_id": "MKT_X", "model_prob": 0.6, "units": 0.5}]
    pairs_b = [{"market_id": "MKT_X", "model_prob": 0.62, "units": 0.5}]
    r.tick(now=1.0, capture_fn=lambda now: pairs_a, pm_dir=tmp_path)
    r.tick(now=2.0, capture_fn=lambda now: pairs_b, pm_dir=tmp_path)
    f = tmp_path / "MKT_X.jsonl"
    lines = [l for l in f.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(lines) == 2


def test_empty_pairs_no_file_created(tmp_path):
    """When capture_fn returns [], no JSONL file is created."""
    r.tick(now=1.0, capture_fn=lambda now: [], pm_dir=tmp_path)
    jsonl_files = list(tmp_path.glob("*.jsonl"))
    assert jsonl_files == []


def test_pm_filter_market_id_grouping(tmp_path):
    """Rows group correctly by market_id into separate files."""
    pairs = [
        {"market_id": "KALSHI_A", "units": 0.5},
        {"market_id": "PM_B", "units": 0.3},
        {"market_id": "KALSHI_A", "units": 0.2},
    ]
    r.tick(now=3.0, capture_fn=lambda now: pairs, pm_dir=tmp_path)
    assert (tmp_path / "KALSHI_A.jsonl").exists()
    assert (tmp_path / "PM_B.jsonl").exists()
    lines_a = [l for l in (tmp_path / "KALSHI_A.jsonl")
               .read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(lines_a) == 2


def test_should_stop_halts_loop(tmp_path):
    calls = {"n": 0}

    def _stop():
        calls["n"] += 1
        return calls["n"] >= 2

    n = r.run(capture_fn=lambda now: [],
              pm_dir=tmp_path,
              clock=lambda: 0.0, sleep=_no_sleep,
              should_stop=_stop, max_ticks=99)
    assert n == 1


if __name__ == "__main__":
    import sys, tempfile
    td = pathlib.Path(tempfile.mkdtemp())
    test_pairs_written_to_jsonl(td)
    print("ok: pairs_written")
    test_append_is_cumulative(td)
    print("ok: append_cumulative")
    sys.exit(0)
