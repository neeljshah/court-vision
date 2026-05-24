"""Tests for scripts/probe_inplay_vs_pregame.py (cycle 89e, loop 5).

The script is the retrospective harness that compares the cycle-88n in-play
predictions to the cycle-47/49/80 pre-game predictions. These tests pin its
behaviour in the (currently empty) pre-data world AND the future populated
world via small synthetic fixtures, so the harness can ship before any
real in-play data has accumulated.
"""
from __future__ import annotations

import csv
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.probe_inplay_vs_pregame as probe  # noqa: E402


# ── fixtures ──────────────────────────────────────────────────────────────

_PRE_FIELDS = ["date", "game_id", "player_id", "player", "team", "opp",
               "venue", "stat", "pred"]
_INPLAY_FIELDS = _PRE_FIELDS + ["lineup_status", "lineup_class", "play_pct",
                                  "injury_status", "pred_kind",
                                  "snapshot_period", "snapshot_clock",
                                  "current_stat"]


def _write_csv(path: str, fieldnames, rows) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _pregame_row(pid, stat, pred, date="2026-05-24"):
    return {"date": date, "game_id": "0022400123", "player_id": str(pid),
            "player": f"P{pid}", "team": "OKC", "opp": "SAS", "venue": "home",
            "stat": stat, "pred": f"{pred:.4f}"}


def _inplay_row(pid, stat, pred, kind="Q2_inplay_1942", date="2026-05-24"):
    return {"date": date, "game_id": "0022400123", "player_id": str(pid),
            "player": f"P{pid}", "team": "OKC", "opp": "SAS", "venue": "home",
            "stat": stat, "pred": f"{pred:.4f}",
            "lineup_status": "", "lineup_class": "starter", "play_pct": "",
            "injury_status": "", "pred_kind": kind,
            "snapshot_period": "2", "snapshot_clock": "6:00",
            "current_stat": "10.0000"}


# ── tests ─────────────────────────────────────────────────────────────────

def test_no_inplay_file_writes_graceful_md(tmp_path, capsys):
    """The most important pre-data test: with no <date>_inplay.csv yet, the
    script must NOT crash and must write a 'framework operational' report."""
    pred_dir = tmp_path / "predictions"
    pred_dir.mkdir()
    _write_csv(str(pred_dir / "2026-05-24.csv"), _PRE_FIELDS,
                [_pregame_row(1, "pts", 25.0)])
    out_md = tmp_path / "report.md"

    rc = probe.run("2026-05-24", str(out_md), pred_dir=str(pred_dir),
                    actuals_loader=lambda d: {})

    assert rc == 0
    captured = capsys.readouterr()
    assert "NO INPLAY DATA YET" in captured.out
    content = out_md.read_text(encoding="utf-8")
    assert "NO INPLAY DATA YET" in content
    assert "Framework is operational" in content


def test_missing_pregame_file_returns_1(tmp_path, capsys):
    pred_dir = tmp_path / "predictions"
    pred_dir.mkdir()
    out_md = tmp_path / "report.md"

    rc = probe.run("2026-05-24", str(out_md), pred_dir=str(pred_dir),
                    actuals_loader=lambda d: {})

    assert rc == 1
    captured = capsys.readouterr()
    assert "no pregame ledger" in captured.out
    # Don't write a stale markdown when the pregame ledger is missing.
    assert not out_md.exists()


def test_mae_by_pred_kind_computed_correctly(tmp_path):
    """Synthetic fixtures with known errors so we can sanity-check MAE math."""
    pred_dir = tmp_path / "predictions"
    pred_dir.mkdir()

    # Pre-game: predict 25 pts for P1 and 8 reb for P2 (errors 5.0 and 2.0 vs actuals).
    _write_csv(str(pred_dir / "2026-05-24.csv"), _PRE_FIELDS, [
        _pregame_row(1, "pts", 25.0),
        _pregame_row(2, "reb", 8.0),
    ])
    # In-play Q2: predict 22 pts (error 2.0) and 7 reb (error 1.0).
    # In-play Q3: predict 21 pts (error 1.0) — should be the winner for pts.
    _write_csv(str(pred_dir / "2026-05-24_inplay.csv"), _INPLAY_FIELDS, [
        _inplay_row(1, "pts", 22.0, kind="Q2_inplay_1942"),
        _inplay_row(2, "reb", 7.0, kind="Q2_inplay_1942"),
        _inplay_row(1, "pts", 21.0, kind="Q3_inplay_2010"),
    ])
    actuals = {("1", "pts"): 20.0, ("2", "reb"): 6.0}
    out_md = tmp_path / "report.md"

    rc = probe.run("2026-05-24", str(out_md), pred_dir=str(pred_dir),
                    actuals_loader=lambda d: actuals)

    assert rc == 0
    md = out_md.read_text(encoding="utf-8")
    # Pregame pts MAE = 5.0; Q2 = 2.0; Q3 = 1.0 → Q3_inplay wins.
    assert "5.0000" in md       # pregame_mae pts
    assert "2.0000" in md       # Q2_inplay pts mae
    assert "1.0000" in md       # Q3_inplay pts mae
    # Best should be Q3_inplay for pts and Q2_inplay for reb.
    pts_line = [l for l in md.splitlines() if l.startswith("| pts ")][0]
    assert pts_line.endswith("Q3_inplay |")
    reb_line = [l for l in md.splitlines() if l.startswith("| reb ")][0]
    assert reb_line.endswith("Q2_inplay |")


def test_missing_actuals_excluded_from_mae(tmp_path):
    """If an actual is missing for a (player, stat), it must NOT count toward MAE."""
    pred_dir = tmp_path / "predictions"
    pred_dir.mkdir()
    _write_csv(str(pred_dir / "2026-05-24.csv"), _PRE_FIELDS, [
        _pregame_row(1, "pts", 25.0),
        _pregame_row(2, "pts", 30.0),    # actual missing
        _pregame_row(3, "pts", 18.0),
    ])
    _write_csv(str(pred_dir / "2026-05-24_inplay.csv"), _INPLAY_FIELDS, [
        _inplay_row(1, "pts", 24.0),
        _inplay_row(2, "pts", 27.0),     # actual missing
        _inplay_row(3, "pts", 17.0),
    ])
    actuals = {("1", "pts"): 22.0, ("3", "pts"): 20.0}  # P2 missing
    out_md = tmp_path / "report.md"

    rc = probe.run("2026-05-24", str(out_md), pred_dir=str(pred_dir),
                    actuals_loader=lambda d: actuals)

    assert rc == 0
    md = out_md.read_text(encoding="utf-8")
    # n should be 2 (P1 and P3, not P2) and pregame MAE = (3 + 2) / 2 = 2.5
    assert "| pts | 2 | 2.5000" in md


def test_median_used_across_multiple_inplay_snapshots(tmp_path):
    """3 Q2_inplay snapshots with different timestamps must collapse to MEDIAN."""
    pred_dir = tmp_path / "predictions"
    pred_dir.mkdir()
    _write_csv(str(pred_dir / "2026-05-24.csv"), _PRE_FIELDS, [
        _pregame_row(1, "pts", 25.0),
    ])
    # Three Q2 snapshots: 18, 22, 30 → median 22. Actual = 20 → MAE = 2.0.
    # Mean would be 23.33 → MAE = 3.33, so the test discriminates.
    _write_csv(str(pred_dir / "2026-05-24_inplay.csv"), _INPLAY_FIELDS, [
        _inplay_row(1, "pts", 18.0, kind="Q2_inplay_1900"),
        _inplay_row(1, "pts", 22.0, kind="Q2_inplay_1915"),
        _inplay_row(1, "pts", 30.0, kind="Q2_inplay_1930"),
    ])
    actuals = {("1", "pts"): 20.0}
    out_md = tmp_path / "report.md"

    rc = probe.run("2026-05-24", str(out_md), pred_dir=str(pred_dir),
                    actuals_loader=lambda d: actuals)

    assert rc == 0
    md = out_md.read_text(encoding="utf-8")
    # The Q2_inplay MAE cell should be 2.0000 (median path), not 3.33 (mean).
    assert "2.0000 (n=1)" in md
    assert "3.3" not in md


# ── helper tests ──────────────────────────────────────────────────────────

def test_normalise_kind_strips_hhmm():
    assert probe._normalise_kind("Q2_inplay_1942") == "Q2_inplay"
    assert probe._normalise_kind("Q4_inplay_0030") == "Q4_inplay"
    # Non-timestamped tags pass through untouched.
    assert probe._normalise_kind("manual_check") == "manual_check"
    assert probe._normalise_kind("pregame") == "pregame"


def test_actuals_map_from_rows_filters_by_date():
    rows = [
        {"date": "2026-05-24", "player_id": "1",
         "target_pts": 25.0, "target_reb": 7.0},
        {"date": "2026-05-23", "player_id": "1",      # wrong date — excluded
         "target_pts": 20.0, "target_reb": 5.0},
    ]
    out = probe.actuals_map_from_rows(rows, "2026-05-24")
    assert out[("1", "pts")] == 25.0
    assert out[("1", "reb")] == 7.0
    assert ("1", "pts") in out and len([k for k in out if k[1] == "pts"]) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
