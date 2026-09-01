"""Soccer broadcast-tracking depth diagnostics.

The probe measures observed coverage, not complete-match tracking quality.  It
uses adapter metadata so frames with accepted homography but zero players remain
in the player-depth denominator.
"""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd


def _fraction(numerator: int, denominator: int) -> float:
    return 0.0 if denominator <= 0 else float(numerator / denominator)


def _grade(homography: float, players: float, pitch: float, pressing: float) -> str:
    if homography >= 0.70 and players >= 14.0 and pitch >= 0.70 and pressing >= 0.50:
        return "A"
    if homography >= 0.40 and players >= 8.0 and pitch >= 0.40 and pressing >= 0.25:
        return "B"
    return "C"


def probe_tracking_depth(rows: pd.DataFrame, metadata: Mapping[str, Any]) -> dict[str, float | str]:
    """Return soccer-specific tracking coverage and a conservative depth grade.

    ``metadata`` is ``SoccerAdapter.last_metadata``.  Missing metadata is
    treated as unobserved coverage, rather than inferred from emitted rows.
    """
    processed = int(metadata.get("processed_frames", 0))
    pitch_frames = {int(frame) for frame in metadata.get("pitch_view_frames", [])}
    accepted = {int(frame) for frame in metadata.get("accepted_homography_frames", [])}
    player_rows = rows[rows["cls"] == "player"] if "cls" in rows else rows.iloc[0:0]
    player_counts = player_rows.groupby("frame").size()
    median_players = float(np.median([int(player_counts.get(frame, 0)) for frame in accepted])) if accepted else 0.0
    pressing = metadata.get("pressing_proxy", {})
    pressing_frames = {int(frame) for frame in pressing.get("frame_ids", [])} if isinstance(pressing, Mapping) else set()
    homography_coverage = _fraction(len(accepted), processed)
    pitch_coverage = _fraction(len(pitch_frames), processed)
    pressing_coverage = _fraction(len(pressing_frames & accepted), len(accepted))
    return {
        "pct_frames_accepted_homography": 100.0 * homography_coverage,
        "median_players_per_accepted_frame": median_players,
        "pitch_view_segment_coverage": pitch_coverage,
        "pressing_proxy_coverage": pressing_coverage,
        "depth_grade": _grade(homography_coverage, median_players, pitch_coverage, pressing_coverage),
    }


def format_depth_report(report: Mapping[str, float | str]) -> str:
    """Format an ASCII-only one-line depth report for headless runs."""
    return (
        "soccer_tracking_depth "
        "homography_pct=%.1f median_players=%.1f pitch_coverage=%.3f "
        "pressing_coverage=%.3f grade=%s"
        % (
            float(report["pct_frames_accepted_homography"]),
            float(report["median_players_per_accepted_frame"]),
            float(report["pitch_view_segment_coverage"]),
            float(report["pressing_proxy_coverage"]),
            str(report["depth_grade"]),
        )
    )
