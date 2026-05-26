"""probe_R32_Y2_shrinkage.py — R32_Y2 season-progress shrinkage probe.

Procedure
---------
1. Resolve a data root that has the current 2025-26 season + at least one
   historical reference (mirrors R27_T3 / R31_X6 probes).
2. Run R27_T3 drift detector BEFORE applying shrinkage; capture
   n_drift_major / n_drift_minor / n_stable plus the per-feature
   classification for the 22 window-artifact features.
3. Copy season_games_2025-26.json to a temp file; apply
   patch_R32_Y2_season_shrinkage to the copy (NEVER mutates the live file).
4. Reload the drift detector against the shrunk copy and capture the same
   counts + per-feature deltas.
5. Persist summary to data/cache/probe_R32_Y2_results.json.
6. Verdict: SHIP if drift_count_after <= drift_count_before - 5 AND the
   shrinkage actually touched all 22 features. Otherwise PARTIAL.

Safety
------
* No network, no subprocess.
* The live season_games file is NEVER mutated by the probe — only a copy.
* The actual backfill wiring writes to the live file separately; this
  probe just measures the shrinkage delta.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402

from scripts.feature_drift_detector import (  # noqa: E402
    _CURRENT_SEASON,
    _REFERENCE_SEASONS,
    detect_drift,
    load_m2_dataframe,
    m2_feature_columns,
    select_current_window,
)
from scripts.patch_R32_Y2_season_shrinkage import patch_file  # noqa: E402
from src.prediction.season_progress_shrinkage import (  # noqa: E402
    DEFAULT_WINDOW_ARTIFACT_FEATURES,
)

PROBE_RESULTS_PATH = _ROOT / "data" / "cache" / "probe_R32_Y2_results.json"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_data_root(explicit: str = "") -> Path:
    cands: List[Path] = []
    if explicit:
        cands.append(Path(explicit))
    env = os.environ.get("NBA_AI_ROOT")
    if env:
        cands.append(Path(env) / "data")
    cands.append(_ROOT / "data")
    cands.append(Path(r"C:\Users\neelj\nba-ai-system") / "data")
    for c in cands:
        cur = c / "nba" / f"season_games_{_CURRENT_SEASON}.json"
        anyref = any(
            (c / "nba" / f"season_games_{s}.json").exists()
            for s in _REFERENCE_SEASONS
        )
        if cur.exists() and anyref:
            return c
    for c in cands:
        if (c / "nba" / f"season_games_{_CURRENT_SEASON}.json").exists():
            return c
    return _ROOT / "data"


def _per_feature_class_map(features: List[Dict[str, Any]]) -> Dict[str, str]:
    return {str(f.get("feature", "")): str(f.get("class", "")) for f in features}


def _run_drift_with_override(
    data_root: Path, current_season_file: Path, current_days: int,
) -> Dict[str, Any]:
    """Run m2 drift detector but feed an EXPLICIT current-season file path
    (so we can swap in the shrunk copy). Loads reference from the real
    data_root as usual.
    """
    ref = load_m2_dataframe(_REFERENCE_SEASONS, data_root)
    # Load the override 2025-26 file manually.
    with open(current_season_file, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    rows = payload["rows"] if isinstance(payload, dict) else payload
    cur_all = pd.DataFrame(rows)
    if "game_date" in cur_all.columns:
        cur_all["game_date"] = pd.to_datetime(cur_all["game_date"], errors="coerce")
    cur = select_current_window(cur_all, current_days=current_days)
    cols = m2_feature_columns(ref)
    if ref.empty or cur.empty or not cols:
        return {
            "n_features_analyzed": 0, "n_stable": 0,
            "n_drift_minor": 0, "n_drift_major": 0, "features": [],
            "status": "BLOCKED",
        }
    res = detect_drift(ref, cur, cols)
    res["status"] = "OK"
    return res


def _per_window_artifact_status(
    per_feature: Dict[str, str],
) -> Dict[str, str]:
    """Filter per-feature class map down to the 22 window-artifact features."""
    return {
        feat: per_feature.get(feat, "missing")
        for feat in sorted(DEFAULT_WINDOW_ARTIFACT_FEATURES)
    }


def run(data_root: Path, current_days: int = 14) -> Dict[str, Any]:
    sg = data_root / "nba" / f"season_games_{_CURRENT_SEASON}.json"

    # --- BEFORE
    before = _run_drift_with_override(data_root, sg, current_days)
    before_per_class = _per_feature_class_map(before.get("features", []))

    # --- Apply shrinkage on a COPY (never mutate live file)
    tmp_dir = Path(tempfile.mkdtemp(prefix="r32_y2_"))
    shrunk_path = tmp_dir / sg.name
    shutil.copy2(sg, shrunk_path)
    patch_res = patch_file(shrunk_path, force=True)

    # --- AFTER
    after = _run_drift_with_override(data_root, shrunk_path, current_days)
    after_per_class = _per_feature_class_map(after.get("features", []))

    # Per-feature delta for the 22 targeted features.
    delta_table: List[Dict[str, str]] = []
    moved_out_of_major = 0
    for feat in sorted(DEFAULT_WINDOW_ARTIFACT_FEATURES):
        b = before_per_class.get(feat, "missing")
        a = after_per_class.get(feat, "missing")
        delta_table.append({"feature": feat, "before": b, "after": a})
        if b == "drift_major" and a != "drift_major":
            moved_out_of_major += 1

    n_before = int(before.get("n_drift_major", 0))
    n_after = int(after.get("n_drift_major", 0))

    n_features_shrunk = int((patch_res.get("n_features") or 0)
                            if isinstance(patch_res, dict) else 0)

    delta = n_before - n_after
    # Ship gate: drift drops by >=5 AND we shrunk at least the 22 canonical
    # R29_V3 window-artifact features (24 = 22 R29_V3 + 2 R31_X6 lineup).
    verdict = "SHIP" if delta >= 5 and n_features_shrunk >= 22 else "PARTIAL"

    # Try to clean up the temp dir (best-effort).
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    return {
        "probe":                "R32_Y2",
        "ts":                   _iso_now(),
        "data_root":            str(data_root),
        "current_days":         int(current_days),
        "drift_count_before":   n_before,
        "drift_count_after":    n_after,
        "drift_count_delta":    delta,
        "n_features_shrunk":    n_features_shrunk,
        "moved_out_of_major_count": moved_out_of_major,
        "pre_drift": {
            "n_major":  int(before.get("n_drift_major", 0)),
            "n_minor":  int(before.get("n_drift_minor", 0)),
            "n_stable": int(before.get("n_stable", 0)),
            "n_analyzed": int(before.get("n_features_analyzed", 0)),
        },
        "post_drift": {
            "n_major":  int(after.get("n_drift_major", 0)),
            "n_minor":  int(after.get("n_drift_minor", 0)),
            "n_stable": int(after.get("n_stable", 0)),
            "n_analyzed": int(after.get("n_features_analyzed", 0)),
        },
        "per_feature_delta":    delta_table,
        "shrunk_features":      sorted(DEFAULT_WINDOW_ARTIFACT_FEATURES),
        "patch_summary":        {
            "status":     patch_res.get("status") if isinstance(patch_res, dict) else None,
            "n_rows_patched": patch_res.get("n_rows_patched") if isinstance(patch_res, dict) else None,
            "n_features": patch_res.get("n_features") if isinstance(patch_res, dict) else None,
        },
        "verdict":              verdict,
        "ship_ok":              verdict == "SHIP",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--current-days", type=int, default=14)
    ap.add_argument("--data-root", type=str, default="")
    args = ap.parse_args()

    data_root = _resolve_data_root(args.data_root)
    summary = run(data_root, current_days=int(args.current_days))

    PROBE_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)

    print(json.dumps({
        "probe":                  summary["probe"],
        "verdict":                summary["verdict"],
        "drift_count_before":     summary["drift_count_before"],
        "drift_count_after":      summary["drift_count_after"],
        "drift_count_delta":      summary["drift_count_delta"],
        "n_features_shrunk":      summary["n_features_shrunk"],
        "moved_out_of_major":     summary["moved_out_of_major_count"],
    }, indent=2, default=str))
    return 0 if summary["ship_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
