"""probe_R27_T3_drift_detector.py — R27_T3 end-to-end probe against real data.

Procedure
---------
1. Resolve a data root that has at least one historical season + the
   current 2025-26 season on disk (allows running from a worktree by
   falling back to the canonical main repo path).
2. Run the drift detector for each feature set (``m2``, ``prop_pergame``).
3. Capture n_features_analyzed / n_stable / n_minor / n_major and the top-5
   most-drifted features (with KS stat + p-value + mean z).
4. Persist a single summary JSON to
   ``data/cache/probe_R27_T3_results.json``.
5. Exit non-zero if neither feature set produces a usable analysis.

Safety
------
* No network. No subprocess. No alerts fired (alerter is not invoked).
* Read-only on data files; only writes a single results JSON.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.feature_drift_detector import (  # noqa: E402
    _CURRENT_SEASON,
    _REFERENCE_SEASONS,
    run as run_drift,
)

PROBE_RESULTS_PATH = _ROOT / "data" / "cache" / "probe_R27_T3_results.json"


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
    # Fall back to whichever has the current season — detector will BLOCK
    # gracefully if there isn't a usable reference.
    for c in cands:
        if (c / "nba" / f"season_games_{_CURRENT_SEASON}.json").exists():
            return c
    return _ROOT / "data"


def _top5(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in features[:5]:
        out.append({
            "feature":  str(r.get("feature", "")),
            "class":    str(r.get("class", "")),
            "ks_stat":  r.get("ks_stat"),
            "p_value":  r.get("p_value"),
            "mean_z":   r.get("mean_z"),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--current-days", type=int, default=14,
                    help="Window for current data (default 14 days).")
    ap.add_argument("--data-root", type=str, default="",
                    help="Override the data root (defaults to NBA_AI_ROOT "
                         "or the canonical main-repo path).")
    args = ap.parse_args()

    data_root = _resolve_data_root(args.data_root)

    per_set: Dict[str, Dict[str, Any]] = {}
    raised = False
    error_repr = ""

    for fs in ("m2", "prop_pergame"):
        try:
            report = run_drift(
                feature_set=fs,
                current_days=int(args.current_days),
                data_root=data_root,
            )
        except Exception as exc:  # noqa: BLE001
            raised = True
            error_repr = repr(exc)
            traceback.print_exc()
            per_set[fs] = {"status": "ERROR", "error": repr(exc)}
            continue
        per_set[fs] = {
            "status":              report.get("status"),
            "blocked_reason":      report.get("blocked_reason", ""),
            "n_reference":         int(report.get("n_reference", 0) or 0),
            "n_current":           int(report.get("n_current", 0) or 0),
            "n_features_analyzed": int(report.get("n_features_analyzed", 0) or 0),
            "n_stable":            int(report.get("n_stable", 0) or 0),
            "n_drift_minor":       int(report.get("n_drift_minor", 0) or 0),
            "n_drift_major":       int(report.get("n_drift_major", 0) or 0),
            "top_5_drifted":       _top5(list(report.get("features") or [])),
        }

    # Ship gate: at least one feature set analyzed >=1 feature with stats.
    any_analyzed = any(
        (v.get("n_features_analyzed", 0) or 0) >= 1 for v in per_set.values()
    )
    ship_ok = (not raised) and any_analyzed

    summary = {
        "probe":         "R27_T3",
        "ts":            _iso_now(),
        "data_root":     str(data_root),
        "current_days":  int(args.current_days),
        "per_set":       per_set,
        "ship_ok":       ship_ok,
        "raised":        raised,
        "error_repr":    error_repr,
    }

    PROBE_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))
    return 0 if ship_ok else 1


if __name__ == "__main__":
    sys.exit(main())
