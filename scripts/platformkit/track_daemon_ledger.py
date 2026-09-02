"""Append-only ledger entry builders for the tracking daemon."""
from __future__ import annotations

import time


def corrupt_entry(game_id: str, sport: str, size: int, retained: bool) -> dict:
    """Describe one invalid staged file, including failed-retain recovery."""
    heads = ["staged file is %d bytes, not a video" % size]
    if not retained:
        heads.append("retain_failed: staged source renamed .failed")
    return {"game_id": game_id, "sport": sport, "status": "corrupt",
            "adjudicated": False, "retain_failed": not retained, "rows": 0,
            "passed": None, "failure_heads": heads, "failures": heads,
            "coverage_pct": None, "coordinate_space": None, "rung": None,
            "evaluated_at": None, "seconds": 0, "finished_at": int(time.time())}
