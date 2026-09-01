"""Team-game features derived from NBA screen-candidate events.

Honest scope
------------
Upstream detection (``screens.detect_screens``) is SCREEN-CANDIDATE detection:
a same-team teammate parked near the ball handler. It carries NO defender
coverage classification (over / under / switch / hedge / blitz), so a
"screen" here may be any stationary teammate convergence.

Every feature below is therefore DESCRIPTIVE -- a summary of what the tracking
saw. None has been shown to add prediction lift; that verdict is pending a
foundry validation run, and until then these must not be treated as validated
signals.

Leak discipline: these describe the game they were computed from. Anything
downstream that predicts a game outcome must lag them (shift before roll) so
only prior-game values are visible as-of tip-off.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from domains.basketball_nba.tracking.screens import detect_screens

COURT_LENGTH_FT = 94.0
COURT_WIDTH_FT = 50.0

# Zone cuts on the folded half-court frame (distance from the nearest baseline,
# lateral offset from the midline). Corners sit below the free-throw-line
# extended and outside the lane; "top" is the lane-wide band through the middle.
CORNER_MAX_BASELINE_FT = 14.0
CORNER_MIN_LATERAL_FT = 14.0
TOP_MAX_LATERAL_FT = 8.0

ZONES = ("top", "wing", "corner")

FEATURE_COLUMNS = [
    "screen_candidate_count",
    "screen_rate_per_min",
    "screen_zone_share_top",
    "screen_zone_share_wing",
    "screen_zone_share_corner",
    "screen_handler_hhi",
]


def court_zone(x: float, y: float) -> str:
    """Classify a screen location into ``top`` / ``wing`` / ``corner``.

    Uses the 94x50 foot court convention. The court is folded about half-court
    so that a screen is described relative to whichever basket it is nearest.
    """
    x = min(max(float(x), 0.0), COURT_LENGTH_FT)
    y = min(max(float(y), 0.0), COURT_WIDTH_FT)
    from_baseline = min(x, COURT_LENGTH_FT - x)
    from_midline = abs(y - COURT_WIDTH_FT / 2.0)
    if from_baseline <= CORNER_MAX_BASELINE_FT and from_midline >= CORNER_MIN_LATERAL_FT:
        return "corner"
    if from_midline <= TOP_MAX_LATERAL_FT:
        return "top"
    return "wing"


def screen_rate(events: pd.DataFrame, n_frames: int, fps: float) -> float:
    """Screen candidates per minute of tracked footage."""
    if fps <= 0:
        raise ValueError("fps must be positive")
    if n_frames <= 0:
        raise ValueError("n_frames must be positive")
    minutes = float(n_frames) / float(fps) / 60.0
    return float(len(events)) / minutes


def screen_location_mix(events: pd.DataFrame) -> dict[str, float]:
    """Share of screen candidates by court zone; shares sum to 1.0 (0.0 if empty)."""
    mix = {zone: 0.0 for zone in ZONES}
    if events.empty or not {"x", "y"}.issubset(events.columns):
        return mix
    located = events[["x", "y"]].dropna()
    if located.empty:
        return mix
    zones = [court_zone(row.x, row.y) for row in located.itertuples()]
    total = float(len(zones))
    for zone in zones:
        mix[zone] += 1.0 / total
    return mix


def screen_handler_concentration(events: pd.DataFrame) -> float:
    """Herfindahl index over handler ids: 1.0 = one handler, lower when split.

    Returns 0.0 for an empty event set (no offense observed, not "spread out").
    """
    if events.empty or "handler_id" not in events.columns:
        return 0.0
    handlers = events["handler_id"].dropna()
    if handlers.empty:
        return 0.0
    shares = handlers.value_counts(normalize=True)
    return float(shares.pow(2).sum())


def features_from_events(events: pd.DataFrame, n_frames: int, fps: float) -> pd.DataFrame:
    """Assemble one row of ``screen_`` features from already-detected events."""
    mix = screen_location_mix(events)
    row = {
        "screen_candidate_count": int(len(events)),
        "screen_rate_per_min": screen_rate(events, n_frames, fps),
        "screen_zone_share_top": mix["top"],
        "screen_zone_share_wing": mix["wing"],
        "screen_zone_share_corner": mix["corner"],
        "screen_handler_hhi": screen_handler_concentration(events),
    }
    return pd.DataFrame([row], columns=FEATURE_COLUMNS)


def game_features(tracking_csv_path: str | Path, fps: float = 30.0,
                  min_frames: int = 8) -> pd.DataFrame:
    """Read one game's tracking CSV and return its single-row ``screen_`` features.

    ``n_frames`` is the observed frame span of the file, so the rate is per
    minute of TRACKED footage -- not per minute of game clock. A partially
    tracked game is a partial description, not a smaller number of screens.
    """
    df = pd.read_csv(tracking_csv_path)
    frames = pd.to_numeric(df["frame"], errors="coerce").dropna()
    if frames.empty:
        raise ValueError("Tracking file has no usable frame column")
    n_frames = int(frames.max() - frames.min()) + 1
    events = detect_screens(df, fps=fps, min_frames=min_frames)
    return features_from_events(events, n_frames, fps)
