"""tracker_config.py — Load tunable tracker parameters from config/tracker_params.json."""
import json
import os
from typing import Any, Dict

_PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_CONFIG_PATH = os.path.join(_PROJECT_DIR, "config", "tracker_params.json")

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
    # OSNet pre-trained weights (absolute path — silently skipped if file not found)
    "osnet_weights_path":    os.path.join(_PROJECT_DIR, "data", "models", "osnet_x0_25_imagenet.pth"),
    # YOLO model stem and image size — override for post-game high-quality runs
    "yolo_model":            "yolov8n",
    "yolo_imgsz":            640,
}

# Applied when TRACKER_POST_GAME=1 env var is set.
# Trades ~3× slower inference for 87%→94% detection accuracy.
_POST_GAME_OVERRIDES: Dict[str, Any] = {
    "yolo_model":     "yolov8x",
    "yolo_imgsz":     1280,
    "conf_threshold": 0.25,
}


def load_config() -> Dict[str, Any]:
    """Return config dict merged over DEFAULTS. Always returns all keys.

    If env var TRACKER_POST_GAME=1 is set, post-game quality overrides are
    applied on top (yolov8x, imgsz=1280, lower conf_threshold).
    """
    cfg = DEFAULTS.copy()
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH) as f:
            file_cfg = json.load(f)
            # Strip internal comment keys (prefixed with _)
            cfg.update({k: v for k, v in file_cfg.items() if not k.startswith("_")})
    if os.environ.get("TRACKER_POST_GAME", "").strip() == "1":
        cfg.update(_POST_GAME_OVERRIDES)
    return cfg


def save_config(params: Dict[str, Any]):
    """Write params to config file, creating directory if needed."""
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(params, f, indent=2)
