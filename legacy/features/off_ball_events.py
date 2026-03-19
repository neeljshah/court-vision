# Compatibility re-export — source of truth is src/analytics/off_ball_events.py
from src.analytics.off_ball_events import (  # noqa: F401
    detect_off_ball_events,
    CUT_SPEED_THRESHOLD,
    SCREEN_SPEED_THRESHOLD,
    SCREEN_PROXIMITY,
    DRIFT_SPEED_MIN,
    DRIFT_SPEED_MAX,
)
