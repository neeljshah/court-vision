"""Evaluate canonical tracking rows with versioned, sport-specific thresholds.

Run: python scripts/platformkit/tracking_harness.py <tracking.csv> <sport>
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from typing import Mapping

import pandas as pd

from scripts.platformkit.attempted_frame_count_source import evaluated_frames_from_tracking_table
from scripts.platformkit.liveness_metrics import compute_liveness_metrics, liveness_failures
from scripts.platformkit.metric_local_profile import report_fields as metric_local_report_fields
from scripts.platformkit.tracking_schema import (
    CoordinateTransformUnavailable,
    METRIC_LOCAL,
    identify_tracking_schema,
    normalize_tracking_frame,
)

DEFAULT_CONFIG_VERSION = "2026-09-01-v1"
_BASKETBALL = {"bounds": (0, 94, 0, 50), "min_players": 6,
               "ball_valid_min": 0.30, "coverage_min": 0.60,
               "oob_max": 0.05, "jump_p95_max": 6.0, "jump_max_max": 6.0,
               "min_median_track_len": 3.0}
_BASEBALL = {"bounds": (-30, 30, 0, 60), "min_players": 2,
             "ball_valid_min": 0.10, "coverage_min": 0.70,
             "oob_max": 0.10, "jump_p95_max": 10.0, "jump_max_max": 10.0,
             "min_median_track_len": 3.0}

# A report carries both this version and its input sport label, even when an
# adapter implementation is shared by related competitions.
CONFIG_VERSIONS: dict[str, dict[str, dict]] = {
    DEFAULT_CONFIG_VERSION: {
        "basketball": dict(_BASKETBALL),
        "wnba": dict(_BASKETBALL),
        "tennis": {"bounds": (-21, 99, -12, 48), "min_players": 2,
                   "ball_valid_min": 0.20, "coverage_min": 0.90,
                   "oob_max": 0.08, "jump_p95_max": 8.0, "jump_max_max": 8.0,
                   "min_median_track_len": 3.0},
        "soccer": {"bounds": (0, 105, 0, 68), "min_players": 14,
                   "ball_valid_min": 0.20, "coverage_min": 0.85,
                   "oob_max": 0.05, "jump_p95_max": 8.0, "jump_max_max": 8.0,
                   "min_median_track_len": 3.0},
        "baseball": dict(_BASEBALL),
        "npb": dict(_BASEBALL),
        "kbo": dict(_BASEBALL),
        # FootballAdapter emits only pre-snap rows in an offset-relative
        # 360-by-160-foot field plane and deliberately has no ball detector.
        "football": {"bounds": (0, 360, 0, 160), "min_players": 14,
                     "ball_valid_min": 0.0, "coverage_min": 0.85,
                     "oob_max": 0.05, "jump_p95_max": 8.0, "jump_max_max": 8.0,
                     "min_median_track_len": 3.0},
    }
}
# Backward-compatible view of the current threshold map.
SPORTS = CONFIG_VERSIONS[DEFAULT_CONFIG_VERSION]


# G50: below this many frames the metrics are not meaningful. NEW constant --
# it gates nothing today and no existing threshold was touched.
MIN_FRAMES_FOR_METRICS = 30
_N_DEPENDENT_METRIC_FIELDS = (
    "coverage_pct", "det_per_frame", "median_track_len", "ball_valid_pct",
    "coverage_attempted_frames_pct", "ball_valid_attempted_frames_pct",
    "ball_in_bounds_pct", "jump_p95", "jump_max", "oob_pct", "zero_step_share",
    "median_step_distance", "distinct_position_ratio", "stationary_track_share",
    "liveness_verdict", "jump_p95_ft_per_s", "jump_max_modal_stride_frames",
)


@dataclass
class QualityReport:
    sport: str
    config_version: str
    n_frames: int
    n_unique_games: int
    n_duplicate_frame_track_rows: int
    ball_rows: int
    coverage_pct: float | None
    det_per_frame: float | None
    median_track_len: float | None
    ball_valid_pct: float | None
    ball_valid: str
    ball_valid_applicable: bool
    ball_telemetry_available: bool | None
    ball_telemetry_rule: str
    # Deprecated gate statistic retained for historical report readers only.
    jump_p95: float | str | None
    # Current gate statistic: max displacement on modal-stride-adjacent pairs.
    jump_max: float | str | None
    oob_pct: float | str | None
    zero_step_share: float | None
    median_step_distance: float | str | None
    distinct_position_ratio: float | str | None
    stationary_track_share: float | str | None
    liveness_verdict: str | None
    source_resolution: str | None
    source_frame_rate: float | None
    self_consistency_only: bool
    passed: bool
    verdict: str
    failures: list[str]
    # G43: ball_valid_pct measures ball-row PRESENCE, so a row projecting to
    # 106,853 ft counts as valid telemetry. This reports how many of those rows
    # actually land on the court. Additive and informational -- it does NOT
    # gate, and no threshold reads it.
    ball_in_bounds_pct: float | str | None = None
    # G50: coverage_pct 1.0 has been published on a 2-frame table. This flags a
    # report whose metrics rest on too little data to mean anything. Additive
    # and informational -- `passed` deliberately does not read it.
    insufficient_data: bool = False
    # G48: a raw per-step jump has no stable time unit unless the producing
    # run records its configured stride and the source frame rate. These are
    # informational only; `passed` deliberately does not read them.
    sampling_interval_s: float | None = None
    sampling_interval_reason: str | None = None
    jump_p95_ft_per_s: float | str | None = None
    jump_max_modal_stride_frames: int | None = None
    # The legacy fields above retain their emitted-frame denominator. These
    # additive fields are the only coverage metrics allowed to decide a gate.
    attempted_frames: int | None = None
    coverage_attempted_frames_pct: float | None = None
    ball_valid_attempted_frames_pct: float | None = None
    coverage_pct_denominator: str = "emitted_frames"
    ball_valid_pct_denominator: str = "emitted_frames"
    coverage_attempted_frames_pct_denominator: str = "unavailable"
    ball_valid_attempted_frames_pct_denominator: str = "unavailable"

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def _source_fields(metadata: Mapping[str, object] | None) -> tuple[str | None, float | None]:
    if not metadata:
        return None, None
    resolution = metadata.get("resolution")
    frame_rate = metadata.get("frame_rate")
    return (str(resolution) if resolution is not None else None,
            float(frame_rate) if frame_rate is not None else None)


def _sampling_fields(metadata: Mapping[str, object] | None) -> tuple[float | None, str | None]:
    """Return the configured sampling interval, never inferring it from rows."""
    if not metadata:
        return None, "source metadata unavailable"
    frame_rate = metadata.get("frame_rate")
    stride = metadata.get("frame_stride", metadata.get("stride"))
    if frame_rate is None:
        return None, "source frame rate unavailable"
    if stride is None:
        return None, "frame stride unavailable"
    try:
        frame_rate = float(frame_rate)
        stride = int(stride)
    except (TypeError, ValueError):
        return None, "source frame rate or frame stride is invalid"
    if frame_rate <= 0:
        return None, "source frame rate is not positive"
    if stride <= 0:
        return None, "frame stride is not positive"
    return round(stride / frame_rate, 4), None


def _failed_report(sport: str, config_version: str, failure: str,
                   metadata: Mapping[str, object] | None = None,
                   schema=None) -> QualityReport:
    resolution, frame_rate = _source_fields(metadata)
    interval, interval_reason = _sampling_fields(metadata)
    available = schema.ball_telemetry_available if schema is not None else None
    rule = schema.ball_telemetry_rule if schema is not None else "not_normalized"
    return QualityReport(
        sport=sport, config_version=config_version, n_frames=0, n_unique_games=0,
        n_duplicate_frame_track_rows=0, ball_rows=0, coverage_pct=0.0,
        det_per_frame=0.0, median_track_len=0.0, ball_valid_pct=0.0,
        ball_valid="not_evaluated", ball_valid_applicable=available is not False,
        ball_telemetry_available=available, ball_telemetry_rule=rule,
        jump_p95=0.0, jump_max=None, oob_pct=0.0, zero_step_share=0.0,
        median_step_distance=0.0, distinct_position_ratio=0.0,
        stationary_track_share=0.0, liveness_verdict="SUSPECT",
        source_resolution=resolution, source_frame_rate=frame_rate,
        self_consistency_only=True, passed=False, verdict="FAIL", failures=[failure],
        sampling_interval_s=interval, sampling_interval_reason=interval_reason,
        jump_p95_ft_per_s=(0.0 if interval is not None else None))


def _modal_stride(frame_gaps: pd.Series) -> int | None:
    """Return the unique most-frequent positive per-track frame gap, if any."""
    counts = frame_gaps.loc[frame_gaps > 0].value_counts()
    if counts.empty:
        return None
    top_count = counts.max()
    modes = counts.loc[counts.eq(top_count)]
    return int(modes.index[0]) if len(modes) == 1 else None


def _attempted_frame_count(df: pd.DataFrame, attempted_frames: int | None,
                           emitted_frames: int) -> tuple[int | None, str | None]:
    """Validate an explicit attempted count, never deriving one from emitted rows."""
    candidate = attempted_frames
    if candidate is None and "attempted_frames" in df:
        values = df["attempted_frames"].dropna().unique()
        if len(values) != 1 or df["attempted_frames"].isna().any():
            return None, "attempted_frames invalid"
        candidate = values[0]
    if candidate is None:
        return None, "attempted_frames unavailable"
    try:
        value = int(candidate)
    except (TypeError, ValueError):
        return None, "attempted_frames invalid"
    if value != candidate or value < emitted_frames or value <= 0:
        return None, "attempted_frames invalid"
    return value, None


def _apply_metric_local_attempted_gate(report: QualityReport, df: pd.DataFrame, cfg: Mapping[str, object],
                                       attempted_frames: int | None, reason: str | None) -> QualityReport:
    """Replace metric-local's legacy coverage checks with attempted-frame checks."""
    report.attempted_frames = attempted_frames
    report.coverage_pct_denominator = "emitted_frames"
    report.ball_valid_pct_denominator = "emitted_frames"
    report.failures = [failure for failure in report.failures
                       if not failure.startswith(("coverage ", "ball_valid "))]
    if attempted_frames is None:
        report.coverage_attempted_frames_pct_denominator = "unavailable"
        report.ball_valid_attempted_frames_pct_denominator = "unavailable"
        report.failures.append(reason or "attempted_frames unavailable")
    else:
        players = df[df["cls"] == "player"]
        coverage = float((players.groupby("frame")["track_id"].nunique()
                          >= cfg["min_players"]).sum() / attempted_frames)
        report.coverage_attempted_frames_pct = round(coverage, 4)
        report.coverage_attempted_frames_pct_denominator = "attempted_frames"
        if coverage < cfg["coverage_min"]:
            report.failures.append("coverage_attempted_frames {:.2f} < {:.2f}".format(
                coverage, cfg["coverage_min"]
            ))
        if report.ball_telemetry_available is not False:
            ball_valid = float(df.loc[df["cls"] == "ball", "frame"].nunique() / attempted_frames)
            report.ball_valid_attempted_frames_pct = round(ball_valid, 4)
            report.ball_valid_attempted_frames_pct_denominator = "attempted_frames"
            if ball_valid < cfg["ball_valid_min"]:
                report.failures.append("ball_valid_attempted_frames {:.2f} < {:.2f}".format(
                    ball_valid, cfg["ball_valid_min"]
                ))
        else:
            report.ball_valid_attempted_frames_pct_denominator = "not_applicable"
    report.passed = not report.failures
    report.verdict = "PASS_METRIC_LOCAL" if report.passed else "FAIL_METRIC_LOCAL"
    return report


def _adjudicate_insufficient_data(report: QualityReport) -> QualityReport:
    if report.insufficient_data:
        report.passed = False
        report.verdict = "INSUFFICIENT_DATA"
        report.failures = ["insufficient data: {} frames < {}".format(
            report.n_frames, MIN_FRAMES_FOR_METRICS)]
    return report


def evaluate(df: pd.DataFrame, sport: str,
             config_version: str = DEFAULT_CONFIG_VERSION,
             source_metadata: Mapping[str, object] | None = None,
             source: str | None = None,
             attempted_frames: int | None = None,
             allow_legacy_undeclared: bool = False) -> QualityReport:
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

    schema = None
    try:
        schema = identify_tracking_schema(df, source)
        df = normalize_tracking_frame(df, source, sport, allow_legacy_undeclared)
    except CoordinateTransformUnavailable as exc:
        return _failed_report(sport, config_version, "coordinate_contract: {}".format(exc),
                              source_metadata, schema)
    resolution, frame_rate = _source_fields(source_metadata)
    sampling_interval, sampling_interval_reason = _sampling_fields(source_metadata)
    n_frames = int(df["frame"].nunique())
    attempted_count, attempted_reason = _attempted_frame_count(df, attempted_frames, n_frames)
    # Legacy-undeclared rows reach here without a coordinate_space column at all
    # (normalize_tracking_frame leaves them as-is under the audited legacy mode).
    # Reading it unconditionally turned an intended clean FAIL into a KeyError,
    # so absence means "not metric_local" and falls through to the court profile.
    if "coordinate_space" in df and df["coordinate_space"].eq(METRIC_LOCAL).all():
        local_report = QualityReport(
            sport=sport, config_version=config_version, source_resolution=resolution,
            source_frame_rate=frame_rate, sampling_interval_s=sampling_interval,
            sampling_interval_reason=sampling_interval_reason,
            **metric_local_report_fields(df, cfg, schema),
        )
        return _adjudicate_insufficient_data(_apply_metric_local_attempted_gate(
            local_report, df, cfg, attempted_count, attempted_reason
        ))
    n_unique_games = (int(df["game_id"].dropna().nunique()) if "game_id" in df
                      else int(n_frames > 0))
    duplicate_keys = ["frame", "track_id"]
    if "game_id" in df:
        duplicate_keys.insert(0, "game_id")
    duplicates = int(df.duplicated(duplicate_keys).sum())
    ball_rows = int((df["cls"] == "ball").sum())
    if n_frames == 0:
        report = _failed_report(sport, config_version, "empty", source_metadata, schema)
        report.n_duplicate_frame_track_rows = duplicates
        report.ball_rows = ball_rows
        return report

    x0, x1, y0, y1 = cfg["bounds"]
    players = df[df["cls"] == "player"]
    per_frame = players.groupby("frame")["track_id"].nunique()
    coverage = float((per_frame >= cfg["min_players"]).sum() / n_frames)
    coverage_attempted = (float((per_frame >= cfg["min_players"]).sum() / attempted_count)
                          if attempted_count is not None else None)
    det_per_frame = float(len(df) / n_frames)
    track_len = (float(players.groupby("track_id")["frame"].count().median())
                 if len(players) else 0.0)
    oob = (~players["x"].between(x0, x1)) | (~players["y"].between(y0, y1))
    oob_pct = float(oob.mean()) if len(players) else 1.0
    ball_valid = (float(df[df["cls"] == "ball"]["frame"].nunique() / n_frames)
                  if schema.ball_telemetry_available is not False else None)
    ball_valid_attempted = (float(df[df["cls"] == "ball"]["frame"].nunique() / attempted_count)
                            if attempted_count is not None and schema.ball_telemetry_available is not False
                            else None)
    balls = df[df["cls"] == "ball"]
    ball_in_bounds = (float((balls["x"].between(x0, x1) & balls["y"].between(y0, y1)).mean())
                      if len(balls) else None)
    grouped = players.sort_values(["track_id", "frame"]).groupby("track_id")
    frame_gaps = grouped["frame"].diff()
    jump = ((grouped["x"].diff() ** 2 + grouped["y"].diff() ** 2) ** 0.5).dropna()
    jump_p95 = float(jump.quantile(0.95)) if len(jump) else 0.0
    modal_stride = _modal_stride(frame_gaps)
    modal_jump = jump.loc[frame_gaps.eq(modal_stride)] if modal_stride is not None else jump.iloc[0:0]
    jump_max = float(modal_jump.max()) if len(modal_jump) else None
    liveness = compute_liveness_metrics(df, sport)

    failures: list[str] = []
    if duplicates:
        failures.append("duplicate frame-track rows {}".format(duplicates))
    for name, value, threshold, operator in (
        ("coverage_attempted_frames", coverage_attempted, cfg["coverage_min"], "min"),
        ("median_track_len", track_len, cfg["min_median_track_len"], "min"),
        ("oob", oob_pct, cfg["oob_max"], "max"),
        ("jump_max", jump_max, cfg["jump_max_max"], "max"),
    ):
        invalid = value is not None and (value < threshold if operator == "min" else value > threshold)
        if invalid:
            sign = "<" if operator == "min" else ">"
            failures.append("{} {:.2f} {} {:.2f}".format(name, value, sign, threshold))
    if len(players) and jump_max is None:
        failures.append("jump_max unmeasurable: no unique positive modal frame stride")
    if attempted_reason is not None:
        failures.append(attempted_reason)
    if ball_valid_attempted is not None and ball_valid_attempted < cfg["ball_valid_min"]:
        failures.append("ball_valid_attempted_frames {:.2f} < {:.2f}".format(
            ball_valid_attempted, cfg["ball_valid_min"]
        ))
    if liveness.verdict == "FROZEN":
        failures.append("liveness verdict FROZEN")
    failures.extend(liveness_failures(liveness, sport))

    passed = not failures
    verdict = "PASS_NO_BALL" if passed and schema.ball_telemetry_available is False else (
        "PASS" if passed else "FAIL"
    )
    reported_jump_p95 = round(jump_p95, 2)
    reported_jump_max = round(jump_max, 2) if jump_max is not None else None
    jump_p95_ft_per_s = (round(reported_jump_p95 / sampling_interval, 2)
                          if sampling_interval is not None else None)
    report = QualityReport(sport, config_version, n_frames, n_unique_games,
                           duplicates, ball_rows, round(coverage, 4),
                           round(det_per_frame, 2), track_len,
                           round(ball_valid, 4) if ball_valid is not None else None,
                           "evaluated" if ball_valid is not None else "not_evaluated",
                           schema.ball_telemetry_available is not False,
                           schema.ball_telemetry_available, schema.ball_telemetry_rule,
                           reported_jump_p95, reported_jump_max, round(oob_pct, 4),
                           round(liveness.zero_step_share, 4),
                           round(liveness.median_step_distance, 4),
                           round(liveness.distinct_position_ratio, 4),
                           round(liveness.stationary_track_share, 4),
                           liveness.verdict, resolution,
                           frame_rate, True, passed, verdict, failures,
                           round(ball_in_bounds, 4) if ball_in_bounds is not None else None,
                           n_frames < MIN_FRAMES_FOR_METRICS, sampling_interval,
                           sampling_interval_reason, jump_p95_ft_per_s, modal_stride,
                           attempted_count,
                           round(coverage_attempted, 4) if coverage_attempted is not None else None,
                           round(ball_valid_attempted, 4) if ball_valid_attempted is not None else None,
                           "emitted_frames", "emitted_frames",
                           "attempted_frames" if attempted_count is not None else "unavailable",
                           "attempted_frames" if attempted_count is not None else "unavailable")
    if report.insufficient_data:
        for field in _N_DEPENDENT_METRIC_FIELDS:
            setattr(report, field, None)
    return _adjudicate_insufficient_data(report)


def evaluate_csv_path(path: str, sport: str,
                      config_version: str = DEFAULT_CONFIG_VERSION) -> QualityReport:
    """Score a direct CSV using only its stable pre-tracking metadata count."""
    frame = pd.read_csv(path)
    return evaluate(
        frame, sport, config_version, source=path,
        attempted_frames=evaluated_frames_from_tracking_table(frame),
    )


if __name__ == "__main__":
    path, sport, *version = sys.argv[1:]
    report = evaluate_csv_path(path, sport, version[0] if version else DEFAULT_CONFIG_VERSION)
    sys.stdout.write(report.to_json() + "\n")
    sys.exit(0 if report.passed else 1)
