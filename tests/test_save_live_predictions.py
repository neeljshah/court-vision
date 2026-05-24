"""Tests for scripts/save_live_predictions.py (cycle 88n)."""
from __future__ import annotations

import csv
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.save_live_predictions as slp  # noqa: E402


def _snapshot(period=2, clock="6:00", home_score=50, away_score=50,
              home_team="OKC", away_team="SAS", players=None):
    return {
        "game_id": "0022400123",
        "captured_at": "2026-05-24T19:42:00",
        "game_status": "LIVE",
        "period": period, "clock": clock,
        "home_score": home_score, "away_score": away_score,
        "home_team": home_team, "away_team": away_team,
        "players": players if players is not None else [],
    }


def _player(name, team, pid=1, is_starter=True, **stats):
    base = {"name": name, "player_id": pid, "team": team,
            "is_starter": is_starter, "min": 18.0, "pf": 1,
            "pts": 12, "reb": 4, "ast": 3, "fg3m": 1, "stl": 1, "blk": 0, "tov": 1}
    base.update(stats)
    return base


# ── derive_inplay_predictions ─────────────────────────────────────────────

def test_derive_emits_7_rows_per_player():
    snap = _snapshot(players=[
        _player("Player A", "OKC"),
        _player("Player B", "SAS", pid=2),
    ])
    rows = slp.derive_inplay_predictions(snap, "2026-05-24")
    assert len(rows) == 14    # 2 players * 7 stats
    assert {r["stat"] for r in rows} == set(slp.STATS)


def test_derive_includes_current_stat_alongside_projection():
    """Critical for future analysis: we need to know what the actual was
    AT THE TIME of the prediction to measure projection-vs-actual MAE later."""
    snap = _snapshot(players=[_player("X. Player", "OKC", pts=15)])
    rows = slp.derive_inplay_predictions(snap, "2026-05-24")
    pts_row = next(r for r in rows if r["stat"] == "pts")
    assert pts_row["current_stat"] == "15.0000"
    # Projection ~40 (Q2 6:00 -> 37.5% played)
    assert abs(float(pts_row["pred"]) - 40.0) < 0.5


def test_derive_marks_lineup_class_starter_vs_bench():
    snap = _snapshot(players=[
        _player("Starter", "OKC", is_starter=True),
        _player("Bencher", "OKC", pid=2, is_starter=False),
    ])
    rows = slp.derive_inplay_predictions(snap, "2026-05-24")
    starter_pts = next(r for r in rows
                        if r["player"] == "Starter" and r["stat"] == "pts")
    bench_pts = next(r for r in rows
                      if r["player"] == "Bencher" and r["stat"] == "pts")
    assert starter_pts["lineup_class"] == "starter"
    assert bench_pts["lineup_class"] == "bench"


def test_derive_sets_correct_opp_and_venue():
    """Player on home team has the away team as opp and venue=home."""
    snap = _snapshot(home_team="LAL", away_team="DEN", players=[
        _player("LAL Player", "LAL", is_starter=True),
        _player("DEN Player", "DEN", pid=2, is_starter=True),
    ])
    rows = slp.derive_inplay_predictions(snap, "2026-05-24")
    lal_row = next(r for r in rows if r["player"] == "LAL Player" and r["stat"] == "pts")
    den_row = next(r for r in rows if r["player"] == "DEN Player" and r["stat"] == "pts")
    assert lal_row["opp"] == "DEN" and lal_row["venue"] == "home"
    assert den_row["opp"] == "LAL" and den_row["venue"] == "away"


def test_derive_includes_pred_kind_with_period():
    snap = _snapshot(period=3, clock="5:00", players=[_player("X", "OKC")])
    rows = slp.derive_inplay_predictions(snap, "2026-05-24")
    assert rows[0]["pred_kind"].startswith("Q3_inplay_")


def test_derive_pred_kind_override():
    snap = _snapshot(players=[_player("X", "OKC")])
    rows = slp.derive_inplay_predictions(snap, "2026-05-24",
                                            override_kind="manual_check")
    assert all(r["pred_kind"] == "manual_check" for r in rows)


def test_derive_skips_players_with_no_name():
    snap = _snapshot(players=[
        _player("", "OKC", is_starter=True),
        _player("Real Player", "OKC", pid=2),
    ])
    rows = slp.derive_inplay_predictions(snap, "2026-05-24")
    assert len({r["player"] for r in rows}) == 1
    assert rows[0]["player"] == "Real Player"


def test_derive_applies_foul_trouble_factor():
    """Player with 5 fouls in Q3 should have a much lower projection than
    the same player with 0 fouls (cycle 88e factor table)."""
    snap_clean = _snapshot(period=3, clock="6:00", players=[
        _player("Clean", "OKC", pts=18, pf=1),
    ])
    snap_trouble = _snapshot(period=3, clock="6:00", players=[
        _player("InTrouble", "OKC", pts=18, pf=5),
    ])
    clean = slp.derive_inplay_predictions(snap_clean, "2026-05-24")
    trouble = slp.derive_inplay_predictions(snap_trouble, "2026-05-24")
    clean_pts = float(next(r for r in clean if r["stat"] == "pts")["pred"])
    trouble_pts = float(next(r for r in trouble if r["stat"] == "pts")["pred"])
    assert trouble_pts < clean_pts


# ── append_to_ledger ────────────────────────────────────────────────────

def test_append_writes_header_then_rows_on_new_file():
    snap = _snapshot(players=[_player("X", "OKC")])
    rows = slp.derive_inplay_predictions(snap, "2026-05-24")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "inplay.csv")
        n = slp.append_to_ledger(rows, path)
        assert n == 7
        with open(path) as fh:
            reader = csv.DictReader(fh)
            saved = list(reader)
        assert len(saved) == 7
        assert "pred_kind" in saved[0]
        assert "snapshot_period" in saved[0]
        assert "current_stat" in saved[0]


def test_append_does_not_rewrite_header_on_existing_file():
    snap = _snapshot(players=[_player("X", "OKC")])
    rows = slp.derive_inplay_predictions(snap, "2026-05-24")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "inplay.csv")
        slp.append_to_ledger(rows, path)
        slp.append_to_ledger(rows, path)
        with open(path) as fh:
            content = fh.read().strip().splitlines()
        # 1 header + 14 rows (7 * 2 appends)
        assert len(content) == 15
        for line in content[1:]:
            assert not line.startswith("date,")


def test_append_creates_parent_dir():
    snap = _snapshot(players=[_player("X", "OKC")])
    rows = slp.derive_inplay_predictions(snap, "2026-05-24")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "deep", "nested", "inplay.csv")
        slp.append_to_ledger(rows, path)
        assert os.path.exists(path)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
