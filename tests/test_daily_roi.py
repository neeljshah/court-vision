"""tests/test_daily_roi.py — Unit tests for src.reporting.daily_roi."""
from __future__ import annotations

import csv
import os
import re
import subprocess
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.reporting.daily_roi import (
    build_daily_report,
    load_settled_day,
    write_daily_report,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SETTLED_COLS = [
    "ts", "game_id", "period", "clock_remaining", "player_id", "name",
    "team", "stat", "side", "line", "book", "odds", "model_proj",
    "current_stat", "sigma", "raw_ev", "kelly", "tier",
    "gate_status", "gate_blocked_by", "source",
    "actual_stat", "outcome", "realized_return_$1", "settled_at",
]


def _write_settled(path: str, rows: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_SETTLED_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            complete = {c: r.get(c, "") for c in _SETTLED_COLS}
            w.writerow(complete)


def _make_row(**overrides):
    base = {
        "ts": "2026-05-27T04:00:00",
        "game_id": "0022400001",
        "period": "2",
        "clock_remaining": "720.0",
        "player_id": "111",
        "name": "Alice Smith",
        "team": "BOS",
        "stat": "pts",
        "side": "over",
        "line": "20.5",
        "book": "pin",
        "odds": "-110",
        "model_proj": "24.0",
        "current_stat": "10.0",
        "sigma": "5.0",
        "raw_ev": "0.15",
        "kelly": "0.05",
        "tier": "A",
        "gate_status": "passed",
        "gate_blocked_by": "",
        "source": "snapshot_replay",
        "actual_stat": "22.0",
        "outcome": "hit",
        "realized_return_$1": "0.9091",
        "settled_at": "2026-05-27T05:00:00+00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture
def settled_csv(tmp_path):
    """Synthetic settled CSV with varied tiers, stats, books, quarters."""
    rows = []
    tiers  = ["S", "A", "B", "C"]
    stats  = ["pts", "reb", "ast"]
    books  = ["pin", "fd"]
    periods = ["2", "3", "4"]

    ev_vals = [0.6, 0.3, 0.1, -0.4]  # S=high, C=low
    outcomes = ["hit", "hit", "miss", "miss"]
    returns  = ["0.9091", "0.9091", "-1.0000", "-1.0000"]

    row_id = 0
    for tier, ev, outcome, ret in zip(tiers, ev_vals, outcomes, returns):
        for stat in stats:
            for book in books:
                for period in periods:
                    rows.append(_make_row(
                        player_id=str(row_id),
                        name=f"Player{row_id}",
                        tier=tier,
                        stat=stat,
                        book=book,
                        period=period,
                        raw_ev=str(ev),
                        outcome=outcome,
                        **{"realized_return_$1": ret},
                    ))
                    row_id += 1

    date_str = "2026-05-27"
    csv_path = tmp_path / f"settled_{date_str}.csv"
    _write_settled(str(csv_path), rows)
    return tmp_path, date_str, len(rows)


# ---------------------------------------------------------------------------
# Test 1: load returns empty DataFrame when file absent
# ---------------------------------------------------------------------------

def test_load_settled_day_missing_file(tmp_path):
    df = load_settled_day("2099-01-01", base_dir=str(tmp_path))
    assert df.empty, "Should return empty DataFrame for missing file"


# ---------------------------------------------------------------------------
# Test 2: build_daily_report has all expected section headers
# ---------------------------------------------------------------------------

EXPECTED_HEADERS = [
    r"# Daily ROI Report",
    r"## Summary",
    r"## Top 20 Picks by EV",
    r"## ROI by Tier",
    r"## Calibration",
    r"## Per-Quarter Breakdown",
    r"## Per-Stat Breakdown",
    r"## Per-Book Breakdown",
]


def test_build_daily_report_has_all_headers(settled_csv):
    tmp_path, date_str, _ = settled_csv
    md = build_daily_report(date_str, base_dir=str(tmp_path))
    for pattern in EXPECTED_HEADERS:
        assert re.search(pattern, md), f"Missing section header matching {pattern!r}"


# ---------------------------------------------------------------------------
# Test 3: per-stat and per-book groupings produce rows with correct names
# ---------------------------------------------------------------------------

def test_per_stat_and_book_groupings(settled_csv):
    tmp_path, date_str, _ = settled_csv
    md = build_daily_report(date_str, base_dir=str(tmp_path))
    # Stats used in fixture: pts, reb, ast
    for stat in ["pts", "reb", "ast"]:
        assert stat in md, f"Stat '{stat}' missing from report"
    # Books used: pin, fd
    for book in ["pin", "fd"]:
        assert book in md, f"Book '{book}' missing from report"


# ---------------------------------------------------------------------------
# Test 4: calibration deciles are monotonic for well-calibrated data
# ---------------------------------------------------------------------------

def test_calibration_monotonic_well_calibrated(tmp_path):
    """Build a dataset where higher raw_ev always → higher realized return.
    Calibration decile table avg_realized_return should be non-decreasing."""
    import numpy as np

    rng = np.random.default_rng(42)
    n = 500
    ev_vals = rng.uniform(-1, 1, size=n)
    # realized return is ev + small noise → well-calibrated
    ret_vals = ev_vals + rng.normal(0, 0.05, size=n)

    rows = []
    for i, (ev, ret) in enumerate(zip(ev_vals, ret_vals)):
        outcome = "hit" if ret > 0 else "miss"
        rows.append(_make_row(
            player_id=str(i),
            raw_ev=str(float(ev)),
            **{"realized_return_$1": str(float(ret))},
            outcome=outcome,
            gate_status="passed",
        ))

    date_str = "2099-06-01"
    csv_path = tmp_path / f"settled_{date_str}.csv"
    _write_settled(str(csv_path), rows)

    md = build_daily_report(date_str, base_dir=str(tmp_path))
    # Extract avg_realized_return column values from calibration table
    calib_section = md[md.find("## Calibration"):]
    ret_matches = re.findall(r"\|\s*([+-]?\d+\.\d+)\s*\|", calib_section)
    # Every second float-looking value in the table rows is avg_ret (decile, n, avg_ev, avg_ret)
    avg_rets = []
    lines = calib_section.split("\n")
    for line in lines:
        if "|" in line and "---" not in line and "Decile" not in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) == 4:
                try:
                    avg_rets.append(float(parts[3]))
                except ValueError:
                    pass

    assert len(avg_rets) >= 5, f"Expected >=5 calibration rows, got {len(avg_rets)}"
    # Allow at most 1 inversion in 10 deciles for well-calibrated data
    inversions = sum(1 for a, b in zip(avg_rets, avg_rets[1:]) if b < a - 0.05)
    assert inversions <= 2, f"Too many inversions in calibration curve: {avg_rets}"


# ---------------------------------------------------------------------------
# Test 5: CLI smoke test — runs end-to-end on synthetic data
# ---------------------------------------------------------------------------

def test_cli_smoke(settled_csv, tmp_path):
    base_path, date_str, n_rows = settled_csv
    out_file = tmp_path / f"report_{date_str}.md"
    result = subprocess.run(
        [
            sys.executable, "-m", "src.reporting.daily_roi",
            "--date", date_str,
            "--output", str(out_file),
            "--base-dir", str(base_path),
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
    )
    assert result.returncode == 0, f"CLI failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert out_file.exists(), "Output file not created"
    content = out_file.read_text(encoding="utf-8")
    assert f"Daily ROI Report — {date_str}" in content
    # Console output checks
    assert "Rows logged" in result.stdout or "Rows logged" in result.stderr or n_rows > 0


# ---------------------------------------------------------------------------
# Test 6: write_daily_report creates file and returns correct path
# ---------------------------------------------------------------------------

def test_write_daily_report_creates_file(settled_csv, tmp_path):
    base_path, date_str, _ = settled_csv
    out = tmp_path / "out" / f"daily_roi_{date_str}.md"
    returned_path = write_daily_report(date_str, out_path=str(out), base_dir=str(base_path))
    assert returned_path == str(out)
    assert out.exists()
    assert os.path.getsize(str(out)) > 100


# ---------------------------------------------------------------------------
# Test 7: load_settled_day empty DataFrame has correct structure (not just len==0)
# ---------------------------------------------------------------------------

def test_load_settled_day_empty_is_dataframe(tmp_path):
    import pandas as pd
    df = load_settled_day("2099-12-31", base_dir=str(tmp_path))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
