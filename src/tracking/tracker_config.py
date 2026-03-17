"""tracker_config.py — Load tunable tracker parameters from config/tracker_params.json."""
import json
import os
from typing import Any, Dict

_CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "tracker_params.json")
)

DEFAULTS: Dict[str, Any] = {
    "conf_threshold":        0.3,
    "broadcast_mode":        True,   # lower conf threshold for distant/small players on broadcast footage
    "topcut":                320,
    "appearance_w":          0.25,
    "max_lost_frames":       90,
    "min_gameplay_persons":  5,
    # Re-ID tuning
    "reid_threshold":        0.45,   # max appearance distance to accept re-ID
    "gallery_ttl":           300,    # frames a gallery entry stays valid
    "kalman_fill_window":    5,      # Kalman gap-fill: fill if lost_age <= this
}


def load_config() -> Dict[str, Any]:
    """Return config dict merged over DEFAULTS. Always returns all keys."""
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH) as f:
            return {**DEFAULTS, **json.load(f)}
    return DEFAULTS.copy()


def save_config(params: Dict[str, Any]):
    """Write params to config file, creating directory if needed."""
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(params, f, indent=2)
