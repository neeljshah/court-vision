"""Non-spatial tracking metrics for explicitly declared local-scale rows."""
from __future__ import annotations

from typing import Mapping

import pandas as pd

NOT_APPLICABLE = "not_applicable"
_SPATIAL_FIELDS = (
    "jump_p95", "oob_pct", "median_step_distance", "distinct_position_ratio",
    "stationary_track_share", "liveness_verdict", "ball_in_bounds_pct",
    "jump_p95_ft_per_s",
)


def _zero_step_share(players: pd.DataFrame) -> float:
    """Return exact repeated-coordinate share without calculating a distance."""
    ordered = players.sort_values(["track_id", "frame"])
    delta_x = ordered.groupby("track_id")["x"].diff()
    delta_y = ordered.groupby("track_id")["y"].diff()
    same_x, same_y = delta_x.eq(0), delta_y.eq(0)
    steps = delta_x.notna() & delta_y.notna()
    return float((same_x[steps] & same_y[steps]).mean()) if steps.any() else 0.0


def report_fields(df: pd.DataFrame, cfg: Mapping[str, float], schema) -> dict[str, object]:
    """Score only G69's declared non-spatial metrics for metric-local rows."""
    n_frames = int(df["frame"].nunique())
    n_unique_games = (int(df["game_id"].dropna().nunique()) if "game_id" in df
                      else int(n_frames > 0))
    keys = ["frame", "track_id"]
    if "game_id" in df:
        keys.insert(0, "game_id")
    duplicates = int(df.duplicated(keys).sum())
    players = df[df["cls"] == "player"]
    balls = df[df["cls"] == "ball"]
    per_frame = players.groupby("frame")["track_id"].nunique()
    coverage = float((per_frame >= cfg["min_players"]).sum() / n_frames) if n_frames else 0.0
    det_per_frame = float(len(df) / n_frames) if n_frames else 0.0
    track_len = float(players.groupby("track_id")["frame"].count().median()) if len(players) else 0.0
    ball_valid = (float(balls["frame"].nunique() / n_frames) if n_frames
                  and schema.ball_telemetry_available is not False else None)
    failures: list[str] = []
    if n_frames == 0:
        failures.append("empty")
    if duplicates:
        failures.append("duplicate frame-track rows {}".format(duplicates))
    for name, value, threshold in (("coverage", coverage, cfg["coverage_min"]),
                                   ("median_track_len", track_len, cfg["min_median_track_len"])):
        if value < threshold:
            failures.append("{} {:.2f} < {:.2f}".format(name, value, threshold))
    if ball_valid is not None and ball_valid < cfg["ball_valid_min"]:
        failures.append("ball_valid {:.2f} < {:.2f}".format(ball_valid, cfg["ball_valid_min"]))
    fields: dict[str, object] = {
        "n_frames": n_frames, "n_unique_games": n_unique_games,
        "n_duplicate_frame_track_rows": duplicates, "ball_rows": int(len(balls)),
        "coverage_pct": round(coverage, 4), "det_per_frame": round(det_per_frame, 2),
        "median_track_len": track_len, "ball_valid_pct": round(ball_valid, 4) if ball_valid is not None else None,
        "ball_valid": "evaluated" if ball_valid is not None else "not_evaluated",
        "ball_valid_applicable": schema.ball_telemetry_available is not False,
        "ball_telemetry_available": schema.ball_telemetry_available,
        "ball_telemetry_rule": schema.ball_telemetry_rule,
        "zero_step_share": round(_zero_step_share(players), 4),
        "self_consistency_only": True, "passed": False,
        "verdict": "PASS_METRIC_LOCAL" if not failures else "FAIL_METRIC_LOCAL",
        "failures": failures, "insufficient_data": n_frames < 30,
    }
    fields.update({field: NOT_APPLICABLE for field in _SPATIAL_FIELDS})
    return fields
