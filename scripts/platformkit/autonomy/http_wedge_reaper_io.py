"""scripts.platformkit.autonomy.http_wedge_reaper_io -- state + decisions
persistence for http_wedge_reaper (split out to keep that module <=300 LOC).

Atomic tmp+os.replace, ASCII-only, under data/frontend/ops/ (mirrors
reaper_status_bridge.py / output_freshness.py's path convention). Never raises.

Per-file test: covered by scripts/platformkit/autonomy/test_http_wedge_reaper.py
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_STATE_PATH = _REPO / "data" / "frontend" / "ops" / "http_wedge_reaper_state.json"
DEFAULT_DECISIONS_PATH = _REPO / "data" / "frontend" / "ops" / "http_wedge_reaper.json"


def load_state_file(*, path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Best-effort load of the persisted per-name state dict. Never raises.

    Missing/corrupt file -> {} (a fresh reaper simply starts every streak at 0,
    which is the safe/conservative direction -- never fabricates a mid-streak).
    """
    try:
        p = Path(path) if path is not None else DEFAULT_STATE_PATH
        if not p.exists():
            return {}
        raw = p.read_text(encoding="ascii")
        if not raw.strip():
            return {}
        doc = json.loads(raw)
        return doc if isinstance(doc, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_state_file(state: Dict[str, Dict[str, Any]], *,
                     path: Optional[Path] = None) -> bool:
    """Atomically persist the per-name state dict. Never raises."""
    try:
        p = Path(path) if path is not None else DEFAULT_STATE_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(state or {}, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(p))
        return True
    except Exception:  # noqa: BLE001
        return False


def write_decisions(rows: Dict[str, Dict[str, Any]], *,
                     out_path: Optional[Path] = None,
                     now: Optional[float] = None) -> bool:
    """Atomically write the latest verdict rows for operator visibility.

    Mirrors reaper_status_bridge.write_reaper_status's shape/conventions:
    generated_at + rows + an honest_note. Never raises."""
    try:
        path = Path(out_path) if out_path is not None else DEFAULT_DECISIONS_PATH
        ts = float(now) if now is not None else time.time()
        doc = {
            "generated_at": ts,
            "rows": rows or {},
            "honest_note": (
                "http-readiness wedge reaper: kills ONLY the wedged PID on "
                ">=3 consecutive >10s HTTP timeouts WHILE the port stays "
                "listening AND CPU>50% sustained >120s; no $ field; "
                "no restart authority beyond the single kill (supervisor relaunches)."
            ),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "DEFAULT_STATE_PATH",
    "DEFAULT_DECISIONS_PATH",
    "load_state_file",
    "save_state_file",
    "write_decisions",
]
