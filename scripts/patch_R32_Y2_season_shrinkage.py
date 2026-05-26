"""patch_R32_Y2_season_shrinkage.py — R32_Y2 season-progress shrinkage patch.

Apply ``src.prediction.season_progress_shrinkage`` to the 22 window-artifact
features in a season_games file. Idempotent via ``season_shrinkage_R32_Y2``
marker.

The shrinkage POST-processes already-computed leak-free expanding-window
values. It dampens early-season noise by mixing each value with the
historical league mean using weight ``(1 - elapsed_frac) ** alpha``.

Why
---
Drift detector R27_T3 reports drift_major for features like
``home_top_lineup_net_rtg`` (cur_mean=28.15 vs ref_mean=4.22). The
reference distribution is end-of-season-stabilized; current distribution
is mid-season noisy. Shrinking each row's value toward the reference
mean by the fraction of season unplayed brings the distributions into
alignment without touching the leak-free computation.

CLI
---
    python scripts/patch_R32_Y2_season_shrinkage.py
    python scripts/patch_R32_Y2_season_shrinkage.py --season 2025-26 --force
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from src.prediction.season_progress_shrinkage import (  # noqa: E402
    DEFAULT_TOTAL_GAMES,
    DEFAULT_WINDOW_ARTIFACT_FEATURES,
    SHRINKAGE_CONFIG,
    apply_shrinkage_to_rows,
)

SEASON_DEFAULT = "2025-26"
MARKER_KEY = "season_shrinkage_R32_Y2"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, path)


def patch_file(
    season_games_path: Path,
    *,
    backup_path: Optional[Path] = None,
    write_marker: bool = True,
    force: bool = False,
    total_games: int = DEFAULT_TOTAL_GAMES,
    config: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """Apply R32_Y2 season-progress shrinkage to season_games file."""
    if not season_games_path.exists():
        return {"status": "BLOCKED", "reason": f"missing {season_games_path}"}
    with open(season_games_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    is_dict = isinstance(payload, dict)
    rows: List[Dict[str, Any]] = payload["rows"] if is_dict and "rows" in payload \
        else (list(payload) if isinstance(payload, list) else [])
    if not rows:
        return {"status": "BLOCKED", "reason": "season_games file has no rows"}

    if is_dict and not force and isinstance(payload.get(MARKER_KEY), dict):
        return {"status": "ALREADY_APPLIED", "marker": payload[MARKER_KEY]}

    if backup_path is not None and not backup_path.exists():
        try:
            shutil.copy2(season_games_path, backup_path)
        except Exception:
            pass

    summary = apply_shrinkage_to_rows(
        rows,
        features=DEFAULT_WINDOW_ARTIFACT_FEATURES,
        config=config or SHRINKAGE_CONFIG,
        total_games=total_games,
    )

    if is_dict:
        payload["rows"] = rows
        if write_marker:
            payload[MARKER_KEY] = {
                "applied_at":  _iso_now(),
                "n_rows":      len(rows),
                "n_features":  summary["n_features"],
                "features":    sorted(summary["per_feature"].keys()),
                "total_games": int(total_games),
                "per_feature": summary["per_feature"],
            }
    else:
        payload = rows

    _atomic_write(season_games_path, payload)
    summary["status"] = "OK"
    summary["n_rows_patched"] = len(rows)
    summary["features"] = sorted(summary["per_feature"].keys())
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(
        description="R32_Y2 season-progress shrinkage for window-artifact features."
    )
    ap.add_argument("--season", default=SEASON_DEFAULT)
    ap.add_argument("--data-root", default=str(PROJECT_DIR / "data"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--total-games", type=int, default=DEFAULT_TOTAL_GAMES)
    args = ap.parse_args()

    data_root = Path(args.data_root)
    sg = data_root / "nba" / f"season_games_{args.season}.json"
    bk = sg.with_suffix(sg.suffix + ".bak_R32_Y2")

    t0 = time.time()
    print(f"=== R32_Y2 season-progress shrinkage ===")
    print(f"  season_games: {sg}")
    print(f"  backup:       {bk}")
    res = patch_file(
        sg, backup_path=bk, force=args.force,
        total_games=int(args.total_games),
    )
    print(f"  result: {json.dumps(res, default=str, indent=2)}")
    print(f"  elapsed: {time.time() - t0:.2f}s")
    return 0 if res.get("status") in ("OK", "ALREADY_APPLIED") else 1


if __name__ == "__main__":
    sys.exit(main())
