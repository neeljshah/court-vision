"""scoreboard_history -- longitudinal log of headline calibration numbers.

Appends one row per (source generated_at, sport, method) to
data/cache/scoreboard_history.jsonl each time the calibration scoreboard is
regenerated. Dedup by key so re-runs are idempotent. Report-only; calibration
metrics only, no $ / edge fields anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
# M17: canonical refreshed path (calibration_refresh_job keeps this <=72h old);
# fall back to the retired one-shot wave21 artifact only if latest is absent.
# Resolved lazily (not a frozen module-level constant) so a long-running
# daemon process sees _LATEST the moment calibration_refresh_job creates it.
_LATEST = REPO / "data" / "frontend" / "ops" / "calibration_scoreboard_latest.json"
SOURCE = REPO / "data" / "frontend" / "ops" / "calibration_scoreboard_wave21.json"
HISTORY = REPO / "data" / "cache" / "scoreboard_history.jsonl"


def _resolve_source() -> Path:
    return _LATEST if _LATEST.exists() else SOURCE


def _seen_keys(history_path: Path) -> set:
    keys = set()
    if history_path.exists():
        for line in history_path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                keys.add((r.get("source_generated_at"), r.get("sport"), r.get("model_tag")))
            except Exception:
                continue
    return keys


def append_rows(source_path: Optional[Path] = None,
                history_path: Optional[Path] = None) -> Dict[str, Any]:
    """Append new per-sport calibration rows; idempotent. Returns summary."""
    src = source_path or _resolve_source()
    hist = history_path or HISTORY
    if not src.exists():
        return {"status": "no_source", "appended": 0}
    doc = json.loads(src.read_text(encoding="utf-8"))
    gen = doc.get("generated_at")
    per_sport: List[Dict[str, Any]] = (
        doc.get("calibration_scoreboard", {}).get("per_sport", []) or [])
    seen = _seen_keys(hist)
    hist.parent.mkdir(parents=True, exist_ok=True)
    appended = 0
    with hist.open("a", encoding="utf-8") as fh:
        for row in per_sport:
            key = (gen, row.get("sport"), row.get("method"))
            if key in seen:
                continue
            fh.write(json.dumps({
                "source_generated_at": gen,
                "sport": row.get("sport"),
                "n": row.get("n"),
                "baseline_brier": row.get("baseline_brier"),
                "improved_brier": row.get("improved_brier"),
                "baseline_ece": row.get("baseline_ece"),
                "improved_ece": row.get("improved_ece"),
                "model_tag": row.get("method"),
                "note": "calibration metrics only; not an edge claim",
            }, ensure_ascii=True) + "\n")
            seen.add(key)
            appended += 1
    return {"status": "ok", "appended": appended, "history": str(hist)}


if __name__ == "__main__":
    print(json.dumps(append_rows(), ensure_ascii=True))
