"""
cv_quality.py — Tracking JSON quality scoring for the CV pipeline.

Implements the cv-quality-auditor spec: scores a tracking output dict
on five metrics and flags games needing reprocessing.

Public API
----------
    score_tracking_json(tracking: dict) -> TrackingQualityResult
    audit_game_dir(game_dir: str)       -> TrackingQualityResult
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# Thresholds from the cv-quality-auditor spec
CRITICAL_BALL_VALID_PCT    = 0.30   # below → CRITICAL (ball_track_suspended bug)
WARN_BALL_VALID_PCT        = 0.60
CRITICAL_AVG_PLAYERS       = 6.0
WARN_AVG_PLAYERS           = 7.0
CRITICAL_HOMOGRAPHY_STAB   = 0.80
CRITICAL_AVG_FPS           = 15.0
CRITICAL_REID_MATCH_RATE   = 0.70


@dataclass
class MetricResult:
    name: str
    value: Optional[float]
    passed: bool
    level: str  # "ok" | "warn" | "critical" | "missing"


@dataclass
class TrackingQualityResult:
    game_id: str
    metrics: List[MetricResult] = field(default_factory=list)
    critical_flags: List[str] = field(default_factory=list)
    warning_flags: List[str] = field(default_factory=list)
    needs_reprocess: bool = False

    @property
    def overall_ok(self) -> bool:
        return not self.needs_reprocess

    def to_dict(self) -> Dict:
        return {
            "game_id": self.game_id,
            "needs_reprocess": self.needs_reprocess,
            "critical_flags": self.critical_flags,
            "warning_flags": self.warning_flags,
            "metrics": {m.name: {"value": m.value, "level": m.level}
                        for m in self.metrics},
        }


def score_tracking_json(tracking: dict, game_id: str = "unknown") -> TrackingQualityResult:
    """
    Score a tracking output dict on five CV quality metrics.

    Expected tracking dict keys (all optional — missing treated as None):
        ball_valid_pct, avg_players_detected, homography_stability,
        avg_fps, re_id_match_rate

    Returns a TrackingQualityResult with per-metric pass/warn/critical flags.
    """
    result = TrackingQualityResult(game_id=game_id)

    def _check(
        name: str,
        value: Optional[float],
        critical_threshold: float,
        warn_threshold: Optional[float] = None,
        direction: str = "above",  # "above" = higher is better; "below" = lower is better
    ) -> MetricResult:
        if value is None:
            mr = MetricResult(name=name, value=None, passed=False, level="missing")
            result.warning_flags.append(f"{name}=missing")
            return mr

        if direction == "above":
            is_critical = value < critical_threshold
            is_warn = warn_threshold is not None and value < warn_threshold and not is_critical
        else:
            is_critical = value > critical_threshold
            is_warn = warn_threshold is not None and value > warn_threshold and not is_critical

        if is_critical:
            level = "critical"
            result.critical_flags.append(f"{name}={value:.3f}")
            result.needs_reprocess = True
        elif is_warn:
            level = "warn"
            result.warning_flags.append(f"{name}={value:.3f}")
        else:
            level = "ok"

        return MetricResult(name=name, value=value, passed=not is_critical, level=level)

    result.metrics.append(_check(
        "ball_valid_pct",
        tracking.get("ball_valid_pct"),
        CRITICAL_BALL_VALID_PCT,
        warn_threshold=WARN_BALL_VALID_PCT,
        direction="above",
    ))
    result.metrics.append(_check(
        "avg_players_detected",
        tracking.get("avg_players_detected"),
        CRITICAL_AVG_PLAYERS,
        warn_threshold=WARN_AVG_PLAYERS,
        direction="above",
    ))
    result.metrics.append(_check(
        "homography_stability",
        tracking.get("homography_stability"),
        CRITICAL_HOMOGRAPHY_STAB,
        direction="above",
    ))
    result.metrics.append(_check(
        "avg_fps",
        tracking.get("avg_fps"),
        CRITICAL_AVG_FPS,
        direction="above",
    ))
    result.metrics.append(_check(
        "re_id_match_rate",
        tracking.get("re_id_match_rate"),
        CRITICAL_REID_MATCH_RATE,
        direction="above",
    ))

    return result


def audit_game_dir(game_dir: str) -> TrackingQualityResult:
    """
    Load tracking_summary.json from game_dir and score it.

    Looks for: <game_dir>/tracking_summary.json or <game_dir>/metrics.json
    Returns a result with needs_reprocess=True and critical flags on load failure.
    """
    import json
    import os
    from pathlib import Path

    gd = Path(game_dir)
    game_id = gd.name

    for fname in ("tracking_summary.json", "metrics.json", "tracking_metrics.json"):
        p = gd / fname
        if p.exists():
            try:
                tracking = json.loads(p.read_text(encoding="utf-8"))
                return score_tracking_json(tracking, game_id=game_id)
            except Exception as exc:
                result = TrackingQualityResult(game_id=game_id, needs_reprocess=True)
                result.critical_flags.append(f"parse_error: {exc}")
                return result

    result = TrackingQualityResult(game_id=game_id, needs_reprocess=True)
    result.critical_flags.append("no_metrics_file_found")
    return result
