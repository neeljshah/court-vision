"""Evaluate canonical tracking rows with versioned, sport-specific thresholds.

Run: python scripts/platformkit/tracking_harness.py <tracking.csv> <sport>
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from typing import Mapping

import pandas as pd

from scripts.platformkit.liveness_metrics import compute_liveness_metrics, liveness_failures
from scripts.platformkit.tracking_schema import (
    CoordinateTransformUnavailable,
    identify_tracking_schema,
    normalize_tracking_frame,
)

DEFAULT_CONFIG_VERSION = "2026-09-01-v1"
_BASKETBALL = {"bounds": (0, 94, 0, 50), "min_players": 6,
               "ball_valid_min": 0.30, "coverage_min": 0.60,
               "oob_max": 0.05, "jump_p95_max": 6.0}
_BASEBALL = {"bounds": (-30, 30, 0, 60), "min_players": 2,
             "ball_valid_min": 0.10, "coverage_min": 0.70,
             "oob_max": 0.10, "jump_p95_max": 10.0}

# A report carries both this version and its input sport label, even when an
# adapter implementation is shared by related competitions.
CONFIG_VERSIONS: dict[str, dict[str, dict]] = {
    DEFAULT_CONFIG_VERSION: {
        "basketball": dict(_BASKETBALL),
        "wnba": dict(_BASKETBALL),
        "tennis": {"bounds": (-21, 99, -12, 48), "min_players": 2,
                   "ball_valid_min": 0.20, "coverage_min": 0.90,
                   "oob_max": 0.08, "jump_p95_max": 8.0},
        "soccer": {"bounds": (0, 105, 0, 68), "min_players": 14,
                   "ball_valid_min": 0.20, "coverage_min": 0.85,
                   "oob_max": 0.05, "jump_p95_max": 8.0},
        "baseball": dict(_BASEBALL),
        "npb": dict(_BASEBALL),
        "kbo": dict(_BASEBALL),
        # FootballAdapter emits only pre-snap rows in an offset-relative
        # 360-by-160-foot field plane and deliberately has no ball detector.
        "football": {"bounds": (0, 360, 0, 160), "min_players": 14,
                     "ball_valid_min": 0.0, "coverage_min": 0.85,
                     "oob_max": 0.05, "jump_p95_max": 8.0},
    }
}
# Backward-compatible view of the current threshold map.
SPORTS = CONFIG_VERSIONS[DEFAULT_CONFIG_VERSION]


@dataclass
class QualityReport:
    sport: str
    config_version: str
    n_frames: int
    n_unique_games: int
    n_duplicate_frame_track_rows: int
    ball_rows: int
    coverage_pct: float
    det_per_frame: float
    median_track_len: float
    ball_valid_pct: float | None
    ball_valid_applicable: bool
    jump_p95: float
    oob_pct: float
    zero_step_share: float
    median_step_distance: float
    distinct_position_ratio: float
    stationary_track_share: float
    liveness_verdict: str
    source_resolution: str | None
    source_frame_rate: float | None
    self_consistency_only: bool
    passed: bool
    failures: list[str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def _source_fields(metadata: Mapping[str, object] | None) -> tuple[str | None, float | None]:
    if not metadata:
        return None, None
    resolution = metadata.get("resolution")
    frame_rate = metadata.get("frame_rate")
    return (str(resolution) if resolution is not None else None,
            float(frame_rate) if frame_rate is not None else None)


def _failed_report(sport: str, config_version: str, failure: str,
                   metadata: Mapping[str, object] | None = None) -> QualityReport:
    resolution, frame_rate = _source_fields(metadata)
    return QualityReport(
        sport=sport, config_version=config_version, n_frames=0, n_unique_games=0,
        n_duplicate_frame_track_rows=0, ball_rows=0, coverage_pct=0.0,
        det_per_frame=0.0, median_track_len=0.0, ball_valid_pct=0.0,
        ball_valid_applicable=True,
        jump_p95=0.0, oob_pct=0.0, zero_step_share=0.0,
        median_step_distance=0.0, distinct_position_ratio=0.0,
        stationary_track_share=0.0, liveness_verdict="SUSPECT",
        source_resolution=resolution, source_frame_rate=frame_rate,
        self_consistency_only=True, passed=False, failures=[failure])


def evaluate(df: pd.DataFrame, sport: str,
             config_version: str = DEFAULT_CONFIG_VERSION,
             source_metadata: Mapping[str, object] | None = None) -> QualityReport:
    """Return self-consistency health metrics for a recognized tracking table."""
    configs = CONFIG_VERSIONS.get(config_version)
    if configs is None:
        return _failed_report(sport, config_version,
                              "unknown config version {}".format(config_version),
                              source_metadata)
    cfg = configs.get(sport)
    if cfg is None:
        return _failed_report(sport, config_version,
                              "unknown sport {}".format(sport), source_metadata)

    try:
        schema = identify_tracking_schema(df)
        df = normalize_tracking_frame(df)
    except CoordinateTransformUnavailable as exc:
        return _failed_report(sport, config_version, "coordinate_contract: {}".format(exc),
                              source_metadata)
    resolution, frame_rate = _source_fields(source_metadata)
    n_frames = int(df["frame"].nunique())
    n_unique_games = (int(df["game_id"].dropna().nunique()) if "game_id" in df
                      else int(n_frames > 0))
    duplicate_keys = ["frame", "track_id"]
    if "game_id" in df:
        duplicate_keys.insert(0, "game_id")
    duplicates = int(df.duplicated(duplicate_keys).sum())
    ball_rows = int((df["cls"] == "ball").sum())
    if n_frames == 0:
        report = _failed_report(sport, config_version, "empty", source_metadata)
        report.n_duplicate_frame_track_rows = duplicates
        report.ball_rows = ball_rows
        return report

    x0, x1, y0, y1 = cfg["bounds"]
    players = df[df["cls"] == "player"]
    per_frame = players.groupby("frame")["track_id"].nunique()
    coverage = float((per_frame >= cfg["min_players"]).sum() / n_frames)
    det_per_frame = float(len(df) / n_frames)
    track_len = (float(players.groupby("track_id")["frame"].count().median())
                 if len(players) else 0.0)
    oob = (~players["x"].between(x0, x1)) | (~players["y"].between(y0, y1))
    oob_pct = float(oob.mean()) if len(players) else 1.0
    ball_valid = (float(df[df["cls"] == "ball"]["frame"].nunique() / n_frames)
                  if schema.ball_telemetry_available else None)
    grouped = players.sort_values(["track_id", "frame"]).groupby("track_id")
    jump = ((grouped["x"].diff() ** 2 + grouped["y"].diff() ** 2) ** 0.5).dropna()
    jump_p95 = float(jump.quantile(0.95)) if len(jump) else 0.0
    liveness = compute_liveness_metrics(df, sport)

    failures: list[str] = []
    if duplicates:
        failures.append("duplicate frame-track rows {}".format(duplicates))
    for name, value, threshold, operator in (
        ("coverage", coverage, cfg["coverage_min"], "min"),
        ("oob", oob_pct, cfg["oob_max"], "max"),
        ("jump_p95", jump_p95, cfg["jump_p95_max"], "max"),
    ):
        invalid = value < threshold if operator == "min" else value > threshold
        if invalid:
            sign = "<" if operator == "min" else ">"
            failures.append("{} {:.2f} {} {:.2f}".format(name, value, sign, threshold))
    if ball_valid is not None and ball_valid < cfg["ball_valid_min"]:
        failures.append("ball_valid {:.2f} < {:.2f}".format(
            ball_valid, cfg["ball_valid_min"]
        ))
    if liveness.verdict == "FROZEN":
        failures.append("liveness verdict FROZEN")
    failures.extend(liveness_failures(liveness, sport))

    return QualityReport(sport, config_version, n_frames, n_unique_games,
                         duplicates, ball_rows, round(coverage, 4),
                         round(det_per_frame, 2), track_len,
                         round(ball_valid, 4) if ball_valid is not None else None,
                         schema.ball_telemetry_available,
                         round(jump_p95, 2), round(oob_pct, 4),
                         round(liveness.zero_step_share, 4),
                         round(liveness.median_step_distance, 4),
                         round(liveness.distinct_position_ratio, 4),
                         round(liveness.stationary_track_share, 4),
                         liveness.verdict, resolution,
                         frame_rate, True, not failures, failures)


if __name__ == "__main__":
    path, sport, *version = sys.argv[1:]
    report = evaluate(pd.read_csv(path), sport,
                      version[0] if version else DEFAULT_CONFIG_VERSION)
    sys.stdout.write(report.to_json() + "\n")
    sys.exit(0 if report.passed else 1)
