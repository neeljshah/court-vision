"""
build_xfg_baseline.py — Phase 41: xFG regression-detection baseline.

For each player with available shot-chart data, computes:
    actual_fg   = actual FG% from shot outcomes
    expected_fg = mean xFG predicted by xfg_v1 model over those shots
    gap         = actual_fg - expected_fg   (positive = outperforming model)

Output: data/nba/player_xfg_gaps.json
    {
      "<player_id>": {
        "actual_fg": 0.xxx,
        "expected_fg": 0.xxx,
        "gap": 0.xxx,
        "n_shots": int,
        "player_name": "..."   # best available; may be empty string
      },
      ...
    }

Exits 0 in all cases. Writes an empty dict {} if no data is available.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, Optional

import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

NBA_DIR    = os.path.join(PROJECT_DIR, "data", "nba")
MODEL_PATH = os.path.join(PROJECT_DIR, "data", "models", "xfg_v1.pkl")
OUT_PATH   = os.path.join(NBA_DIR, "player_xfg_gaps.json")

logging.basicConfig(level=logging.INFO, format="[xfg-baseline] %(message)s")
log = logging.getLogger(__name__)


def _load_xfg_model(model_path: str) -> Any:
    """Load xFG model from disk. Exposed at module level for test patching."""
    from src.prediction.xfg_model import load as _load
    return _load(model_path)


# ── data loading ──────────────────────────────────────────────────────────────

def _load_shot_charts() -> pd.DataFrame:
    """
    Load all shot_chart_*.json files from data/nba/.

    Returns empty DataFrame if none found.
    Shot chart keys are upper-cased (NBA API format).
    """
    import glob

    files = sorted(glob.glob(os.path.join(NBA_DIR, "shot_chart_*.json")))
    if not files:
        log.warning("No shot_chart_*.json files found in %s", NBA_DIR)
        return pd.DataFrame()

    frames = []
    for fpath in files:
        try:
            with open(fpath, encoding="utf-8") as fh:
                data = json.load(fh)
            if data:
                frames.append(pd.DataFrame(data))
        except Exception as exc:
            log.warning("Skipping %s: %s", fpath, exc)

    if not frames:
        log.warning("All shot_chart files were empty or unreadable")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    log.info("Loaded %d shots from %d file(s)", len(df), len(files))
    return df


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case column names to match xfg_model expectations."""
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    # Rename NBA API uppercase fields to the xfg_model lower-case names
    rename_map = {
        "shot_zone_basic": "shot_zone_basic",  # already matches
        "shot_zone_area":  "shot_zone_area",
        "shot_zone_range": "shot_zone_range",
        "shot_distance":   "shot_distance",
        "shot_type":       "shot_type",
        "action_type":     "action_type",
        "shot_made_flag":  "shot_made_flag",
        "player_id":       "player_id",
        "player_name":     "player_name",
    }
    # All the relevant columns are already lower-cased by the step above;
    # just ensure required ones exist.
    return df


# ── core computation ───────────────────────────────────────────────────────────

def build_baseline(
    df: pd.DataFrame,
    model: Optional[Any] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Compute per-player xFG gap from shot-chart DataFrame.

    Args:
        df:    Normalised shot-chart DataFrame (lower-cased columns).
        model: Pre-loaded XFGModel instance. If None, loads from MODEL_PATH.
               Pass a mock here for unit tests to avoid disk I/O.

    Returns:
        Dict keyed by str(player_id) with actual_fg, expected_fg, gap, n_shots,
        player_name.
    """
    required = {"player_id", "shot_made_flag",
                "shot_zone_basic", "shot_zone_area", "shot_zone_range",
                "shot_distance", "shot_type", "action_type"}
    missing = required - set(df.columns)
    if missing:
        log.warning("Shot data missing columns %s — returning empty baseline", missing)
        return {}

    df = df.copy()
    df["shot_made_flag"] = pd.to_numeric(df["shot_made_flag"], errors="coerce")
    df = df.dropna(subset=["shot_made_flag", "player_id"])
    if df.empty:
        log.warning("No valid shots after filtering — returning empty baseline")
        return {}

    # Load model if not supplied
    if model is None:
        model = _load_xfg_model(MODEL_PATH)

    # Predict xFG for every shot
    df["xfg"] = model.predict_batch(df)

    result: Dict[str, Dict[str, Any]] = {}
    for pid, grp in df.groupby("player_id"):
        n = len(grp)
        actual_fg   = float(grp["shot_made_flag"].mean())
        expected_fg = float(grp["xfg"].mean())
        gap         = round(actual_fg - expected_fg, 4)
        name = ""
        if "player_name" in grp.columns:
            name_vals = grp["player_name"].dropna()
            if not name_vals.empty:
                name = str(name_vals.iloc[0])
        result[str(pid)] = {
            "actual_fg":   round(actual_fg,   4),
            "expected_fg": round(expected_fg, 4),
            "gap":         gap,
            "n_shots":     n,
            "player_name": name,
        }

    log.info("Built baseline for %d player(s)", len(result))
    return result


# ── I/O ───────────────────────────────────────────────────────────────────────

def write_output(baseline: Dict[str, Dict[str, Any]]) -> None:
    """Write baseline dict to OUT_PATH as pretty-printed JSON."""
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    log.info("Wrote %d player records -> %s", len(baseline), OUT_PATH)


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """Build the per-player xFG gap baseline and write JSON output."""
    df = _load_shot_charts()

    if df.empty:
        log.info("No shot data available — writing empty baseline")
        write_output({})
        return

    df = _normalise_columns(df)
    baseline = build_baseline(df)
    write_output(baseline)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log.error("Unexpected error: %s", exc, exc_info=True)
        # Still write an empty baseline so downstream tools see a valid file
        write_output({})
        sys.exit(0)
