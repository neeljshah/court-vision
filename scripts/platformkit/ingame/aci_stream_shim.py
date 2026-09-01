"""Paper-only persistence and serving seam for online ACI calibration.

Reads settled grade rows in tick-timestamp order, persists one alpha state per
sport/segment, and adjusts only an already-produced static interval.  It never
creates a band or infers an outcome; rows without both are ignored.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from scripts.platformkit.ingame.aci_online import (
    _DEFAULT_ALPHA_TARGET, _MIN_STREAM_LEN, aci_update, apply_aci_to_band,
)

logger = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO / "data" / "cache" / "ingame_grade"
DEFAULT_STATE_DIR = _REPO / "data" / "cache" / "ingame_aci"


def state_path(sport: str, segment: str, state_dir: Optional[Path] = None) -> Path:
    """Return the one persisted ACI state path for a sport/segment stream."""
    base = Path(state_dir) if state_dir is not None else DEFAULT_STATE_DIR
    return base / ("%s_%s.json" % (str(sport).lower(), str(segment).lower()))


def _load(path: Path) -> Dict[str, Any]:
    default = {"alpha_t": _DEFAULT_ALPHA_TARGET, "n_graded": 0, "seen": []}
    try:
        doc = json.loads(path.read_text(encoding="ascii"))
        if not isinstance(doc, dict):
            return default
        alpha = float(doc.get("alpha_t", _DEFAULT_ALPHA_TARGET))
        return {"alpha_t": max(0.0, min(1.0, alpha)),
                "n_graded": max(0, int(doc.get("n_graded", 0))),
                "seen": list(doc.get("seen", []))}
    except (OSError, ValueError, TypeError):
        return default


def _write(path: Path, doc: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=True, sort_keys=True), encoding="ascii")
    os.replace(str(tmp), str(path))


def load_alpha(sport: str, segment: str = "all", *,
               state_dir: Optional[Path] = None) -> float:
    """Read alpha_t, returning the target alpha when no valid state exists."""
    return float(_load(state_path(sport, segment, state_dir))["alpha_t"])


def _num(row: Dict[str, Any], keys: Iterable[str]) -> Optional[float]:
    for key in keys:
        try:
            return float(row[key])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _band(row: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    lo = _num(row, ("lo", "static_lo", "base_lo", "interval_lo"))
    hi = _num(row, ("hi", "static_hi", "base_hi", "interval_hi"))
    if lo is None or hi is None or lo > hi:
        return None
    return lo, hi


def _resolved_rows(sport: str, segment: str, grade_dir: Path) -> List[Tuple[str, Dict[str, Any]]]:
    rows: List[Tuple[str, Dict[str, Any]]] = []
    for path in sorted((grade_dir / sport).glob("*.jsonl")) if (grade_dir / sport).is_dir() else []:
        try:
            raw_rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, ValueError):
            continue
        outcome = next((_num(r, ("outcome", "home_win")) for r in raw_rows[::-1]
                        if isinstance(r, dict) and _num(r, ("outcome", "home_win")) in (0.0, 1.0)), None)
        if outcome is None:
            continue
        for index, row in enumerate(raw_rows):
            if not isinstance(row, dict) or str(row.get("segment", "all")).lower() != segment.lower():
                continue
            band = _band(row)
            if band is None:
                continue
            key = "%s:%s:%d" % (path.stem, str(row.get("ts", "")), index)
            rows.append((key, {"ts": str(row.get("ts", "")), "lo": band[0], "hi": band[1], "y": outcome}))
    return sorted(rows, key=lambda item: (item[1]["ts"], item[0]))


def update_stream(sport: str, segment: str = "all", *, grade_dir: Optional[Path] = None,
                  state_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Apply unseen settled ticks in timestamp order and persist the ACI state."""
    path = state_path(sport, segment, state_dir)
    state = _load(path)
    seen = set(str(v) for v in state["seen"])
    fresh = [(key, row) for key, row in _resolved_rows(str(sport).lower(), segment,
             Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR) if key not in seen]
    for key, row in fresh:
        state["n_graded"] += 1
        if state["n_graded"] > _MIN_STREAM_LEN:
            err = int(not (row["lo"] <= row["y"] <= row["hi"]))
            state["alpha_t"] = aci_update(state["alpha_t"], err)
        seen.add(key)
    state["seen"] = sorted(seen)
    if fresh:
        _write(path, state)
    return {"alpha_t": float(state["alpha_t"]), "n_graded": state["n_graded"],
            "n_updated": len(fresh)}


def apply_to_document(doc: Dict[str, Any], sport: str, segment: str = "all", *,
                      state_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Apply current ACI alpha to a document's pre-existing static_interval block."""
    out = dict(doc)
    band_doc = out.get("static_interval")
    if not isinstance(band_doc, dict):
        return out
    band = _band(band_doc)
    if band is None:
        return out
    lo, hi = apply_aci_to_band(band[0], band[1], (band[1] - band[0]) / 2.0,
                               load_alpha(sport, segment, state_dir=state_dir),
                               _DEFAULT_ALPHA_TARGET)
    adjusted = dict(band_doc)
    adjusted["lo"], adjusted["hi"] = lo, hi
    out["static_interval"] = adjusted
    return out


__all__ = ["DEFAULT_GRADE_DIR", "DEFAULT_STATE_DIR", "state_path", "load_alpha",
           "update_stream", "apply_to_document"]
