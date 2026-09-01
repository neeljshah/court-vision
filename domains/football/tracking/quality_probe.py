"""Pre-snap-aware depth diagnostics for football tracking rows.

The shared harness grades every frame, but this adapter is deliberately scoped
to pre-snap formations.  This probe reports both that ungated harness coverage
and the coverage of the detected pre-snap subset; neither is an accuracy claim.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from domains.football.tracking.presnap_features import (
    LOS_BAND_FT,
    MIN_PLAYERS_FOR_LOS,
    formation_features,
    formation_family,
    line_of_scrimmage,
    offense_defense_split,
)
from scripts.platformkit.tracking_harness import SPORTS


PRE_SNAP_MAX_DISPLACEMENT_FT = 1.0
_FOOTBALL = SPORTS["football"]
DEPTH_GRADE_THRESHOLDS = {
    "A": {"presnap_coverage": 0.95, "los": 0.98, "players": 20.0, "formation": 0.67},
    "B": {"presnap_coverage": _FOOTBALL["coverage_min"], "los": _FOOTBALL["coverage_min"],
          "players": float(_FOOTBALL["min_players"]), "formation": 0.50},
}


@dataclass(frozen=True)
class DepthReport:
    """Observed football tracking depth with an explicit pre-snap gate."""

    source: str
    sport: str
    rows: int
    frames: int
    pct_frames_presnap_view: float
    pct_frames_los_resolved: float
    median_players_per_presnap_frame: float
    formation_family_fill_rate: float
    pct_frames_presnap_coverage: float
    ungated_harness_coverage: float
    depth_grade: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready report with its published thresholds."""
        result = asdict(self)
        result["grade_thresholds"] = DEPTH_GRADE_THRESHOLDS
        result["presnap_max_displacement_ft"] = PRE_SNAP_MAX_DISPLACEMENT_FT
        result["los_band_ft"] = LOS_BAND_FT
        return result


def _players(rows: pd.DataFrame) -> pd.DataFrame:
    required = {"frame", "track_id", "x", "y"}
    missing = sorted(required.difference(rows.columns))
    if missing:
        raise ValueError("tracking rows missing columns: %s" % ", ".join(missing))
    return rows.loc[rows["cls"].eq("player")].copy() if "cls" in rows else rows.copy()


def _frame_motion(players: pd.DataFrame) -> dict[int, float]:
    ordered = players.sort_values(["track_id", "frame"])
    delta = ordered.groupby("track_id")[["x", "y"]].diff()
    ordered = ordered.assign(_jump=np.hypot(delta["x"], delta["y"]).fillna(0.0))
    return {int(frame): float(value) for frame, value in ordered.groupby("frame")["_jump"].max().items()}


def _grade(coverage: float, los: float, players: float, formation: float) -> str:
    values = (coverage, los, players, formation)
    for grade in ("A", "B"):
        if all(value >= threshold for value, threshold in zip(values, DEPTH_GRADE_THRESHOLDS[grade].values())):
            return grade
    return "C"


def measure_dataframe(rows: pd.DataFrame, source: str = "<dataframe>") -> DepthReport:
    """Measure a football frame table without treating post-snap motion as loss."""
    players = _players(rows)
    frames = sorted(int(frame) for frame in rows["frame"].unique())
    if not frames:
        return DepthReport(str(source), "football", len(rows), 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "C")
    motion = _frame_motion(players)
    per_frame = players.groupby("frame")
    presnap: list[pd.DataFrame] = []
    los_resolved = 0
    formation_filled = 0
    for frame in frames:
        frame_rows = per_frame.get_group(frame) if frame in per_frame.groups else players.iloc[0:0]
        los = line_of_scrimmage(frame_rows)
        is_still = motion.get(frame, 0.0) < PRE_SNAP_MAX_DISPLACEMENT_FT
        if los is None or not is_still:
            continue
        offense_defense_split(frame_rows, los)
        presnap.append(frame_rows)
        los_resolved += 1
        if formation_family(formation_features(frame_rows)) != "UNKNOWN":
            formation_filled += 1
    min_players = int(_FOOTBALL["min_players"])
    presnap_counts = [len(frame_rows) for frame_rows in presnap]
    presnap_total = len(presnap)
    presnap_coverage = (sum(count >= min_players for count in presnap_counts) / presnap_total
                         if presnap_total else 0.0)
    ungated = sum(len(per_frame.get_group(frame)) >= min_players if frame in per_frame.groups else False
                  for frame in frames) / len(frames)
    median = float(np.median(presnap_counts)) if presnap_counts else 0.0
    report = DepthReport(
        str(source), "football", len(rows), len(frames),
        round(presnap_total / len(frames), 4),
        round(los_resolved / presnap_total, 4) if presnap_total else 0.0,
        round(median, 2), round(formation_filled / presnap_total, 4) if presnap_total else 0.0,
        round(presnap_coverage, 4), round(float(ungated), 4), "C",
    )
    return DepthReport(
        source=report.source, sport=report.sport, rows=report.rows, frames=report.frames,
        pct_frames_presnap_view=report.pct_frames_presnap_view,
        pct_frames_los_resolved=report.pct_frames_los_resolved,
        median_players_per_presnap_frame=report.median_players_per_presnap_frame,
        formation_family_fill_rate=report.formation_family_fill_rate,
        pct_frames_presnap_coverage=report.pct_frames_presnap_coverage,
        ungated_harness_coverage=report.ungated_harness_coverage,
        depth_grade=_grade(report.pct_frames_presnap_coverage,
                           report.pct_frames_los_resolved,
                           report.median_players_per_presnap_frame,
                           report.formation_family_fill_rate),
    )


def quality_probe(path: str | Path) -> DepthReport:
    """Read a football tracking CSV and return its pre-snap depth report."""
    source = Path(path)
    return measure_dataframe(pd.read_csv(source), source=str(source))
