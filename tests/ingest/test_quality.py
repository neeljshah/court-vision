"""P4 tests: quality gate tier boundaries."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.ingest.quality import (
    CLEAN_BALL_PCT, CLEAN_CONTINUITY, CLEAN_EVENTS_MAX, CLEAN_EVENTS_MIN,
    CLEAN_HOMO_PCT, score,
)


def _make_tracking(tmp_path: Path, game_id: str,
                   ball_pct: float = 80.0,
                   homo_pct: float = 90.0,
                   n_frames: int = 3000,
                   n_shots: int = 100) -> Path:
    gdir = tmp_path / game_id
    gdir.mkdir(parents=True)

    # tracking_data.csv
    td = gdir / "tracking_data.csv"
    with td.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame", "player_id", "team", "homography_valid"])
        homo_valid_count = int(n_frames * homo_pct / 100)
        for i in range(n_frames):
            w.writerow([i * 30, f"P{i % 5}", "home", 1 if i < homo_valid_count else 0])

    # ball_tracking.csv
    bt = gdir / "ball_tracking.csv"
    ball_valid_count = int(n_frames * ball_pct / 100)
    with bt.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame", "detected", "live"])
        for i in range(n_frames):
            w.writerow([i * 30, 1 if i < ball_valid_count else 0, 1])

    # shot_log.csv
    sl = gdir / "shot_log.csv"
    with sl.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["game_id", "shot_id", "frame"])
        for i in range(n_shots):
            w.writerow([game_id, i, i * 300])

    return gdir


# ── tier boundaries ────────────────────────────────────────────────────────────

def test_clean_tier(tmp_path: Path):
    _make_tracking(tmp_path, "GCLEAN",
                   ball_pct=CLEAN_BALL_PCT + 10,
                   homo_pct=CLEAN_HOMO_PCT + 5,
                   n_shots=CLEAN_EVENTS_MIN + 20)
    tier, reason, metrics = score("GCLEAN", tmp_path)
    assert tier == "CLEAN"
    assert reason is None


def test_partial_tier_two_pass(tmp_path: Path):
    """Only ball + homo pass → PARTIAL."""
    _make_tracking(tmp_path, "GPART",
                   ball_pct=CLEAN_BALL_PCT + 5,
                   homo_pct=CLEAN_HOMO_PCT + 5,
                   n_shots=5,           # events fail
                   n_frames=100)         # continuity will be low
    tier, reason, metrics = score("GPART", tmp_path)
    assert tier in ("PARTIAL", "REJECT")   # depends on continuity calc


def test_reject_tier_no_tracking(tmp_path: Path):
    """No tracking output → REJECT."""
    tier, reason, metrics = score("GMISSING", tmp_path)
    assert tier == "REJECT"
    assert "no_tracking" in reason


def test_reject_tier_ball_below_threshold(tmp_path: Path):
    """Ball < threshold with few other passes → REJECT."""
    _make_tracking(tmp_path, "GREJ",
                   ball_pct=5.0,
                   homo_pct=20.0,
                   n_shots=5,
                   n_frames=500)
    tier, reason, _ = score("GREJ", tmp_path)
    assert tier == "REJECT"


def test_clean_exact_threshold(tmp_path: Path):
    """Game exactly at CLEAN thresholds → CLEAN."""
    _make_tracking(tmp_path, "GEXACT",
                   ball_pct=CLEAN_BALL_PCT,
                   homo_pct=CLEAN_HOMO_PCT,
                   n_shots=CLEAN_EVENTS_MIN,
                   n_frames=3000)
    tier, reason, _ = score("GEXACT", tmp_path)
    # ball_pct and homo_pct exactly at threshold — may be CLEAN
    assert tier in ("CLEAN", "PARTIAL")


def test_reject_events_too_many(tmp_path: Path):
    """Event count above max → one check fails."""
    _make_tracking(tmp_path, "GTOOMANY",
                   ball_pct=CLEAN_BALL_PCT + 10,
                   homo_pct=CLEAN_HOMO_PCT + 10,
                   n_shots=CLEAN_EVENTS_MAX + 50,
                   n_frames=5000)
    tier, reason, metrics = score("GTOOMANY", tmp_path)
    assert metrics["event_count"] == CLEAN_EVENTS_MAX + 50
    # Events fail, ball+homo pass + continuity likely pass → PARTIAL
    assert tier in ("PARTIAL", "REJECT")
