"""
tests/cv/test_quality_metrics.py — CV tracking quality scoring tests.

Tests score_tracking_json() against the cv-quality-auditor thresholds:
  ball_valid_pct    < 0.30 → CRITICAL
  avg_players       < 6.0  → CRITICAL
  homography_stab   < 0.80 → CRITICAL
  avg_fps           < 15.0 → CRITICAL
  re_id_match_rate  < 0.70 → CRITICAL
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.tracking.cv_quality import (
    CRITICAL_AVG_FPS,
    CRITICAL_AVG_PLAYERS,
    CRITICAL_BALL_VALID_PCT,
    CRITICAL_HOMOGRAPHY_STAB,
    CRITICAL_REID_MATCH_RATE,
    audit_game_dir,
    score_tracking_json,
)


def _healthy_tracking() -> dict:
    return {
        "ball_valid_pct": 0.75,
        "avg_players_detected": 8.5,
        "homography_stability": 0.92,
        "avg_fps": 22.0,
        "re_id_match_rate": 0.85,
    }


# ── healthy game ──────────────────────────────────────────────────────────────

def test_healthy_tracking_passes() -> None:
    """All metrics above thresholds → overall_ok=True, no critical flags."""
    result = score_tracking_json(_healthy_tracking(), game_id="game_001")
    assert result.overall_ok is True
    assert result.needs_reprocess is False
    assert len(result.critical_flags) == 0


# ── ball_valid_pct ────────────────────────────────────────────────────────────

def test_ball_valid_pct_critical() -> None:
    """ball_valid_pct < 0.30 → CRITICAL, needs_reprocess."""
    t = {**_healthy_tracking(), "ball_valid_pct": 0.10}
    result = score_tracking_json(t)
    assert result.needs_reprocess is True
    assert any("ball_valid_pct" in f for f in result.critical_flags)


def test_ball_valid_pct_warning() -> None:
    """ball_valid_pct between 0.30 and 0.60 → warn (not critical)."""
    t = {**_healthy_tracking(), "ball_valid_pct": 0.45}
    result = score_tracking_json(t)
    assert result.needs_reprocess is False
    assert any("ball_valid_pct" in f for f in result.warning_flags)


def test_ball_valid_pct_at_critical_threshold() -> None:
    """Exactly at critical threshold (0.30) should NOT be critical (boundary-inclusive)."""
    t = {**_healthy_tracking(), "ball_valid_pct": CRITICAL_BALL_VALID_PCT}
    result = score_tracking_json(t)
    # 0.30 == threshold; our check is value < threshold, so 0.30 is not critical
    assert result.needs_reprocess is False


# ── avg_players_detected ──────────────────────────────────────────────────────

def test_avg_players_critical() -> None:
    """avg_players_detected < 6 → CRITICAL."""
    t = {**_healthy_tracking(), "avg_players_detected": 4.5}
    result = score_tracking_json(t)
    assert result.needs_reprocess is True
    assert any("avg_players_detected" in f for f in result.critical_flags)


def test_avg_players_warn() -> None:
    """avg_players_detected between 6 and 7 → warn."""
    t = {**_healthy_tracking(), "avg_players_detected": 6.5}
    result = score_tracking_json(t)
    assert result.needs_reprocess is False
    assert any("avg_players_detected" in f for f in result.warning_flags)


# ── homography_stability ──────────────────────────────────────────────────────

def test_homography_stability_critical() -> None:
    """homography_stability < 0.80 → CRITICAL."""
    t = {**_healthy_tracking(), "homography_stability": 0.50}
    result = score_tracking_json(t)
    assert result.needs_reprocess is True


def test_homography_stability_ok() -> None:
    """homography_stability >= 0.80 → ok."""
    t = {**_healthy_tracking(), "homography_stability": 0.82}
    result = score_tracking_json(t)
    assert not any("homography_stability" in f for f in result.critical_flags)


# ── avg_fps ───────────────────────────────────────────────────────────────────

def test_avg_fps_critical() -> None:
    """avg_fps < 15 → CRITICAL."""
    t = {**_healthy_tracking(), "avg_fps": 10.0}
    result = score_tracking_json(t)
    assert result.needs_reprocess is True
    assert any("avg_fps" in f for f in result.critical_flags)


def test_avg_fps_ok() -> None:
    """avg_fps >= 15 → ok."""
    t = {**_healthy_tracking(), "avg_fps": 18.0}
    result = score_tracking_json(t)
    assert not any("avg_fps" in f for f in result.critical_flags)


# ── re_id_match_rate ──────────────────────────────────────────────────────────

def test_reid_match_rate_critical() -> None:
    """re_id_match_rate < 0.70 → CRITICAL."""
    t = {**_healthy_tracking(), "re_id_match_rate": 0.55}
    result = score_tracking_json(t)
    assert result.needs_reprocess is True


def test_reid_match_rate_ok() -> None:
    """re_id_match_rate >= 0.70 → ok."""
    t = {**_healthy_tracking(), "re_id_match_rate": 0.80}
    result = score_tracking_json(t)
    assert not any("re_id_match_rate" in f for f in result.critical_flags)


# ── missing metrics ───────────────────────────────────────────────────────────

def test_missing_metric_reported_as_warning() -> None:
    """Missing metric key → appears in warning_flags (not critical)."""
    t = {k: v for k, v in _healthy_tracking().items() if k != "avg_fps"}
    result = score_tracking_json(t)
    assert any("avg_fps" in f for f in result.warning_flags)


# ── audit_game_dir ────────────────────────────────────────────────────────────

def test_audit_game_dir_no_file(tmp_path: Path) -> None:
    """audit_game_dir flags needs_reprocess when no metrics file found."""
    result = audit_game_dir(str(tmp_path))
    assert result.needs_reprocess is True
    assert len(result.critical_flags) > 0


def test_audit_game_dir_with_metrics_file(tmp_path: Path) -> None:
    """audit_game_dir reads tracking_summary.json and scores it correctly."""
    metrics = _healthy_tracking()
    (tmp_path / "tracking_summary.json").write_text(
        json.dumps(metrics), encoding="utf-8"
    )
    result = audit_game_dir(str(tmp_path))
    assert result.overall_ok is True
    assert result.needs_reprocess is False


def test_audit_game_dir_critical_json(tmp_path: Path) -> None:
    """audit_game_dir flags CRITICAL when ball_valid_pct is critically low."""
    metrics = {**_healthy_tracking(), "ball_valid_pct": 0.05}
    (tmp_path / "tracking_summary.json").write_text(
        json.dumps(metrics), encoding="utf-8"
    )
    result = audit_game_dir(str(tmp_path))
    assert result.needs_reprocess is True


# ── to_dict serialization ─────────────────────────────────────────────────────

def test_to_dict_serializable() -> None:
    """to_dict() returns a JSON-serializable dict."""
    result = score_tracking_json(_healthy_tracking(), game_id="g42")
    d = result.to_dict()
    serialized = json.dumps(d)  # must not raise
    reparsed = json.loads(serialized)
    assert reparsed["game_id"] == "g42"
    assert reparsed["needs_reprocess"] is False
