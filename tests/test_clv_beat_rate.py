"""
tests/test_clv_beat_rate.py — Tests for generate_beat_rate_report().
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

from clv_tracker import generate_beat_rate_report


def _make_entry(bet_id, stat, clv, direction="over", opening=20.0, closing=None):
    if closing is None:
        # derive a closing that yields the desired CLV
        if direction == "over":
            closing = opening * (1 + clv)
        else:
            closing = opening * (1 - clv)
    return {
        "bet_id": bet_id,
        "stat": stat,
        "direction": direction,
        "opening_line": opening,
        "closing_line": closing,
        "edge_pct": 0.05,
        "clv": clv,
    }


def test_report_no_data(tmp_path):
    """Missing log file → report contains 'No CLV log' message."""
    missing_log = tmp_path / "nonexistent_clv_log.json"
    out = generate_beat_rate_report(
        output_dir=str(tmp_path),
        log_path=str(missing_log),
        week="2026-W21",
    )
    content = Path(out).read_text(encoding="utf-8")
    assert "No CLV log" in content


def test_report_empty_log(tmp_path):
    """Empty list log → report contains 'No bets recorded'."""
    log = tmp_path / "clv_log.json"
    log.write_text(json.dumps([]), encoding="utf-8")
    out = generate_beat_rate_report(
        output_dir=str(tmp_path),
        log_path=str(log),
        week="2026-W21",
    )
    content = Path(out).read_text(encoding="utf-8")
    assert "No bets recorded" in content


def test_report_computes_beat_rate(tmp_path):
    """4 entries (2 CLV>0, 2 CLV<0) → beat_rate reported as 50.0%."""
    entries = [
        _make_entry("b1", "pts", clv=0.05),
        _make_entry("b2", "pts", clv=0.10),
        _make_entry("b3", "pts", clv=-0.03),
        _make_entry("b4", "pts", clv=-0.07),
    ]
    log = tmp_path / "clv_log.json"
    log.write_text(json.dumps(entries), encoding="utf-8")
    out = generate_beat_rate_report(
        output_dir=str(tmp_path),
        log_path=str(log),
        week="2026-W21",
    )
    content = Path(out).read_text(encoding="utf-8")
    assert "50.0%" in content
    assert "n=4" in content


def test_report_per_stat(tmp_path):
    """Entries across 2 stats → per-stat section present with both stat names."""
    entries = [
        _make_entry("b1", "pts", clv=0.05),
        _make_entry("b2", "pts", clv=-0.02),
        _make_entry("b3", "reb", clv=0.08),
        _make_entry("b4", "reb", clv=0.03),
    ]
    log = tmp_path / "clv_log.json"
    log.write_text(json.dumps(entries), encoding="utf-8")
    out = generate_beat_rate_report(
        output_dir=str(tmp_path),
        log_path=str(log),
        week="2026-W21",
    )
    content = Path(out).read_text(encoding="utf-8")
    assert "Per-stat breakdown" in content
    assert "pts" in content
    assert "reb" in content


def test_report_week_in_filename(tmp_path):
    """week='2026-W21' → output filename contains '2026-W21'."""
    entries = [_make_entry("b1", "pts", clv=0.05)]
    log = tmp_path / "clv_log.json"
    log.write_text(json.dumps(entries), encoding="utf-8")
    out = generate_beat_rate_report(
        output_dir=str(tmp_path),
        log_path=str(log),
        week="2026-W21",
    )
    assert "2026-W21" in Path(out).name
